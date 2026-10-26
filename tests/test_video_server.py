"""Tests for the local video extension server."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from connect_api.video_server import VideoExtensionHandler, manifest_document


class ManifestTests(unittest.TestCase):
    def test_manifest_points_at_the_extension_page(self) -> None:
        document = manifest_document("https://videos.example/")
        self.assertEqual(document["url"], "https://videos.example/")
        self.assertEqual(document["icon"], "https://videos.example/icon.svg")
        self.assertEqual(document["extensionType"], ["project"])
        self.assertTrue(document["title"])


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), VideoExtensionHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_manifest_is_cors_enabled_for_connect(self) -> None:
        with urllib.request.urlopen(f"{self.base}/manifest.json") as response:
            body = json.loads(response.read().decode())
            allow = response.headers["Access-Control-Allow-Origin"]
        self.assertEqual(allow, "*")
        self.assertEqual(body["url"], f"{self.base}/")
        self.assertEqual(body["extensionType"], ["project"])

    def test_extension_page_is_served_and_traversal_is_rejected(self) -> None:
        with urllib.request.urlopen(f"{self.base}/") as response:
            page = response.read().decode()
        self.assertIn("Video viewer", page)
        self.assertIn("/app.js", page)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base}/%2e%2e/connect_api/cli.py")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
