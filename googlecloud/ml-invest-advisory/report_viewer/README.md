# Report Viewer (beta)

A web UI that shows every HTML report uploaded by
[`portfolio_reports/ollama_report_pipeline/run-market-hours.sh`](../portfolio_reports/ollama_report_pipeline/run-market-hours.sh)
to `gs://hil-financial-services-smart-invest/reports/<portfolio>/` in tabs, so you can switch between ~24 reports
in one browser tab instead of opening each `https://storage.cloud.google.com/...` URL separately.

- **Portfolio tabs** (top row): one per portfolio folder, e.g. `hil-michelle-portfolio-1`, `vicky`, `vicky-tw-portfolio`,
  `yang`, each with a count of its reports.
- **Report tabs** (second row): the portfolio's daily report first, then one news report per news site
  (CNBC, Fundstrat, Fundstrat daily technical, Fundstrat macro analysis, Global headlines, WSJ).
- **Info bar**:
  - when the report was last uploaded (highlighted if older than 24 h), its size and file name
  - a **Reload** button
  - an **Open in Cloud Storage ↗** link to the report's authenticated `storage.cloud.google.com` URL
- **Refresh list** lists the bucket again and picks up new or re-uploaded reports.
- **Bookmarkable tabs**: the URL hash holds the selected report (e.g. `#yang%2Fdaily-report-yang-llm-generated.html`) and
  survives the sign-in round trip.
- **Keyboard**: ←/→/Home/End switch tabs.
- **Light and dark theme**: follows the browser/OS setting (see [Dark theme](#dark-theme)).

## Product requirements

[PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) (also as [PRODUCT_REQUIREMENTS.html](PRODUCT_REQUIREMENTS.html))
describes the existing features and the planned **Ask AI** export to Google Gemini and Meta AI. Edit the `.md`,
then regenerate the HTML with pandoc. [docs-style.html](docs-style.html) holds the page style (light/dark, tables):

```bash
pandoc -s -f gfm+yaml_metadata_block -t html5 --toc --toc-depth=1 --metadata toc-title=Contents \
  --include-in-header docs-style.html -o PRODUCT_REQUIREMENTS.html PRODUCT_REQUIREMENTS.md
```

## Access control

Visitors **sign in with their own Google account**. The server reads Cloud Storage with that visitor's access token
and has **no credentials of its own**. Cloud Storage IAM therefore decides who can read the reports, the same check
`storage.cloud.google.com` makes:

| Visitor                                              | `/api/reports`, `/reports/<portfolio>/<file>` |
|------------------------------------------------------|-----------------------------------------------|
| Not signed in (e.g. a private browsing window)       | **401**, page offers "Sign in with Google" |
| Signed in, account has no read access to the bucket  | **403** from Cloud Storage, page names the account |
| Signed in, account can read the bucket               | the reports                       |

To let someone else see the reports, give their Google account read access to the bucket, e.g.
`roles/storage.objectViewer`. Also add them as a test user on the OAuth consent screen while the app is in
"Testing" (see step 1 below).

Sessions live in the server's memory. A session ends when its Google access token expires (about 1 hour; no refresh
token is requested or stored), when you click **Sign out** (which also revokes the token), or when the server
restarts. Signing in again is usually one click, because Google remembers the consent.

> Before this beta, the viewer read the bucket with the `gcloud` login of whoever started it, and the browser
> never had to sign in. Anyone who could reach the port, a private window included, could read every report. That
> design is gone: the server won't start without an OAuth client, and it never falls back to server-side
> credentials.

## How it works

```
browser ──► report_viewer.py ──(the visitor's own access token)──► Cloud Storage JSON API
   │          /                             static/index.html, the tab UI (public: holds no report data)
   │          /api/reports                  reports grouped into tabs (report_catalog.py)   sign-in required
   │          /reports/<portfolio>/<file>   one report's HTML, shown in the tab's <iframe>   sign-in required
   │          /auth/login                   redirects to Google sign-in
   └────────► /auth/callback                Google redirects back; the server creates the session (google_sign_in.py)
              /auth/logout                  POST: ends the session and revokes the token
```

| File                                 | What it does                                                           |
|--------------------------------------|------------------------------------------------------------------------|
| [report_viewer.py](report_viewer.py) | Entry point: configuration, HTTP routes, access checks, responses      |
| [google_sign_in.py](google_sign_in.py) | OAuth 2.0 authorization code flow with PKCE, in-memory sessions      |
| [cloud_storage.py](cloud_storage.py) | Lists and downloads the reports with the signed-in user's token        |
| [report_catalog.py](report_catalog.py) | Groups report file names into portfolio and report tabs              |
| [static/index.html](static/index.html) | The tab UI                                                           |

Why not `<iframe>` the `storage.cloud.google.com` URLs directly? Those responses send
`x-frame-options: SAMEORIGIN`, and their login relies on third-party cookies inside an iframe, which browsers
increasingly block.

Standard library only. Nothing to `pip install`.

## Setup

### 1. Create an OAuth client (once)

In the [Google Cloud console](https://console.cloud.google.com/), pick a project, ideally the one that holds the
bucket:

1. **APIs & Services → OAuth consent screen**: choose **External** (or **Internal** for a Google Workspace
   organization), fill in the app name and support email, and add the scope
   `https://www.googleapis.com/auth/devstorage.read_only`. While the app's publishing status is **Testing**, add
   every Google account that should sign in under **Test users**. Google shows an "unverified app" notice to test
   users, which is expected for a personal app.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs: `<address>/auth/callback` for every address the viewer is opened at, e.g.
     `http://localhost:8080/auth/callback` and `https://services.googlecloud.fr/auth/callback`. Google refuses
     sign-in at an address whose redirect URI isn't listed.
3. Download the client JSON and keep it outside the repository. The viewer looks for it at
   `/home/hil/Encfs/confidential/secrets/client_secret_603410815034-35d82rt5p1t0n4mijg5j14g5etjoqnih.apps.googleusercontent.com.json`
   (`DEFAULT_OAUTH_CLIENT_FILE` in [google_sign_in.py](google_sign_in.py)); restrict it with `chmod 600 <file>`.
   Another location works with `OAUTH_CLIENT_FILE`.
   (`client_secret*.json` is in this folder's `.gitignore` as a safety net.)

The Cloud Storage JSON API must be enabled in that project. It is enabled by default.

### 2. Run

```bash
cd report_viewer
python3 report_viewer.py     # reads the OAuth client from the default file above
# Cannot listen on 0.0.0.0:80 (Permission denied); trying port 8080
# Report Viewer (beta) for gs://hil-financial-services-smart-invest/reports/<portfolio>/*.html
#   listening on 0.0.0.0:8080; open http://localhost:8080/
#   OAuth redirect URI (must be authorized on the client): http://localhost:8080/auth/callback
```

Open <http://localhost:8080> and click **Sign in with Google**.

### Configuration (environment variables)

| Variable              | Default                               | Meaning                                         |
|-----------------------|---------------------------------------|-------------------------------------------------|
| `OAUTH_CLIENT_FILE`   | the default file (see setup step 3)   | OAuth client JSON from the console              |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | (instead of the file)  | OAuth client ID and secret; used before the default file |
| `PUBLIC_BASE_URL`     | (unset: the address of each request)  | Optional; pins sign-in to this one address, e.g. `https://services.example` |
| `GCS_BUCKET`          | `hil-financial-services-smart-invest` | Bucket with the reports                         |
| `GCS_PREFIX`          | `reports/`                            | Folder in the bucket, with one sub-folder per portfolio |
| `HOST`                | `0.0.0.0` (all interfaces)            | Listen address; `127.0.0.1` = this machine only |
| `PORT`                | unset: try `80`, then `8080`          | Listen on exactly this port                     |

### Ports

The server tries **port 80 first, then 8080**. On Linux, port 80 is a privileged port (below
`net.ipv4.ip_unprivileged_port_start`, usually 1024), so a normal user falls back to 8080. To get port 80 while
still running as yourself, give the Python binary the bind capability once:

```bash
sudo setcap 'cap_net_bind_service=+ep' "$(readlink -f "$(which python3)")"
# undo: sudo setcap -r "$(readlink -f "$(which python3)")"
```

This lets every script run by that `python3` binary bind ports below 1024. A venv doesn't limit it: its `python3`
is a symlink to the same binary. If neither port can be bound (e.g. another viewer already uses 8080), the server
exits with an error. Set `PORT` to use one specific port instead.

### Opening the viewer from other devices

The server listens on all interfaces, and sign-in uses whatever address the browser used: the `Host` header, or
`X-Forwarded-Host` and `X-Forwarded-Proto` from a reverse proxy. That address's `/auth/callback` must be an
authorized redirect URI, and Google accepts plain `http://` redirect URIs only for `localhost`, never raw IP
addresses such as `http://192.168.1.2:8080`. Options for other devices:

- **SSH tunnel** (no setup on the server):
  `ssh -L 8080:localhost:8080 <this machine>`, then open `http://localhost:8080` on the other device.
- **HTTPS name** in front of the server, e.g. `tailscale serve 8080` (gives `https://<machine>.<tailnet>.ts.net`)
  or a reverse proxy with a TLS certificate that passes the original `Host` (or sets `X-Forwarded-Host`) and sets
  `X-Forwarded-Proto: https`. Add `https://<that name>/auth/callback` as an authorized redirect URI. Over
  `https://` the cookies are also marked `Secure`.

Set `PUBLIC_BASE_URL=https://<that name>` only to pin sign-in to that one address, e.g. when the proxy can't pass
the host; **Sign in with Google** at any other address then shows a page pointing to it.

Use `HOST=127.0.0.1` if only this machine (or an SSH tunnel or a local proxy) needs to reach it.

## Dark theme

The viewer and the reports follow the browser/OS light or dark setting (`prefers-color-scheme`). The reports' dark
theme comes from `HTML_REPORT_STYLE` in
[`report-common.sh`](../portfolio_reports/ollama_report_pipeline/report-common.sh), which `write_html_report` passes
to pandoc with `--include-in-header`. So it applies to reports generated **after** that change. Reports already in
the bucket stay light until the pipeline regenerates and re-uploads them. Printing a report stays black on white.

## Tab grouping

`run-market-hours.sh` uploads each portfolio's reports to its own folder (see `report-daily.sh` and
`report-news-impact.sh` for the names):

- `<GCS_PREFIX><portfolio>/daily-report-<portfolio>-llm-generated.html` is the **Daily report** tab.
- `<GCS_PREFIX><portfolio>/news-<site>-<portfolio>-llm-generated.html` is a **News · <site>** tab. The folder
  names the portfolio, so the site is whatever sits between `news-` and `-<portfolio>`. For example,
  `vicky-tw-portfolio/news-fundstrat-daily-technical-vicky-tw-portfolio-…` is `News · Fundstrat daily technical`.
- Any other `*.html` in a portfolio folder gets a tab after those, labelled with its file name.
- Files directly under `GCS_PREFIX` (the old flat layout) or in deeper folders aren't listed.

If a new `--site` of `fetch-news.sh` needs special capitalization (like `CNBC`), add it to `SITE_LABELS` in
[`report_catalog.py`](report_catalog.py).

## Security notes

- **Access**: see [Access control](#access-control). The report list and the reports need a session, and Cloud
  Storage checks the session's own token on every request.
- **Sign-in**: the authorization code flow with PKCE and a one-time `state` value bound to the browser by a
  short-lived cookie, which prevents login CSRF. Only the `openid`, `email` and `devstorage.read_only` scopes are
  requested.
- **Cookies**: the session cookie is a random 256-bit ID, `HttpOnly` and `SameSite=Lax`, and `Secure` over
  `https://` (an `https://` `PUBLIC_BASE_URL`, or `X-Forwarded-Proto: https`). Access tokens never reach the
  browser. Sign-out is a `POST`, so other sites can't trigger it.
- **Plain HTTP**: over plain `http://` (fine for `localhost`), anyone who can watch the network traffic could copy
  the session cookie. Serve it over `https://` for anything beyond this machine.
- **Report names**: only `<portfolio>/<file>.html` paths under `GCS_PREFIX` are served, each part made of
  letters, digits, `.`, `_` and `-` and not starting with `.`. Path traversal is rejected.
- **Report content**: reports hold LLM output and news text, and pandoc passes raw HTML through. So they are served
  with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none';
  frame-ancestors 'self'; base-uri 'none'` and shown in a sandboxed iframe without `allow-scripts`. They can't run
  scripts, submit forms or make outbound requests, and only the viewer can frame them. Links that leave a report
  open in a new tab, with `Referrer-Policy: no-referrer`.
- **The page's own script**: the CSP allows only the page's inline `<script>`, by its SHA-256 hash, computed when
  the page is served. So editing `static/index.html` needs no CSP change, but inline event handlers
  (`onclick="..."`) won't run; use `addEventListener`.
- **Slow or idle clients**: a connection that doesn't finish its request within 30 s
  (`REQUEST_TIMEOUT_SECONDS`) is closed, so slowloris-style clients can't hold server threads forever.
- **Memory bounds**: anyone can start a sign-in, so at most 10,000 are pending (`MAX_PENDING_SIGN_INS`; the oldest
  is dropped). Expired sessions are purged.
- **Sign-in address**: a forged `Host` or `X-Forwarded-*` header can't send a sign-in elsewhere: Google only
  redirects to authorized redirect URIs, the state cookie stays on the host the browser really used, and malformed
  host values are rejected. Expose the viewer only through the proxy, so those headers come from it.
- **HTTPS**: over `https://`, every response also carries
  `Strict-Transport-Security: max-age=31536000`.
- **Sessions**: they are in memory only, so restarting the server signs everyone out.

## Tests

```bash
cd report_viewer
python3 -m unittest -v test_report_viewer.py     # or: python -m pytest -v test_report_viewer.py
```

Cloud Storage and Google's OAuth endpoints are faked. The tests cover:

- the tab grouping
- 401 for visitors who aren't signed in, and for forged or expired sessions
- Cloud Storage's 403 being passed through
- the user's own token being used for every Cloud Storage call
- the sign-in flow: state binding, single-use state, required scope
- sign-out
- the port fallback

## Possible next steps

- Deploy to Cloud Run behind Identity-Aware Proxy, so a fixed HTTPS URL works from any device.
- Auto-refresh the list during market hours (the pipeline re-uploads reports continuously).
- Show a "new since last viewed" marker on tabs whose report was re-uploaded.
