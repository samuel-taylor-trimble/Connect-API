# Connect API

A small Python client for [Trimble Connect](https://developer.trimble.com/docs/connect) that signs in with Trimble ID and calls the Core v2 API.

Credentials stay in a local `.env` file. They are not stored in this repository.

## Credentials

1. In the Trimble Developer Console, create an end-user application with the Trimble Connect API product and the Authorization Code grant.
2. Register this callback URL: `http://localhost:8181/callback`
3. Copy `.env.example` to `.env` and set `TRIMBLE_CLIENT_ID` and `TRIMBLE_CLIENT_SECRET` from the application's Credentials tab.

The client secret is the private key from that tab. It is sent only to `https://id.trimble.com/oauth/token`, as a Basic authorization header, when exchanging a login code. If the secret is the same string as the client ID, the login command warns you: that usually means the secret was copied from the client ID field.

Because a client secret was pasted into the agent chat, rotate it in the Developer Console if this application is used anywhere else, then put the new secret only in `.env`.

## Sign in and call Connect

From the repository root:

```bash
python3 -m connect_api login
python3 -m connect_api userinfo
python3 -m connect_api regions
```

`login` prints a Trimble ID URL, listens on the localhost callback, and writes the token to `.connect/token.json` (gitignored, mode `0600`). The command does not print the access token.

`regions` calls `GET /regions` on the regional Core v2 base, which is the Connect call in Trimble's [initial API transaction](https://developer.trimble.com/docs/authentication/guides/initial-api-transaction/) guide.

| Region | Base URL |
| --- | --- |
| `us` (default) | `https://us-east.api.trimble.com/connect/v2` |
| `eu` | `https://eu.api.trimble.com/connect/v2` |

Set `TRIMBLE_REGION` in `.env` to choose the base URL. A project lives in one region.

Other commands:

```bash
python3 -m connect_api exchange --code CODE
python3 -m connect_api refresh
python3 -m connect_api call GET /regions
```

`client-credentials` requests an application token. Connect data for a signed-in user uses `login`. The scopes sent on login are `openid` and `connect`.

## What is implemented

Trimble has not published the Core v2 OpenAPI definition yet. This client implements the flow and the Connect call that the current docs specify:

- Authorization-code login, code exchange, and refresh against `https://id.trimble.com/oauth/token`
- `GET https://id.trimble.com/oauth/userinfo`
- `GET {region}/regions`
- `call`, for any other Core v2 path once you know it

Send the operations you need next (for example list projects, upload a file, or create a topic), including method, path, and a sample response if you have one. Those can be added on top of this login.
