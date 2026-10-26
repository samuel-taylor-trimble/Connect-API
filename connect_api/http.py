"""JSON HTTP helper. Responses are returned to callers; secrets are not logged."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def request_json(request: urllib.request.Request, *, timeout: float = 60) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode(error.read())


def _decode(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:500]}
