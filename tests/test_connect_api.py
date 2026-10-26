"""Tests for Trimble ID request shape and the Connect client."""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from connect_api.auth import (
    Token,
    TokenStore,
    authorize_url,
    basic_credentials,
    exchange_code,
    wait_for_authorization_code,
)
from connect_api.client import ConnectClient
from connect_api.config import load_env, secret_matches_client_id
from connect_api.errors import TrimbleError


class AuthTests(unittest.TestCase):
    def test_authorize_url_uses_connect_scope_and_state(self) -> None:
        url = authorize_url(
            "client-id",
            redirect_uri="http://localhost:8181/callback",
            scope="openid connect",
            state="state-value",
        )
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "id.trimble.com")
        self.assertEqual(parsed.path, "/oauth/authorize")
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], ["http://localhost:8181/callback"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["scope"], ["openid connect"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertNotIn("client-secret", url)

    def test_basic_credentials_do_not_wrap(self) -> None:
        encoded = basic_credentials("id", "secret")
        self.assertNotIn("\n", encoded)
        self.assertEqual(base64.b64decode(encoded).decode(), "id:secret")

    def test_exchange_posts_authorization_code_with_basic_auth(self) -> None:
        payload = json.dumps(
            {"access_token": "access-token", "token_type": "Bearer", "expires_in": 3600}
        ).encode()

        class Response:
            status = 200

            def read(self) -> bytes:
                return payload

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with patch("connect_api.http.urllib.request.urlopen", return_value=Response()) as urlopen:
            token = exchange_code(
                "id",
                "secret",
                "one-time-code",
                redirect_uri="http://localhost:8181/callback",
            )

        request = urlopen.call_args.args[0]
        body = urllib.parse.parse_qs(request.data.decode())
        header = request.get_header("Authorization")
        self.assertEqual(request.full_url, "https://id.trimble.com/oauth/token")
        self.assertEqual(body["grant_type"], ["authorization_code"])
        self.assertEqual(body["code"], ["one-time-code"])
        self.assertEqual(body["redirect_uri"], ["http://localhost:8181/callback"])
        self.assertEqual(base64.b64decode(header.split(" ", 1)[1]).decode(), "id:secret")
        self.assertEqual(token.access_token, "access-token")
        self.assertNotIn("access-token", repr(token))

    def test_token_error_omits_credentials(self) -> None:
        class Response:
            status = 401

            def read(self) -> bytes:
                return json.dumps(
                    {"error": "invalid_client", "error_description": "bad credentials"}
                ).encode()

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with patch("connect_api.http.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(TrimbleError) as raised:
                exchange_code("id", "secret", "code", redirect_uri="http://localhost:8181/callback")
        message = str(raised.exception)
        self.assertIn("invalid_client", message)
        self.assertNotIn("secret", message)

    def test_callback_rejects_state_mismatch_and_accepts_code(self) -> None:
        redirect = "http://127.0.0.1:8765/callback"
        with self.assertRaises(TrimbleError):
            self._callback(redirect, expected_state="expected", query="code=abc&state=other")

        code = self._callback(redirect, expected_state="expected", query="code=abc&state=expected")
        self.assertEqual(code, "abc")

    def test_callback_rejects_public_redirect(self) -> None:
        with self.assertRaises(TrimbleError):
            wait_for_authorization_code("https://example.com/callback", "state", timeout=1)

    def _callback(self, redirect: str, *, expected_state: str, query: str) -> str:
        box: dict[str, object] = {}

        def run() -> None:
            try:
                box["code"] = wait_for_authorization_code(redirect, expected_state, timeout=5)
            except Exception as error:  # noqa: BLE001 - captured for the assertion below
                box["error"] = error

        thread = threading.Thread(target=run)
        thread.start()
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{redirect}?{query}", timeout=1).read()
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                if threading.Event().wait(0.05):
                    break
        thread.join(5)
        if "error" in box:
            raise box["error"]  # type: ignore[misc]
        return str(box["code"])


class ClientTests(unittest.TestCase):
    def test_regions_uses_regional_v2_base_and_bearer_token(self) -> None:
        payload = json.dumps([{"region": "us"}]).encode()

        class Response:
            status = 200

            def read(self) -> bytes:
                return payload

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with patch("connect_api.http.urllib.request.urlopen", return_value=Response()) as urlopen:
            body = ConnectClient("access-token", region="eu").regions()

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://eu.api.trimble.com/connect/v2/regions")
        self.assertEqual(request.get_header("Authorization"), "Bearer access-token")
        self.assertEqual(body, [{"region": "us"}])

    def test_token_store_round_trip_keeps_file_private(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            store = TokenStore(path)
            store.save(Token(access_token="access-token", expires_in=10, refresh_token="refresh-token"))
            loaded = store.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.access_token, "access-token")
            self.assertEqual(loaded.refresh_token, "refresh-token")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class EnvTests(unittest.TestCase):
    def test_dotenv_does_not_override_existing_environment(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('TRIMBLE_CLIENT_ID="from-file"\nTRIMBLE_CLIENT_SECRET=from-file\n', encoding="utf-8")
            with patch.dict("os.environ", {"TRIMBLE_CLIENT_ID": "from-env"}, clear=False):
                os.environ.pop("TRIMBLE_CLIENT_SECRET", None)
                load_env(path)
                self.assertEqual(os.environ["TRIMBLE_CLIENT_ID"], "from-env")
                self.assertEqual(os.environ["TRIMBLE_CLIENT_SECRET"], "from-file")
            os.environ.pop("TRIMBLE_CLIENT_SECRET", None)

    def test_matching_secret_is_detected(self) -> None:
        self.assertTrue(secret_matches_client_id("same", "same"))
        self.assertFalse(secret_matches_client_id("id", "secret"))

    def test_cli_login_warning_and_saved_token(self) -> None:
        from connect_api.cli import main

        with TemporaryDirectory() as directory:
            with patch("connect_api.cli.authorize_url", return_value="http://localhost/login"):
                with patch("connect_api.cli.wait_for_authorization_code", return_value="code"):
                    with patch(
                        "connect_api.cli.exchange_code",
                        return_value=Token(access_token="access-token", expires_in=3600),
                    ):
                        with patch.dict(
                            "os.environ",
                            {"TRIMBLE_CLIENT_ID": "same-value", "TRIMBLE_CLIENT_SECRET": "same-value"},
                            clear=False,
                        ):
                            stderr = io.StringIO()
                            with patch("connect_api.auth.TOKEN_PATH", Path(directory) / "token.json"):
                                with patch("sys.stderr", stderr):
                                    status = main(["login", "--timeout", "1"])
            self.assertEqual(status, 0)
            self.assertIn("same value", stderr.getvalue())
            stored = json.loads((Path(directory) / "token.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["access_token"], "access-token")


if __name__ == "__main__":
    unittest.main()
