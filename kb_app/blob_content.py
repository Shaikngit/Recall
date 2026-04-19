from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


MANAGED_NOTE_ROOT_NAMES = ("Inbox", "KB", "Quick Tips")
LEGACY_NOTE_ROOTS_ENV = "MYKB_LEGACY_NOTE_ROOTS"


class BlobContentStore:
    def __init__(
        self,
        app_root: Path,
        account_url: str,
        container_name: str,
        runtime_root: Path,
        bootstrap_root: Path | None,
        refresh_seconds: int,
    ) -> None:
        self.app_root = app_root
        self.account_url = account_url.rstrip("/")
        self.container_name = container_name
        self.runtime_root = runtime_root
        self.bootstrap_root = bootstrap_root
        self.refresh_seconds = max(refresh_seconds, 0)
        self.enabled = True
        self._lock = threading.Lock()
        self._last_refresh_at = 0.0
        self._container_checked = False
        self._bootstrap_checked = False

        credential = self._build_credential()
        service_client = BlobServiceClient(account_url=self.account_url, credential=credential)
        self._container_client = service_client.get_container_client(self.container_name)

    @classmethod
    def from_environment(cls, app_root: Path) -> BlobContentStore | DisabledContentStore:
        account_url = os.getenv("MYKB_BLOB_ACCOUNT_URL", "").strip()
        account_name = os.getenv("MYKB_BLOB_ACCOUNT_NAME", "").strip()
        if not account_url and account_name:
            account_url = f"https://{account_name}.blob.core.windows.net"
        if not account_url:
            return DisabledContentStore()

        container_name = os.getenv("MYKB_BLOB_CONTAINER", "mykb-content").strip() or "mykb-content"
        runtime_root = cls._resolve_runtime_root()
        bootstrap_root = cls._resolve_bootstrap_root(runtime_root, app_root)
        refresh_seconds = cls._parse_int_env("MYKB_BLOB_REFRESH_SECONDS", 30)
        return cls(app_root, account_url, container_name, runtime_root, bootstrap_root, refresh_seconds)

    @staticmethod
    def _build_credential():
        managed_identity_client_id = os.getenv("AZURE_CLIENT_ID", "").strip() or None
        if os.getenv("WEBSITE_HOSTNAME", "").strip():
            return ManagedIdentityCredential(client_id=managed_identity_client_id)
        if managed_identity_client_id:
            return DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
        return DefaultAzureCredential()

    @staticmethod
    def _resolve_runtime_root() -> Path:
        configured_root = os.getenv("MYKB_BLOB_CACHE_ROOT", "").strip()
        if configured_root:
            return Path(configured_root).expanduser().resolve()
        return (Path(tempfile.gettempdir()) / "mykb-content-cache").resolve()

    @classmethod
    def _resolve_bootstrap_root(cls, runtime_root: Path, app_root: Path) -> Path | None:
        configured_root = os.getenv("MYKB_BLOB_BOOTSTRAP_ROOT", "").strip()
        if configured_root:
            candidate = Path(configured_root).expanduser().resolve()
            if candidate.exists() and candidate != runtime_root:
                return candidate

        legacy_root = os.getenv("MYKB_CONTENT_ROOT", "").strip()
        if legacy_root:
            candidate = Path(legacy_root).expanduser().resolve()
            if candidate.exists() and candidate != runtime_root:
                return candidate

        return app_root if app_root.exists() and app_root != runtime_root else None

    @staticmethod
    def _parse_int_env(env_name: str, default_value: int) -> int:
        raw_value = os.getenv(env_name, "").strip()
        if not raw_value:
            return default_value
        try:
            return int(raw_value)
        except ValueError:
            return default_value

    def ensure_ready(self, force_refresh: bool = False) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if not force_refresh and self.refresh_seconds and monotonic() - self._last_refresh_at < self.refresh_seconds:
            return

        with self._lock:
            if not force_refresh and self.refresh_seconds and monotonic() - self._last_refresh_at < self.refresh_seconds:
                return
            self._ensure_container()
            self._maybe_bootstrap()
            self._refresh_cache()
            self._last_refresh_at = monotonic()

    def upload_file(self, local_path: Path) -> None:
        if not local_path.exists():
            return
        self._ensure_container()
        blob_name = self.relative_blob_name(local_path)
        if not blob_name:
            return
        payload = local_path.read_bytes()
        blob_client = self._container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            payload,
            overwrite=True,
            content_settings=ContentSettings(content_type="text/markdown; charset=utf-8"),
        )
        self._last_refresh_at = monotonic()

    def delete_file(self, local_path: Path) -> None:
        self._ensure_container()
        blob_name = self.relative_blob_name(local_path)
        if not blob_name:
            return
        try:
            self._container_client.delete_blob(blob_name)
        except ResourceNotFoundError:
            pass
        self._last_refresh_at = monotonic()

    def relative_blob_name(self, local_path: Path) -> str:
        try:
            return local_path.resolve().relative_to(self.runtime_root).as_posix()
        except ValueError:
            return ""

    def _ensure_container(self) -> None:
        if self._container_checked:
            return
        try:
            self._container_client.create_container()
        except ResourceExistsError:
            pass
        self._container_checked = True

    def _maybe_bootstrap(self) -> None:
        if self._bootstrap_checked:
            return
        self._bootstrap_checked = True
        if self.bootstrap_root is None or not self.bootstrap_root.exists():
            return
        if next(iter(self._container_client.list_blobs()), None) is not None:
            return

        for note_file in self._iter_note_files(self.bootstrap_root):
            blob_name = note_file.relative_to(self.bootstrap_root).as_posix()
            blob_client = self._container_client.get_blob_client(blob_name)
            blob_client.upload_blob(
                note_file.read_bytes(),
                overwrite=True,
                content_settings=ContentSettings(content_type="text/markdown; charset=utf-8"),
            )

    def _refresh_cache(self) -> None:
        remote_names: set[str] = set()
        for blob in self._container_client.list_blobs():
            if not blob.name.lower().endswith(".md"):
                continue
            remote_names.add(blob.name)
            local_path = self.runtime_root / Path(blob.name)
            if self._should_download(local_path, blob.last_modified):
                local_path.parent.mkdir(parents=True, exist_ok=True)
                payload = self._container_client.get_blob_client(blob.name).download_blob().readall()
                local_path.write_bytes(payload)
                self._apply_timestamp(local_path, blob.last_modified)

        for local_file in self._iter_note_files(self.runtime_root):
            blob_name = local_file.relative_to(self.runtime_root).as_posix()
            if blob_name in remote_names:
                continue
            local_file.unlink(missing_ok=True)
        self._prune_empty_directories(self.runtime_root)

    def _should_download(self, local_path: Path, last_modified: datetime | None) -> bool:
        if not local_path.exists() or last_modified is None:
            return True
        local_timestamp = local_path.stat().st_mtime
        remote_timestamp = last_modified.astimezone(timezone.utc).timestamp()
        return remote_timestamp - local_timestamp > 1

    def _apply_timestamp(self, local_path: Path, last_modified: datetime | None) -> None:
        if last_modified is None:
            return
        timestamp = last_modified.astimezone(timezone.utc).timestamp()
        os.utime(local_path, (timestamp, timestamp))

    def _prune_empty_directories(self, root: Path) -> None:
        for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
            if any(directory.iterdir()):
                continue
            directory.rmdir()

    def _iter_note_files(self, root: Path):
        for note_root in self._iter_note_roots(root):
            if note_root.is_file() and note_root.suffix.lower() == ".md":
                yield note_root
                continue
            if not note_root.exists():
                continue
            for note_file in note_root.rglob("*.md"):
                yield note_file

    def _iter_note_roots(self, root: Path):
        yielded: set[Path] = set()
        for root_name in MANAGED_NOTE_ROOT_NAMES:
            note_root = root / root_name
            if note_root in yielded:
                continue
            yielded.add(note_root)
            yield note_root
        for extra_root in self._legacy_note_roots(root):
            if extra_root in yielded:
                continue
            yielded.add(extra_root)
            yield extra_root

    def _legacy_note_roots(self, root: Path) -> list[Path]:
        raw_value = os.getenv(LEGACY_NOTE_ROOTS_ENV, "")
        if not raw_value:
            return []

        resolved_paths: list[Path] = []
        for raw_path in raw_value.split(";"):
            normalized_path = raw_path.strip().replace("\\", "/").strip("/")
            if not normalized_path:
                continue
            candidate_path = (root / normalized_path).resolve()
            try:
                candidate_path.relative_to(root)
            except ValueError:
                continue
            if candidate_path.exists():
                resolved_paths.append(candidate_path)
        return resolved_paths


class DisabledContentStore:
    def __init__(self) -> None:
        self.enabled = False
        self.account_url = ""
        self.container_name = ""
        self.runtime_root = Path()

    def ensure_ready(self, force_refresh: bool = False) -> None:
        return None

    def upload_file(self, local_path: Path) -> None:
        return None

    def delete_file(self, local_path: Path) -> None:
        return None