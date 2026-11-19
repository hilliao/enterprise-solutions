#!/usr/bin/env python3
"""
Report Viewer (beta): a web UI that shows the HTML portfolio reports in Cloud Storage in tabs.

Purpose:
  The report pipeline (portfolio_reports/ollama_report_pipeline/run-market-hours.sh) uploads the HTML reports to
  gs://$GCS_BUCKET/$GCS_PREFIX<portfolio>/, one folder per portfolio. This server shows them in one page: a tab per portfolio, a sub-tab per report
  (see report_catalog.py), each with a link to its authenticated storage.cloud.google.com URL.

Security model:
  - Visitors sign in with their Google account (google_sign_in.py). The server calls Cloud Storage with that
    visitor's own access token (cloud_storage.py) and has no credentials of its own, so Cloud Storage IAM decides
    access, the same check storage.cloud.google.com makes:
        not signed in (e.g. a private window)       -> 401, with a "Sign in with Google" prompt
        signed in, account has no access to bucket  -> 403 from Cloud Storage
        signed in, account can read the bucket      -> the reports
  - The page itself (/) holds no report data and is public; /api/reports and /reports/* need a session.
  - The server can't start without an OAuth client, so it never runs unauthenticated.
  - Reports are served with a restrictive Content-Security-Policy (no scripts, no outbound requests) into a
    sandboxed iframe.

Routes:
  GET  /                            the tab UI (static/index.html)
  GET  /favicon.svg                 the browser-tab icon (static/favicon.svg)
  GET  /api/reports                 JSON: signed-in user and the reports grouped into tabs
  GET  /reports/<portfolio>/<file>  one report's HTML
  GET  /auth/login                  starts Google sign-in
  GET  /auth/callback               Google's redirect back (the OAuth client's authorized redirect URI)
  POST /auth/logout                 ends the session and revokes its token

Requirements:
  Python 3.10+, standard library only (no pip install). An OAuth 2.0 "Web application" client; see README.md.

Configuration (environment variables):
  OAUTH_CLIENT_FILE   OAuth client JSON downloaded from the Google Cloud console, or else
  OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET, or else the file google_sign_in.DEFAULT_OAUTH_CLIENT_FILE
  (/home/hil/Encfs/confidential/secrets/client_secret_603410815034-....json)
  PUBLIC_BASE_URL     optional; pins the one address sign-in works at. Unset (the default), sign-in works at
                      whatever address the browser used: the Host header (or X-Forwarded-Host from a reverse
                      proxy), with https when X-Forwarded-Proto is https. Either way, <address>/auth/callback must be
                      an authorized redirect URI of the OAuth client; Google allows plain http only for localhost.
  GCS_BUCKET          default hil-financial-services-smart-invest
  GCS_PREFIX          default reports/
  HOST                listen address, default 0.0.0.0 (all interfaces); 127.0.0.1 for this machine only
  PORT                listen port; unset: port 80, or 8080 if 80 can't be bound

Usage:
  python3 report_viewer.py                                   # OAuth client from the default file
  OAUTH_CLIENT_FILE=/path/to/client_secret.json python3 report_viewer.py
  python3 -m unittest -v test_report_viewer.py
"""
import base64
import hashlib
import http.cookies
import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cloud_storage import CloudStorage, CloudStorageError
from google_sign_in import REDIRECT_PATH, GoogleSignIn, OAuthClient, SessionStore, SignedInUser, SignInError
from report_catalog import group_reports, is_safe_report_path

INDEX_HTML = Path(__file__).resolve().parent / 'static' / 'index.html'
# The browser-tab icon. Public like the page; an SVG, so it gets a CSP that blocks any script in it.
FAVICON_SVG = INDEX_HTML.with_name('favicon.svg')
FAVICON_CSP = "default-src 'none'; style-src 'unsafe-inline'"
SESSION_COOKIE = 'report_viewer_session'
SIGN_IN_STATE_COOKIE = 'report_viewer_sign_in_state'

# Browser hardening for every response; the page and the reports add their own Content-Security-Policy.
COMMON_HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',  # links leaving a report don't reveal report names
}
# The page's only script is its inline <script>, allowed by its SHA-256 hash (see index_csp), so injected markup
# can't run scripts.
INDEX_CSP_TEMPLATE = ("default-src 'self'; script-src {script_hashes}; style-src 'unsafe-inline'; frame-src 'self'; "
                      "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
# The pandoc reports are static: inline CSS only; no scripts, fetches, forms or remote images; framed only by the
# viewer. Reports contain LLM output and news text, and pandoc passes raw HTML through, so this is what keeps
# injected markup inert.
REPORT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; "
              "frame-ancestors 'self'; base-uri 'none'")
# Sent over HTTPS only (an https:// PUBLIC_BASE_URL, or X-Forwarded-Proto: https from the proxy): browsers then
# refuse plain HTTP to this host for a year.
HSTS = 'max-age=31536000'
# A Host or X-Forwarded-Host value the viewer accepts: a DNS name, IPv4 or [IPv6] address, with an optional port.
SAFE_HOST = re.compile(r'^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\])(?::[0-9]{1,5})?$')
# Seconds a connection may sit idle or send a request slowly before it is closed. Without it, a client that never
# finishes its request (slowloris) holds a server thread forever.
REQUEST_TIMEOUT_SECONDS = 30
_SCRIPT = re.compile(rb'<script>(.*?)</script>', re.DOTALL)


def index_csp(page: bytes) -> str:
    """INDEX_CSP_TEMPLATE with the SHA-256 hash of every inline <script> in page."""
    hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(script).digest()).decode()}'"
              for script in _SCRIPT.findall(page)]
    return INDEX_CSP_TEMPLATE.format(script_hashes=' '.join(hashes) or "'none'")


@dataclass(frozen=True)
class Config:
    bucket: str
    prefix: str
    host: str
    ports: tuple[int, ...]
    public_base_url: str | None  # None: the address of each request

    @classmethod
    def from_env(cls) -> 'Config':
        return cls(
            bucket=os.environ.get('GCS_BUCKET', 'hil-financial-services-smart-invest'),
            prefix=os.environ.get('GCS_PREFIX', 'reports/'),
            host=os.environ.get('HOST', '0.0.0.0'),
            # Port 80 needs root or CAP_NET_BIND_SERVICE on Linux; see README.md.
            ports=(int(os.environ['PORT']),) if os.environ.get('PORT') else (80, 8080),
            public_base_url=os.environ.get('PUBLIC_BASE_URL', '').rstrip('/') or None,
        )


@dataclass
class App:
    """What the request handler needs; set on ReportViewerHandler.app before serving."""
    bucket: str
    prefix: str
    public_base_url: str | None  # None: the address of each request (see ReportViewerHandler._base_url)
    storage: CloudStorage
    sign_in: GoogleSignIn
    sessions: SessionStore


class ReportViewerHandler(BaseHTTPRequestHandler):
    app: App = None
    server_version = 'ReportViewer/beta'
    sys_version = ''
    timeout = REQUEST_TIMEOUT_SECONDS  # socket timeout of each connection (BaseHTTPRequestHandler)

    # ---- routing ---------------------------------------------------------------------------------------------

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path in ('/', '/index.html'):
            page = INDEX_HTML.read_bytes()
            self._send(HTTPStatus.OK, 'text/html; charset=utf-8', page, {'Content-Security-Policy': index_csp(page)})
        elif url.path == '/favicon.svg':
            self._send(HTTPStatus.OK, 'image/svg+xml', FAVICON_SVG.read_bytes(), {'Content-Security-Policy': FAVICON_CSP})
        elif url.path == '/api/reports':
            self._get_report_list()
        elif url.path.startswith('/reports/'):
            self._get_report(urllib.parse.unquote(url.path.removeprefix('/reports/')))
        elif url.path == '/auth/login':
            self._start_sign_in()
        elif url.path == REDIRECT_PATH:
            self._finish_sign_in(urllib.parse.parse_qs(url.query))
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {'error': f'Not found: {url.path}'})

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path == '/auth/logout':
            self._sign_out()
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {'error': 'Not found'})

    # ---- reports (signed-in users only) ----------------------------------------------------------------------

    def _get_report_list(self):
        user = self._signed_in_user()
        if not user:
            self._send_json(HTTPStatus.UNAUTHORIZED,
                            {'error': 'Sign in with Google to view the reports.', 'sign_in_url': '/auth/login'})
            return
        try:
            objects = self.app.storage.list_html_objects(user.access_token)
        except CloudStorageError as error:
            self._send_storage_error_json(error, user)
            return
        self._send_json(HTTPStatus.OK, {'bucket': self.app.bucket, 'prefix': self.app.prefix, 'user': user.email,
                                        'groups': group_reports(objects, self.app.bucket, self.app.prefix)})

    def _get_report(self, path: str):
        """path is <portfolio>/<file>.html under the bucket prefix."""
        user = self._signed_in_user()
        if not user:
            self._send_message_page(HTTPStatus.UNAUTHORIZED, 'Sign in required',
                                    'Your session has ended or you are not signed in.', sign_in_link=True)
            return
        if not is_safe_report_path(path):
            self._send_message_page(HTTPStatus.BAD_REQUEST, 'Invalid report name', path)
            return
        try:
            content = self.app.storage.download(path, user.access_token)
        except CloudStorageError as error:
            status, message = self._storage_error_message(error, user)
            self._send_message_page(status, 'Report unavailable', message,
                                    sign_in_link=status == HTTPStatus.UNAUTHORIZED)
            return
        self._send(HTTPStatus.OK, 'text/html; charset=utf-8', content, {'Content-Security-Policy': REPORT_CSP})

    def _send_storage_error_json(self, error: CloudStorageError, user: SignedInUser):
        status, message = self._storage_error_message(error, user)
        self._send_json(status, {'error': message, 'user': user.email,
                                 **({'sign_in_url': '/auth/login'} if status == HTTPStatus.UNAUTHORIZED else {})})

    def _storage_error_message(self, error: CloudStorageError, user: SignedInUser) -> tuple[int, str]:
        """Maps a Cloud Storage failure to the status and message shown to the user."""
        location = f'gs://{self.app.bucket}/{self.app.prefix}'
        if error.status == HTTPStatus.UNAUTHORIZED:  # token revoked or expired early
            self.app.sessions.delete(self._cookie(SESSION_COOKIE))
            return HTTPStatus.UNAUTHORIZED, 'Your Google session is no longer valid. Sign in again.'
        if error.status == HTTPStatus.FORBIDDEN:
            return HTTPStatus.FORBIDDEN, f'{user.email} has no read access to {location}.'
        if error.status == HTTPStatus.NOT_FOUND:
            return HTTPStatus.NOT_FOUND, f'Not found in {location}.'
        self.log_error('Cloud Storage error: %s', error)
        return HTTPStatus.BAD_GATEWAY, f'Cloud Storage error: {error}'

    # ---- Google sign-in --------------------------------------------------------------------------------------

    def _base_url(self) -> str | None:
        """
        The address the browser used, e.g. https://services.example: PUBLIC_BASE_URL when set, else the request's
        X-Forwarded-Host or Host, with the scheme from X-Forwarded-Proto (http without it). None for a malformed host.
        A forged header can't redirect a sign-in elsewhere: Google only returns to authorized redirect URIs, and the
        sign-in's state cookie stays on the host the browser really used.
        """
        if self.app.public_base_url:
            return self.app.public_base_url
        host = self._first_header_value('X-Forwarded-Host') or self.headers.get('Host', '').strip()
        if not SAFE_HOST.match(host):
            return None
        scheme = 'https' if self._first_header_value('X-Forwarded-Proto').lower() == 'https' else 'http'
        return f'{scheme}://{host}'

    def _first_header_value(self, name: str) -> str:
        """First entry of a comma-separated header such as X-Forwarded-Host (one per proxy hop); '' if absent."""
        return self.headers.get(name, '').split(',')[0].strip()

    def _is_https(self) -> bool:
        return (self._base_url() or '').startswith('https://')

    def _start_sign_in(self):
        base_url = self._base_url()
        if base_url is None:
            self._send_message_page(HTTPStatus.BAD_REQUEST, 'Sign-in failed', 'The request has no valid Host header.')
            return
        # With PUBLIC_BASE_URL set, the state cookie must land on that host, where Google's redirect returns.
        public_host = urllib.parse.urlsplit(base_url).netloc
        if self.app.public_base_url and self.headers.get('Host', '') != public_host:
            self._send_message_page(
                HTTPStatus.BAD_REQUEST, 'Open the viewer at its sign-in address',
                f'Google sign-in only works at {base_url} (PUBLIC_BASE_URL). Open that address, or unset '
                'PUBLIC_BASE_URL to allow any address.', link=(base_url + '/', 'Open the viewer'))
            return
        consent_url, state = self.app.sign_in.start(redirect_uri=base_url + REDIRECT_PATH)
        self._redirect(consent_url, cookies=[self._cookie_header(SIGN_IN_STATE_COOKIE, state, path='/auth',
                                                                 max_age=10 * 60)])

    def _finish_sign_in(self, query: dict[str, list[str]]):
        clear_state = self._cookie_header(SIGN_IN_STATE_COOKIE, '', path='/auth', max_age=0)
        if 'error' in query:  # e.g. access_denied when the user cancels
            self._send_message_page(HTTPStatus.UNAUTHORIZED, 'Sign-in cancelled',
                                    f'Google returned: {query["error"][0]}', sign_in_link=True, cookies=[clear_state])
            return
        try:
            user = self.app.sign_in.finish(query_state=query.get('state', [''])[0],
                                           cookie_state=self._cookie(SIGN_IN_STATE_COOKIE),
                                           code=query.get('code', [''])[0])
        except SignInError as error:
            self._send_message_page(HTTPStatus.BAD_REQUEST, 'Sign-in failed', str(error), sign_in_link=True,
                                    cookies=[clear_state])
            return
        self.app.sessions.delete(self._cookie(SESSION_COOKIE))  # never reuse a session ID across sign-ins
        session_id = self.app.sessions.create(user)
        self.log_message('signed in: %s', user.email)
        self._redirect('/', cookies=[clear_state, self._cookie_header(SESSION_COOKIE, session_id)])

    def _sign_out(self):
        # SameSite=Lax keeps the session cookie off cross-site POSTs, so other sites can't sign the user out.
        user = self.app.sessions.delete(self._cookie(SESSION_COOKIE))
        if user:
            self.app.sign_in.revoke(user.access_token)
        self._redirect('/', status=HTTPStatus.SEE_OTHER,
                       cookies=[self._cookie_header(SESSION_COOKIE, '', max_age=0)])

    def _signed_in_user(self) -> SignedInUser | None:
        return self.app.sessions.get(self._cookie(SESSION_COOKIE))

    # ---- cookies and responses -------------------------------------------------------------------------------

    def _cookie(self, name: str) -> str | None:
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except http.cookies.CookieError:
            return None
        return cookies[name].value if name in cookies else None

    def _cookie_header(self, name: str, value: str, path: str = '/', max_age: int | None = None) -> str:
        attributes = [f'{name}={value}', f'Path={path}', 'HttpOnly', 'SameSite=Lax']
        if max_age is not None:
            attributes.append(f'Max-Age={max_age}')
        if self._is_https():
            attributes.append('Secure')
        return '; '.join(attributes)

    def _redirect(self, location: str, status: int = HTTPStatus.FOUND, cookies: list[str] = ()):
        self.send_response(status)
        self.send_header('Location', location)
        for cookie in cookies:
            self.send_header('Set-Cookie', cookie)
        self._send_common_headers()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _send_message_page(self, status: int, title: str, message: str, sign_in_link: bool = False,
                           link: tuple[str, str] | None = None, cookies: list[str] = ()):
        """A small HTML page for errors; it may show inside the viewer's iframe, so links target the top window."""
        if sign_in_link:
            link = ('/auth/login', 'Sign in with Google')
        link_html = f'<p><a href="{escape(link[0])}" target="_top">{escape(link[1])}</a></p>' if link else ''
        body = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
                '<meta name="viewport" content="width=device-width, initial-scale=1"><style>'
                'body{font:15px/1.5 system-ui,sans-serif;margin:48px auto;max-width:36em;padding:0 16px;'
                'color:#1d2330;background:#fff}a{color:#1a5fb4}'
                '@media (prefers-color-scheme:dark){body{color:#e4e7ec;background:#1c2027}a{color:#7fb0ff}}'
                f'</style></head><body><h1>{escape(title)}</h1><p>{escape(message)}</p>{link_html}</body></html>')
        self._send(status, 'text/html; charset=utf-8', body.encode(), {'Content-Security-Policy': REPORT_CSP},
                   cookies)

    def _send_common_headers(self):
        for name, value in COMMON_HEADERS.items():
            self.send_header(name, value)
        if self._is_https():
            self.send_header('Strict-Transport-Security', HSTS)

    def _send_json(self, status: int, payload: dict):
        self._send(status, 'application/json', json.dumps(payload).encode())

    def _send(self, status: int, content_type: str, body: bytes, headers: dict | None = None,
              cookies: list[str] = ()):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self._send_common_headers()
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        for cookie in cookies:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)


def bind_server(host: str, ports: tuple[int, ...]) -> ThreadingHTTPServer:
    """A server bound to the first of ports that can be bound; raises the last port's OSError if none can."""
    for index, port in enumerate(ports):
        try:
            return ThreadingHTTPServer((host, port), ReportViewerHandler)
        except OSError as error:  # PermissionError for a privileged port, EADDRINUSE if it's taken
            if index == len(ports) - 1:
                raise
            print(f'Cannot listen on {host}:{port} ({error.strerror}); trying port {ports[index + 1]}',
                  file=sys.stderr)
    raise ValueError('no port to bind')


def main():
    config = Config.from_env()
    try:
        oauth_client = OAuthClient.from_env()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f'ERROR: {error}. The viewer only runs with Google sign-in.')
    try:
        server = bind_server(config.host, config.ports)
    except OSError as error:
        sys.exit(f'ERROR: cannot listen on {config.host}:{config.ports[-1]} ({error.strerror}). Stop the process '
                 'using it (`ss -ltnp | grep <port>`) or pick another one with PORT=<port>.')

    port = server.server_address[1]
    ReportViewerHandler.app = App(
        bucket=config.bucket, prefix=config.prefix, public_base_url=config.public_base_url,
        storage=CloudStorage(config.bucket, config.prefix), sign_in=GoogleSignIn(oauth_client),
        sessions=SessionStore())

    local_url = f'http://localhost{"" if port == 80 else f":{port}"}'
    open_url = config.public_base_url or local_url
    redirect_uris = (f'{config.public_base_url}{REDIRECT_PATH}' if config.public_base_url else
                     f'<address in the browser>{REDIRECT_PATH}, e.g. {local_url}{REDIRECT_PATH}')
    print(f'Report Viewer (beta) for gs://{config.bucket}/{config.prefix}<portfolio>/*.html\n'
          f'  listening on {config.host}:{port}; open {open_url}/\n'
          f'  OAuth redirect URI (must be authorized on the client): {redirect_uris}',
          file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
