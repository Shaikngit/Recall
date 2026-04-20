from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kb_app.app import create_app
from kb_app import core


class FailingContentStore:
    def __init__(self, runtime_root: Path) -> None:
        self.enabled = True
        self.account_url = "https://example.blob.core.windows.net"
        self.container_name = "mykb-content"
        self.runtime_root = runtime_root

    def ensure_ready(self, force_refresh: bool = False) -> None:
        raise RuntimeError("refresh cache: AuthorizationFailure")

    def upload_file(self, local_path: Path) -> None:
        return None

    def delete_file(self, local_path: Path) -> None:
        return None

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": True,
            "accountUrl": self.account_url,
            "container": self.container_name,
            "runtimeRoot": self.runtime_root.as_posix(),
            "bootstrapRoot": "",
            "refreshSeconds": 30,
            "containerChecked": False,
            "bootstrapChecked": False,
            "lastRefreshStartedAt": "",
            "lastRefreshCompletedAt": "",
            "lastRefreshBlobCount": 0,
            "lastRefreshDownloadCount": 0,
            "lastRefreshDeleteCount": 0,
            "lastBootstrapFileCount": 0,
            "lastUploadBlob": "",
            "lastDeleteBlob": "",
            "lastError": "refresh cache: AuthorizationFailure",
        }


class AdminRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_admin_token = os.environ.get("MYKB_ADMIN_TOKEN")
        os.environ["MYKB_ADMIN_TOKEN"] = "test-token"
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        if self.previous_admin_token is None:
            os.environ.pop("MYKB_ADMIN_TOKEN", None)
        else:
            os.environ["MYKB_ADMIN_TOKEN"] = self.previous_admin_token

    def test_storage_diagnostics_requires_token(self) -> None:
        response = self.client.get("/api/storage/diagnostics")

        self.assertEqual(response.status_code, 403)

    def test_storage_diagnostics_returns_data_with_token(self) -> None:
        response = self.client.get("/api/storage/diagnostics?token=test-token")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        assert payload is not None
        self.assertTrue(payload["enabled"] in {True, False})
        self.assertIn("container", payload)

    def test_storage_admin_page_prompts_without_token(self) -> None:
        response = self.client.get("/admin/storage")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin token", response.data)

    def test_storage_admin_page_renders_diagnostics_with_token(self) -> None:
        response = self.client.get("/admin/storage?token=test-token")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Storage Diagnostics", response.data)
        self.assertIn(b"Tracked blobs", response.data)

    def test_homepage_and_recent_survive_blob_auth_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            failing_store = FailingContentStore(runtime_root)

            with patch.object(core, "CONTENT_STORE", failing_store), \
                 patch.object(core, "CONTENT_ROOT", runtime_root), \
                 patch.object(core, "INBOX_DIR", runtime_root / "Inbox"), \
                 patch.object(core, "KB_DIR", runtime_root / "KB"), \
                 patch.object(core, "QUICK_TIPS_DIR", runtime_root / "Quick Tips"):
                app = create_app()
                client = app.test_client()

                homepage_response = client.get("/")
                recent_response = client.get("/api/recent")
                status_response = client.get("/api/content/status")

        self.assertEqual(homepage_response.status_code, 200)
        self.assertEqual(recent_response.status_code, 200)
        self.assertEqual(recent_response.get_json(), [])
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.get_json()
        assert payload is not None
        self.assertFalse(payload["storageHealthy"])
        self.assertIn("AuthorizationFailure", payload["storageWarning"])