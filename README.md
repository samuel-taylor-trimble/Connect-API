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

## Play videos in Trimble Connect for Browser

Connect for Browser does not play project videos in its own viewer. This repository serves a project extension that Connect embeds. The extension asks Connect for the signed-in user's access token, lists video files through the published Core file API, and plays the selected file in the page.

The client secret is not part of this extension. Connect already has the user session.

Capability manifest URL:

`https://raw.githack.com/samuel-taylor-trimble/Connect-API/gh-pages/manifest.json`

In the project, open Settings → Apps & Capabilities → Add Custom and paste that URL. The extension files are in this repository on the `gh-pages` branch. That URL serves `manifest.json` as JSON with `Access-Control-Allow-Origin: *`, and serves the extension page as HTML so Connect can embed it.

GitHub Pages is not enabled on this repository, and the GitHub connection used here cannot change that setting. `https://samuel-taylor-trimble.github.io/Connect-API/` currently returns 404.

For a local copy instead of the published URL:

```bash
python3 -m connect_api video
```

That serves `http://127.0.0.1:8090/manifest.json` on the same computer as the browser.

A project administrator has to add it. Open Videos in the project navigation and allow the access-token prompt. The panel lists `.mp4`, `.m4v`, `.webm`, `.ogg`, `.ogv`, and `.mov` files, including files in subfolders. Choosing one requests `GET /files/fs/{fileId}/downloadurl` and plays that URL.

The file calls use the Core 2.0 API (`/tc/api/2.0`), because that is the published contract with a download URL. The extension reads `GET /regions` and uses the `tc-api` host for the project's `location`.

## What is implemented

Trimble has not published the Core v2 OpenAPI definition yet. This client implements the flow and the Connect call that the current docs specify:

- Authorization-code login, code exchange, and refresh against `https://id.trimble.com/oauth/token`
- `GET https://id.trimble.com/oauth/userinfo`
- `GET {region}/regions`
- `call`, for any other Core v2 path once you know it

Send the operations you need next (for example list projects, upload a file, or create a topic), including method, path, and a sample response if you have one. Those can be added on top of this login.
