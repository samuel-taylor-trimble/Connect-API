"""Authenticated calls to the Trimble Connect Core v2 API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Mapping

from connect_api.config import REGIONS
from connect_api.errors import TrimbleError
from connect_api.http import request_json


class ConnectClient:
    def __init__(self, access_token: str, *, region: str = "us"):
        if region not in REGIONS:
            known = ", ".join(sorted(REGIONS))
            raise TrimbleError(f"Unknown region {region!r}. Use one of: {known}.")
        if not access_token:
            raise TrimbleError("An access token is required.")
        self.region = region
        self.base_url = REGIONS[region]
        self._access_token = access_token

    def regions(self) -> Any:
        """List regional Connect deployments. This is the first call in Trimble's initial-transaction guide."""
        return self.request("GET", "/regions")

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        json_body: Any = None,
    ) -> Any:
        if not path.startswith("/"):
            raise TrimbleError("Connect API paths must start with '/'.")
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        status, payload = request_json(request)
        if status >= 400:
            if not isinstance(payload, dict):
                payload = {}
            error = payload.get("error") or payload.get("code") or "request_failed"
            description = (
                payload.get("error_description")
                or payload.get("message")
                or payload.get("raw")
                or "Connect API request failed."
            )
            raise TrimbleError(f"{error}: {description}", status=status, error=str(error))
        return payload
