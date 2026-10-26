"""Trimble ID authorization-code, refresh, and client-credentials grants."""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from connect_api.config import AUTHORIZE_URL, TOKEN_PATH, TOKEN_URL, USERINFO_URL
from connect_api.errors import TrimbleError
from connect_api.http import request_json

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class Token:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    refresh_token: str | None = None
    id_token: str | None = None
    obtained_at: float = 0.0

    def __post_init__(self) -> None:
        if self.obtained_at <= 0:
            self.obtained_at = time.time()

    @property
    def expired(self) -> bool:
        if self.expires_in <= 0:
            return False
        return time.time() >= self.obtained_at + self.expires_in - 60

    def to_json(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Token:
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise TrimbleError("Stored token file does not contain an access token.")
        refresh = data.get("refresh_token")
        id_token = data.get("id_token")
        return cls(
            access_token=access_token,
            token_type=str(data.get("token_type") or "Bearer"),
            expires_in=int(data.get("expires_in") or 0),
            refresh_token=refresh if isinstance(refresh, str) else None,
            id_token=id_token if isinstance(id_token, str) else None,
            obtained_at=float(data.get("obtained_at") or 0),
        )

    def __repr__(self) -> str:
        return (
            f"Token(token_type={self.token_type!r}, expires_in={self.expires_in}, "
            f"has_refresh={self.refresh_token is not None})"
        )


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = path or TOKEN_PATH

    def save(self, token: Token) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(token.to_json()), encoding="utf-8")
        self.path.chmod(0o600)

    def load(self) -> Token | None:
        if not self.path.is_file():
            return None
        return Token.from_json(json.loads(self.path.read_text(encoding="utf-8")))


def basic_credentials(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def authorize_url(
    client_id: str,
    *,
    redirect_uri: str,
    scope: str,
    state: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    *,
    redirect_uri: str,
) -> Token:
    return _token_request(
        client_id,
        client_secret,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )


def refresh(client_id: str, client_secret: str, refresh_token: str) -> Token:
    return _token_request(
        client_id,
        client_secret,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


def client_credentials(client_id: str, client_secret: str, *, scope: str) -> Token:
    return _token_request(
        client_id,
        client_secret,
        {
            "grant_type": "client_credentials",
            "scope": scope,
        },
    )


def fetch_userinfo(access_token: str) -> Any:
    request = urllib.request.Request(
        USERINFO_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    status, payload = request_json(request)
    if status >= 400:
        _raise_api(status, payload, "Trimble ID userinfo request failed.")
    return payload


def new_state() -> str:
    return secrets.token_urlsafe(24)


def wait_for_authorization_code(redirect_uri: str, state: str, *, timeout: float = 300) -> str:
    """Listen on a loopback redirect until Trimble ID returns an authorization code."""
    host, port, path = _loopback_bind(redirect_uri)
    result = _CallbackResult()
    try:
        server = _ReusableServer((host, port), _handler_factory(path, state, result))
    except OSError as error:
        raise TrimbleError(
            f"Could not listen on {redirect_uri}. "
            "Stop the process using that port, or set TRIMBLE_REDIRECT_URI to another "
            "localhost callback registered on the Developer Console application."
        ) from error

    server.timeout = 0.5
    deadline = time.time() + timeout
    try:
        while not result.done.is_set() and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if result.error is not None:
        raise result.error
    if result.code is None:
        raise TrimbleError(
            "Timed out waiting for Trimble ID to redirect to the callback URL. "
            "Open the printed login URL and sign in."
        )
    return result.code


def _token_request(client_id: str, client_secret: str, form: Mapping[str, str]) -> Token:
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Basic {basic_credentials(client_id, client_secret)}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    status, payload = request_json(request)
    if not isinstance(payload, dict) or status >= 400 or "access_token" not in payload:
        _raise_api(status, payload if isinstance(payload, dict) else {}, "Trimble ID token request failed.")
    refresh_token = payload.get("refresh_token")
    id_token = payload.get("id_token")
    return Token(
        access_token=str(payload["access_token"]),
        token_type=str(payload.get("token_type") or "Bearer"),
        expires_in=int(payload.get("expires_in") or 0),
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        id_token=id_token if isinstance(id_token, str) else None,
    )


def _raise_api(status: int, payload: Mapping[str, Any], fallback: str) -> None:
    error = payload.get("error")
    description = payload.get("error_description") or payload.get("message") or payload.get("raw")
    error_text = str(error) if error else "request_failed"
    detail = str(description) if description else fallback
    raise TrimbleError(f"{error_text}: {detail}", status=status, error=error_text)


def _loopback_bind(redirect_uri: str) -> tuple[str, int, str]:
    parsed = urllib.parse.urlparse(redirect_uri)
    hostname = parsed.hostname
    if parsed.scheme != "http" or hostname not in _LOOPBACK_HOSTS:
        raise TrimbleError(
            "The built-in login server only accepts http://localhost, 127.0.0.1, or ::1. "
            "For any other redirect URI, sign in in a browser and run the exchange command with the code."
        )
    if parsed.port is None:
        raise TrimbleError("Redirect URI must include a port, for example http://localhost:8181/callback.")
    bind_host = "127.0.0.1" if hostname == "localhost" else hostname
    return bind_host, parsed.port, parsed.path or "/"


class _ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True


class _CallbackResult:
    def __init__(self) -> None:
        self.code: str | None = None
        self.error: TrimbleError | None = None
        self.done = threading.Event()


def _handler_factory(expected_path: str, expected_state: str, result: _CallbackResult):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != expected_path:
                self._reply(404, "Not found")
                return
            query = urllib.parse.parse_qs(parsed.query)
            error = _first(query, "error")
            if error:
                description = _first(query, "error_description") or "Trimble ID did not return a code."
                result.error = TrimbleError(f"{error}: {description}", error=error)
                result.done.set()
                self._reply(400, "Trimble ID did not sign you in. Return to the terminal for the error.")
                return
            returned_state = _first(query, "state")
            if returned_state != expected_state:
                result.error = TrimbleError("Trimble ID returned a state value that does not match this login.")
                result.done.set()
                self._reply(400, "Login state did not match. Return to the terminal and try again.")
                return
            code = _first(query, "code")
            if not code:
                result.error = TrimbleError("Trimble ID redirect did not include an authorization code.")
                result.done.set()
                self._reply(400, "No authorization code was returned.")
                return
            result.code = code
            result.done.set()
            self._reply(200, "Signed in. You can close this window and return to the terminal.")

        def log_message(self, format: str, *args: Any) -> None:
            # The query string contains a one-time authorization code. Do not log it.
            return

        def _reply(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return CallbackHandler


def _first(query: Mapping[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]
