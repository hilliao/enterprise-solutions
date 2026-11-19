# Report Viewer (beta)

A web UI that shows every HTML report uploaded by
[`portfolio_reports/ollama_report_pipeline/run-market-hours.sh`](../portfolio_reports/ollama_report_pipeline/run-market-hours.sh)
to `gs://hil-financial-services-smart-invest/reports/<portfolio>/` in tabs, so you can switch between the reports
(7 per portfolio: the daily report and 6 news reports) in one browser tab instead of opening each
`https://storage.cloud.google.com/...` URL separately. It is part of [ml-invest-advisory](../README.md); the
[top-level README](../README.md) shows the whole system.

- **Portfolio tabs** (top row): one per portfolio folder, e.g. `hil-michelle-portfolio-1`, `vicky`, `vicky-tw-portfolio`,
  `yang`, each with a count of its reports.
- **Report tabs** (second row): the portfolio's daily report first, then one news report per `fetch-news.sh --site`
  key, by site: Aggregate, CNBC, Fundstrat daily technical, Fundstrat flash insights, Fundstrat macro analysis, WSJ.
- **Fits any screen**: above 600 px wide the tabs wrap onto more rows. At 600 px or narrower (phones) each row
  scrolls sideways, with fade cues when more tabs are off-screen. The selected tab is kept in view on resize.
- **Info bar**:
  - when the report was last uploaded (highlighted if older than 24 h), its size and file name
  - a **Reload** button
  - an **Open in Cloud Storage ↗** link to the report's authenticated `storage.cloud.google.com` URL
- **Refresh list** lists the bucket again and picks up new or re-uploaded reports.
- **Bookmarkable tabs**: the URL hash holds the selected report (e.g. `#yang%2Fdaily-report-yang-llm-generated.html`) and
  survives the sign-in round trip.
- **Keyboard**: ←/→/Home/End switch tabs.
- **Light and dark theme**: follows the browser/OS setting (see [Dark theme](#dark-theme)).

## Where the reports come from

The viewer only reads. It needs a working report pipeline that has uploaded reports:

1. [`fetch-news.sh`](../portfolio_reports/ollama_report_pipeline/fetch-news.sh) writes the news files the news
   reports are built from.
2. [`run-market-hours.sh`](../portfolio_reports/ollama_report_pipeline/run-market-hours.sh) runs
   [`report-daily.sh`](../portfolio_reports/ollama_report_pipeline/report-daily.sh) and
   [`report-news-impact.sh`](../portfolio_reports/ollama_report_pipeline/report-news-impact.sh) in a loop during
   market hours.
3. Each HTML report is uploaded with
   [`upload-report.sh`](../portfolio_reports/ollama_report_pipeline/upload-report.sh) (`gcloud storage cp
   --configuration=$GCLOUD_CONFIG`) to `GCS_BUCKET<portfolio>/`.

For the viewer to show them:

- The pipeline's `GCS_BUCKET` (a `gs://bucket/prefix/` URL in the `CONFIGURATION` section of
  `run-market-hours.sh`) must be the same folder as this viewer's `gs://$GCS_BUCKET/$GCS_PREFIX`.
- The pipeline's `GCLOUD_CONFIG` account needs write access to the bucket.
- Each viewer user's Google account needs read access (see [Access control](#access-control)).
- The report names must stay `daily-report-<portfolio>-llm-generated.html` and
  `news-<site>-<portfolio>-llm-generated.html` (see [Tab grouping](#tab-grouping)).

If the pipeline hasn't run, the viewer signs in fine but shows no reports. Check the bucket with
`gcloud storage ls gs://<bucket>/<prefix>*/`.

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
   │          /favicon.svg                  static/favicon.svg, the browser-tab icon (public)
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
| [static/favicon.svg](static/favicon.svg) | The browser-tab icon (a blue square with a rising bar chart)       |

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

### Docker

[Dockerfile](Dockerfile) builds a standard-library-only image that runs as an unprivileged user and holds no
secrets. Its header comment has the full build, run and test commands. In short:

```bash
docker build --pull -t us-central1-docker.pkg.dev/todo-ae9c2/googlecloud-fr/report-viewer:1.0.0 .
docker run -d --name report-viewer --restart unless-stopped --read-only --cap-drop ALL \
  --security-opt no-new-privileges -p 127.0.0.1:8081:8081 \
  -v /etc/report-viewer/client_secret.json:/run/secrets/client_secret.json:ro \
  us-central1-docker.pkg.dev/todo-ae9c2/googlecloud-fr/report-viewer:1.0.0
```

- **Port:** the image listens on `8081` (`PORT`), and `-p 127.0.0.1:` keeps it reachable from the host only.
- **OAuth client:** mounted read-only at run time, never copied into the image.
- **Public address:** a TLS reverse proxy on the host (e.g. nginx) serves the public `https://` address. The
  production deployment is `https://services.googlecloud.fr/`.
- **Pushing:** pushing to Artifact Registry uses the gcloud credential helper (`gcloud auth configure-docker
  us-central1-docker.pkg.dev`). It uses the *active* gcloud configuration, so pick one with
  `CLOUDSDK_ACTIVE_CONFIG_NAME=<name> docker push ...`.
- **zlib upgrade:** the Dockerfile upgrades `zlib1g` for a security fix the base image lacks. Remove that line
  once an image scan of plain `python:3.12-slim` no longer reports it.

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
  host values are rejected. Expose the viewer only through the proxy, so those headers come from it. The proxy
  must also **set** `X-Forwarded-Host` itself (nginx: `proxy_set_header X-Forwarded-Host $host;`) rather than
  pass on the client's. Otherwise a client can make the viewer build a redirect URI for any host. Google refuses it
  unless that URI is authorized, but that leaves the OAuth client's redirect list as the only check.
- **HTTPS**: over `https://`, every response also carries
  `Strict-Transport-Security: max-age=31536000`.
- **Sessions**: they are in memory only, so restarting the server signs everyone out.

## Tests

```bash
cd report_viewer
python3 -m unittest -v test_report_viewer.py     # or: python -m pytest -v test_report_viewer.py
```

Cloud Storage and Google's OAuth endpoints are faked. The tests cover:

- the tab grouping, and skipping unsafe or out-of-layout object names
- 401 for visitors who aren't signed in, and for forged or expired sessions
- Cloud Storage's 403 being passed through, and a rejected token ending the session
- the user's own token being used for every Cloud Storage call
- the sign-in flow: state binding, single-use state, required scope, the redirect URI kept per sign-in
- sign-in at any address, reverse-proxy headers, malformed hosts, and `PUBLIC_BASE_URL` pinning
- the security headers, the page and report CSPs, escaping of reflected input, HSTS and `Secure` cookies over HTTPS
- sign-out (POST only, revokes the token)
- slow and idle clients, the pending sign-in cap, and session purging
- the OAuth client configuration and the port fallback

The tab layout in `static/index.html` has no automated tests. Check it in a browser at desktop, tablet and phone
widths.

## Possible next steps

- Per-client access: map each signed-in Google account to its own bucket and prefix (a JSON file mounted at run
  time, deny by default), with Cloud Storage IAM granting each client read access to their bucket only.
- Optionally deploy to Cloud Run behind Identity-Aware Proxy instead of the VM with nginx.
- Auto-refresh the list during market hours (the pipeline re-uploads reports continuously).
- Show a "new since last viewed" marker on tabs whose report was re-uploaded.
