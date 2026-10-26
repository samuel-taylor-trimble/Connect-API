"""Environment and endpoint settings for Trimble Connect."""

from __future__ import annotations

import os
from pathlib import Path

AUTHORIZE_URL = "https://id.trimble.com/oauth/authorize"
TOKEN_URL = "https://id.trimble.com/oauth/token"
USERINFO_URL = "https://id.trimble.com/oauth/userinfo"

# Regional Core v2 bases from the Connect integration guide.
REGIONS = {
    "us": "https://us-east.api.trimble.com/connect/v2",
    "eu": "https://eu.api.trimble.com/connect/v2",
}

DEFAULT_REDIRECT_URI = "http://localhost:8181/callback"
DEFAULT_SCOPE = "openid connect"
DEFAULT_REGION = "us"
TOKEN_PATH = Path(".connect") / "token.json"


def load_env(path: Path | None = None) -> None:
    """Load a .env file without overriding variables already set in the process."""
    file = path or Path(".env")
    if not file.is_file():
        return
    for raw_line in file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def credentials() -> tuple[str, str]:
    client_id = os.environ.get("TRIMBLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("TRIMBLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Set TRIMBLE_CLIENT_ID and TRIMBLE_CLIENT_SECRET in the environment or in .env."
        )
    return client_id, client_secret


def secret_matches_client_id(client_id: str, client_secret: str) -> bool:
    return bool(client_id) and client_id == client_secret


def redirect_uri() -> str:
    return os.environ.get("TRIMBLE_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip() or DEFAULT_REDIRECT_URI


def scope() -> str:
    return os.environ.get("TRIMBLE_SCOPE", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE


def region_name() -> str:
    name = os.environ.get("TRIMBLE_REGION", DEFAULT_REGION).strip().lower() or DEFAULT_REGION
    if name not in REGIONS:
        known = ", ".join(sorted(REGIONS))
        raise RuntimeError(f"Unknown TRIMBLE_REGION {name!r}. Use one of: {known}.")
    return name
