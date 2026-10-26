"""Local host for the Trimble Connect video extension."""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

EXTENSION_ROOT = Path(__file__).resolve().parents[1] / "extension"


def manifest_document(public_base: str) -> dict[str, object]:
    base = public_base.rstrip("/")
    return {
        "title": "Video viewer",
        "description": "Play project video files inside Trimble Connect for Browser.",
        "url": f"{base}/",
        "icon": f"{base}/icon.svg",
        "infoUrl": f"{base}/",
        "extensionType": ["project"],
    }


class VideoExtensionHandler(BaseHTTPRequestHandler):
    server_version = "ConnectVideo/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/manifest.json":
            body = json.dumps(manifest_document(self._public_base())).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path in {"", "/"}:
            relative = "index.html"
        elif path == "/favicon.ico":
            relative = "icon.svg"
        else:
            relative = path.lstrip("/")
        file = self._safe_file(relative)
        if file is None:
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if file.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif file.suffix == ".svg":
            content_type = "image/svg+xml"
        self._send(200, content_type, file.read_bytes())

    def log_message(self, format: str, *args: object) -> None:
        # Extension requests do not carry Trimble tokens. Keep the local server quiet.
        return

    def _public_base(self) -> str:
        configured = os.environ.get("VIDEO_PUBLIC_URL", "").strip()
        if configured:
            return configured.rstrip("/")
        host = self.headers.get("Host", "127.0.0.1")
        proto = self.headers.get("X-Forwarded-Proto", "http")
        return f"{proto}://{host}".rstrip("/")

    def _safe_file(self, relative: str) -> Path | None:
        root = EXTENSION_ROOT.resolve()
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            return None
        if candidate.is_file():
            return candidate
        return None

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 8090) -> None:
    if not EXTENSION_ROOT.is_dir():
        raise RuntimeError(f"Extension files are missing at {EXTENSION_ROOT}.")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), VideoExtensionHandler)
    except OSError as error:
        raise RuntimeError(
            f"Could not listen on 127.0.0.1:{port}. Choose another port with --port."
        ) from error
    server.allow_reuse_address = True
    print("Video extension is ready.")
    print(f"Manifest URL: http://127.0.0.1:{port}/manifest.json")
    print("In Trimble Connect for Browser: Settings → Apps & Capabilities → Add Custom.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
