from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kb_app.blob_content import BlobContentStore


class FakeDownload:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def readall(self) -> bytes:
        return self._payload


class FakeBlobClient:
    def __init__(self, container: "FakeContainerClient", name: str) -> None:
        self.container = container
        self.name = name

    def upload_blob(self, payload: bytes, overwrite: bool, content_settings=None) -> None:
        self.container.contents[self.name] = payload

    def download_blob(self) -> FakeDownload:
        return FakeDownload(self.container.contents[self.name])


class FakeBlob:
    def __init__(self, name: str, last_modified: datetime) -> None:
        self.name = name
        self.last_modified = last_modified


class FakeContainerClient:
    def __init__(self, contents: dict[str, bytes], last_modified: datetime) -> None:
        self.contents = contents
        self.last_modified = last_modified

    def list_blobs(self):
        return [FakeBlob(name, self.last_modified) for name in sorted(self.contents)]

    def get_blob_client(self, name: str) -> FakeBlobClient:
        return FakeBlobClient(self, name)

    def create_container(self) -> None:
        return None

    def delete_blob(self, name: str) -> None:
        self.contents.pop(name, None)


class BlobContentStoreTests(unittest.TestCase):
    def _build_store(self, runtime_root: Path, container: FakeContainerClient) -> BlobContentStore:
        store = BlobContentStore.__new__(BlobContentStore)
        store.app_root = runtime_root
        store.account_url = "https://example.blob.core.windows.net"
        store.container_name = "mykb-content"
        store.runtime_root = runtime_root
        store.bootstrap_root = None
        store.refresh_seconds = 30
        store.enabled = True
        store._lock = None
        store._last_refresh_at = 0.0
        store._container_checked = True
        store._bootstrap_checked = True
        store._last_refresh_started_at = ""
        store._last_refresh_completed_at = ""
        store._last_refresh_blob_count = 0
        store._last_refresh_download_count = 0
        store._last_refresh_delete_count = 0
        store._last_bootstrap_file_count = 0
        store._last_upload_blob = ""
        store._last_delete_blob = ""
        store._last_error = ""
        store._container_client = container
        return store

    def test_refresh_cache_downloads_remote_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            container = FakeContainerClient(
                {"Inbox/2026-04-19.md": b"# Inbox for 2026-04-19\n"},
                datetime.now(timezone.utc),
            )
            store = self._build_store(runtime_root, container)

            store._refresh_cache()

            downloaded = runtime_root / "Inbox" / "2026-04-19.md"
            self.assertTrue(downloaded.exists())
            self.assertEqual(downloaded.read_text(encoding="utf-8"), "# Inbox for 2026-04-19\n")
            self.assertEqual(store._last_refresh_download_count, 1)
            self.assertEqual(store._last_refresh_blob_count, 1)

    def test_refresh_cache_keeps_recent_local_file_missing_from_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            recent_local = runtime_root / "Inbox" / "pending.md"
            recent_local.parent.mkdir(parents=True, exist_ok=True)
            recent_local.write_text("pending", encoding="utf-8")

            container = FakeContainerClient({}, datetime.now(timezone.utc))
            store = self._build_store(runtime_root, container)

            store._refresh_cache()

            self.assertTrue(recent_local.exists())
            self.assertEqual(store._last_refresh_delete_count, 0)

    def test_refresh_cache_removes_old_local_file_missing_from_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            stale_local = runtime_root / "Inbox" / "stale.md"
            stale_local.parent.mkdir(parents=True, exist_ok=True)
            stale_local.write_text("stale", encoding="utf-8")
            stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()
            stale_local.touch()
            Path(stale_local).chmod(0o666)
            import os
            os.utime(stale_local, (stale_timestamp, stale_timestamp))

            container = FakeContainerClient({}, datetime.now(timezone.utc))
            store = self._build_store(runtime_root, container)

            store._refresh_cache()

            self.assertFalse(stale_local.exists())
            self.assertEqual(store._last_refresh_delete_count, 1)

    def test_diagnostics_exposes_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            container = FakeContainerClient({}, datetime.now(timezone.utc))
            store = self._build_store(runtime_root, container)
            store._last_upload_blob = "Inbox/example.md"
            store._last_delete_blob = "Inbox/old.md"
            store._last_error = ""

            diagnostics = store.diagnostics()

            self.assertTrue(diagnostics["enabled"])
            self.assertEqual(diagnostics["container"], "mykb-content")
            self.assertEqual(diagnostics["runtimeRoot"], runtime_root.as_posix())
            self.assertEqual(diagnostics["lastUploadBlob"], "Inbox/example.md")
            self.assertEqual(diagnostics["lastDeleteBlob"], "Inbox/old.md")


if __name__ == "__main__":
    unittest.main()