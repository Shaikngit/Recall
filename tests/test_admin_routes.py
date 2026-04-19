from __future__ import annotations

import os
import unittest

from kb_app.app import create_app


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