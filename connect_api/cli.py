"""Command line for Trimble ID login and Connect API calls."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from connect_api.auth import (
    TokenStore,
    authorize_url,
    client_credentials,
    exchange_code,
    fetch_userinfo,
    new_state,
    refresh,
    wait_for_authorization_code,
)
from connect_api.client import ConnectClient
from connect_api.config import credentials, load_env, redirect_uri, region_name, scope, secret_matches_client_id
from connect_api.errors import TrimbleError


def main(argv: Sequence[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(
        prog="connect-api",
        description="Sign in with Trimble ID and call the Trimble Connect Core v2 API.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Open the Trimble ID login URL and save a user token.")
    login.add_argument("--timeout", type=float, default=300, help="Seconds to wait for the browser redirect.")

    exchange = sub.add_parser("exchange", help="Exchange a one-time authorization code for a token.")
    exchange.add_argument("--code", required=True)

    sub.add_parser("refresh", help="Use the stored refresh token to get a new access token.")

    client_grant = sub.add_parser(
        "client-credentials",
        help="Request an application token. Connect project data uses the login command instead.",
    )
    client_grant.add_argument("--scope", default=None, help="Defaults to the connect scope only.")

    sub.add_parser("userinfo", help="Call Trimble ID userinfo with the stored token.")
    sub.add_parser("regions", help="List Connect regional deployments.")

    call = sub.add_parser("call", help="Call a Connect Core v2 path with the stored token.")
    call.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    call.add_argument("path", help="Path beginning with /, for example /regions.")
    call.add_argument("--query", action="append", default=[], metavar="KEY=VALUE")
    call.add_argument("--json", dest="json_body", default=None, help="JSON request body.")

    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            _login(args.timeout)
        elif args.command == "exchange":
            _exchange(args.code)
        elif args.command == "refresh":
            _refresh()
        elif args.command == "client-credentials":
            _client_credentials(args.scope)
        elif args.command == "userinfo":
            _print(fetch_userinfo(_access_token()))
        elif args.command == "regions":
            _print(ConnectClient(_access_token(), region=region_name()).regions())
        elif args.command == "call":
            _print(_call(args.method, args.path, args.query, args.json_body))
        else:
            parser.error(f"Unknown command {args.command}")
    except (TrimbleError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def _login(timeout: float) -> None:
    client_id, client_secret = _credentials()
    redirect = redirect_uri()
    state = new_state()
    url = authorize_url(client_id, redirect_uri=redirect, scope=scope(), state=state)
    print("Open this URL in a browser and sign in with your Trimble ID:")
    print(url)
    code = wait_for_authorization_code(redirect, state, timeout=timeout)
    token = exchange_code(client_id, client_secret, code, redirect_uri=redirect)
    TokenStore().save(token)
    print("Saved a Trimble ID token to .connect/token.json.")


def _exchange(code: str) -> None:
    client_id, client_secret = _credentials()
    token = exchange_code(client_id, client_secret, code, redirect_uri=redirect_uri())
    TokenStore().save(token)
    print("Saved a Trimble ID token to .connect/token.json.")


def _refresh() -> None:
    client_id, client_secret = _credentials()
    store = TokenStore()
    current = store.load()
    if current is None or not current.refresh_token:
        raise TrimbleError("No refresh token is stored. Run the login command first.")
    token = refresh(client_id, client_secret, current.refresh_token)
    if token.refresh_token is None:
        token.refresh_token = current.refresh_token
    store.save(token)
    print("Refreshed the stored Trimble ID token.")


def _client_credentials(requested_scope: str | None) -> None:
    client_id, client_secret = _credentials()
    granted_scope = requested_scope or "connect"
    token = client_credentials(client_id, client_secret, scope=granted_scope)
    TokenStore().save(token)
    print("Saved an application token to .connect/token.json.")
    print("Connect project calls on behalf of a user still require the login command.")


def _access_token() -> str:
    client_id, client_secret = _credentials()
    store = TokenStore()
    token = store.load()
    if token is None:
        raise TrimbleError("No token is stored. Run the login command first.")
    if token.expired:
        if not token.refresh_token:
            raise TrimbleError("The stored access token has expired. Run the login command again.")
        token = refresh(client_id, client_secret, token.refresh_token)
        if token.refresh_token is None:
            previous = store.load()
            if previous and previous.refresh_token:
                token.refresh_token = previous.refresh_token
        store.save(token)
    return token.access_token


def _call(method: str, path: str, query_items: list[str], json_body: str | None) -> object:
    query = {}
    for item in query_items:
        if "=" not in item:
            raise TrimbleError(f"Query item {item!r} must be KEY=VALUE.")
        key, value = item.split("=", 1)
        query[key] = value
    body = json.loads(json_body) if json_body is not None else None
    return ConnectClient(_access_token(), region=region_name()).request(
        method,
        path,
        query=query or None,
        json_body=body,
    )


def _credentials() -> tuple[str, str]:
    client_id, client_secret = credentials()
    if secret_matches_client_id(client_id, client_secret):
        print(
            "TRIMBLE_CLIENT_SECRET is the same value as TRIMBLE_CLIENT_ID. "
            "Trimble ID will reject the token request if that is not the secret shown "
            "in the Developer Console.",
            file=sys.stderr,
        )
    return client_id, client_secret


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2))
