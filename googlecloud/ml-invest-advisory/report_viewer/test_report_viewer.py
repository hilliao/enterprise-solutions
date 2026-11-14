"""
Unit tests for the report viewer (beta): report grouping, access control, Google sign-in, and security hardening
(response headers and CSP, escaping of reflected input, slow clients, memory bounds). Cloud Storage and
Google's OAuth endpoints are faked; standard library only:

    python3 -m unittest -v test_report_viewer.py     # or: python -m pytest -v test_report_viewer.py
"""
import base64
import hashlib
import http.client
import json
import os
import re
import socket
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from unittest import mock

import google_sign_in
import report_viewer
from cloud_storage import CloudStorageError
from google_sign_in import GoogleSignIn, OAuthClient, SessionStore, SignedInUser, SignInError
from report_catalog import group_reports

BUCKET, PREFIX = 'test-bucket', 'reports/'
UPDATED = '2026-11-13T23:25:26.000Z'
USER_TOKEN = 'user-access-token'
DAILY_YANG = 'yang/daily-report-yang-llm-generated.html'


def gcs_object(path: str) -> dict:
    return {'name': PREFIX + path, 'updated': UPDATED, 'size': '1024'}


def labels(group: dict) -> list[str]:
    return [report['label'] for report in group['reports']]


class GroupReportsTest(unittest.TestCase):
    def test_groups_by_portfolio_folder_with_daily_report_first(self):
        paths = ['vicky-tw-portfolio/news-wsj-vicky-tw-portfolio-llm-generated.html',
                 'vicky/news-fundstrat-daily-technical-vicky-llm-generated.html',
                 'vicky/daily-report-vicky-llm-generated.html',
                 'vicky-tw-portfolio/daily-report-vicky-tw-portfolio-llm-generated.html',
                 'vicky-tw-portfolio/news-cnbc-vicky-tw-portfolio-llm-generated.html',
                 'vicky/news-cnbc-vicky-llm-generated.html']
        groups = group_reports([gcs_object(path) for path in paths], BUCKET, PREFIX)

        self.assertEqual(['vicky', 'vicky-tw-portfolio'], [group['portfolio'] for group in groups])
        self.assertEqual(['Daily report', 'News · CNBC', 'News · Fundstrat daily technical'], labels(groups[0]))
        self.assertEqual(['Daily report', 'News · CNBC', 'News · WSJ'], labels(groups[1]))

    def test_site_is_read_between_news_and_the_folder_portfolio(self):
        groups = group_reports([gcs_object('hil-michelle-portfolio-1/'
                                           'news-global-headlines-hil-michelle-portfolio-1-llm-generated.html')],
                               BUCKET, PREFIX)

        report = groups[0]['reports'][0]
        self.assertEqual(('hil-michelle-portfolio-1', 'news', 'global-headlines'),
                         (report['portfolio'], report['use_case'], report['site']))
        self.assertEqual('News · Global headlines', report['label'])

    def test_unknown_names_in_a_folder_come_last_labelled_by_file_name(self):
        groups = group_reports([gcs_object('yang/summary.html'), gcs_object(DAILY_YANG),
                                gcs_object('yang/news-cnbc-vicky-llm-generated.html')], BUCKET, PREFIX)

        self.assertEqual(['Daily report', 'news-cnbc-vicky-llm-generated', 'summary'], labels(groups[0]))

    def test_report_fields_and_authenticated_url(self):
        report = group_reports([gcs_object(DAILY_YANG)], BUCKET, PREFIX)[0]['reports'][0]

        self.assertEqual({'file': DAILY_YANG, 'portfolio': 'yang', 'use_case': 'daily-report', 'site': '',
                          'label': 'Daily report', 'updated': UPDATED, 'size': 1024,
                          'auth_url': f'https://storage.cloud.google.com/{BUCKET}/{PREFIX}{DAILY_YANG}'}, report)

    def test_skips_flat_layout_nested_folders_and_unsafe_names(self):
        paths = ['daily-report-yang-llm-generated.html',  # old layout: directly under the prefix
                 'yang/old/daily-report-yang-llm-generated.html', 'yang/bad name.html', '../yang/x.html',
                 'yang/../x.html', '.hidden/x.html', 'yang/.x.html']
        self.assertEqual([], group_reports([gcs_object(path) for path in paths], BUCKET, PREFIX))

    def test_skips_objects_outside_the_prefix(self):
        self.assertEqual([], group_reports([{'name': 'other/yang/x.html'}], BUCKET, PREFIX))


class FakeStorage:
    """Cloud Storage that records the access token of every call and fails with `error_status` if set."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.tokens_used = []
        self.error_status = None

    def list_html_objects(self, access_token):
        self._check(access_token)
        return [gcs_object(name) for name in self.files]

    def download(self, path, access_token):
        self._check(access_token)
        if path not in self.files:
            raise CloudStorageError(404, 'Cloud Storage returned HTTP 404')
        return self.files[path]

    def _check(self, access_token):
        self.tokens_used.append(access_token)
        if self.error_status:
            raise CloudStorageError(self.error_status, f'Cloud Storage returned HTTP {self.error_status}')


def id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({'email': email}).encode()).rstrip(b'=').decode()
    return f'header.{payload}.signature'


class ViewerHttpTest(unittest.TestCase):
    """Runs the real handler on a local port with fake Cloud Storage and a fake Google token endpoint."""

    def setUp(self):
        self.storage = FakeStorage({DAILY_YANG: b'<h1>Yang</h1>'})
        self.sessions = SessionStore()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), report_viewer.ReportViewerHandler)
        self.port = self.httpd.server_address[1]
        self.base_url = f'http://localhost:{self.port}'
        self.sign_in = GoogleSignIn(OAuthClient('client-id', 'client-secret'))
        report_viewer.ReportViewerHandler.app = report_viewer.App(
            bucket=BUCKET, prefix=PREFIX, public_base_url=None, storage=self.storage,
            sign_in=self.sign_in, sessions=self.sessions)
        report_viewer.ReportViewerHandler.log_message = lambda *args: None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method: str, path: str, cookie: str | None = None, host: str | None = None,
                extra_headers: dict | None = None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        headers = {'Host': host or f'localhost:{self.port}', **(extra_headers or {})}
        if cookie:
            headers['Cookie'] = cookie
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def signed_in_cookie(self, email='hil@example.com', expires_in=3600) -> str:
        session_id = self.sessions.create(SignedInUser(email, USER_TOKEN, time.time() + expires_in))
        return f'{report_viewer.SESSION_COOKIE}={session_id}'

    # ---- not signed in, e.g. a private browsing window ---------------------------------------------------------

    def test_page_itself_is_public_and_holds_no_report_data(self):
        response, body = self.request('GET', '/')
        self.assertEqual(200, response.status)
        self.assertIn(b'<title>Portfolio Reports</title>', body)
        self.assertNotIn(b'Yang', body)
        self.assertEqual([], self.storage.tokens_used)

    def test_report_list_requires_sign_in(self):
        response, body = self.request('GET', '/api/reports')
        self.assertEqual(401, response.status)
        self.assertEqual('/auth/login', json.loads(body)['sign_in_url'])
        self.assertEqual([], self.storage.tokens_used)

    def test_report_requires_sign_in(self):
        response, body = self.request('GET', f'/reports/{DAILY_YANG}')
        self.assertEqual(401, response.status)
        self.assertNotIn(b'Yang</h1>', body)
        self.assertEqual([], self.storage.tokens_used)

    def test_unknown_or_forged_session_is_rejected(self):
        response, _ = self.request('GET', f'/reports/{DAILY_YANG}', cookie=f'{report_viewer.SESSION_COOKIE}=forged')
        self.assertEqual(401, response.status)

    def test_expired_session_is_rejected(self):
        response, _ = self.request('GET', '/api/reports', cookie=self.signed_in_cookie(expires_in=-1))
        self.assertEqual(401, response.status)

    # ---- signed in -------------------------------------------------------------------------------------------

    def test_signed_in_user_gets_reports_with_their_own_token(self):
        cookie = self.signed_in_cookie()
        response, body = self.request('GET', '/api/reports', cookie=cookie)
        self.assertEqual(200, response.status)
        self.assertEqual('hil@example.com', json.loads(body)['user'])
        self.assertEqual('yang', json.loads(body)['groups'][0]['portfolio'])

        response, body = self.request('GET', f'/reports/{DAILY_YANG}', cookie=cookie)
        self.assertEqual(200, response.status)
        self.assertEqual(b'<h1>Yang</h1>', body)
        self.assertIn("default-src 'none'", response.getheader('Content-Security-Policy'))
        self.assertEqual([USER_TOKEN, USER_TOKEN], self.storage.tokens_used)

    def test_account_without_bucket_access_gets_403(self):
        self.storage.error_status = 403
        cookie = self.signed_in_cookie(email='stranger@example.com')

        response, body = self.request('GET', '/api/reports', cookie=cookie)
        self.assertEqual(403, response.status)
        self.assertIn('stranger@example.com has no read access', json.loads(body)['error'])
        response, _ = self.request('GET', f'/reports/{DAILY_YANG}', cookie=cookie)
        self.assertEqual(403, response.status)

    def test_token_rejected_by_cloud_storage_ends_the_session(self):
        self.storage.error_status = 401
        cookie = self.signed_in_cookie()
        self.assertEqual(401, self.request('GET', '/api/reports', cookie=cookie)[0].status)

        self.storage.error_status = None
        self.assertEqual(401, self.request('GET', '/api/reports', cookie=cookie)[0].status)

    def test_missing_report_is_404(self):
        response, _ = self.request('GET', '/reports/yang/missing.html', cookie=self.signed_in_cookie())
        self.assertEqual(404, response.status)

    def test_traversal_and_paths_outside_a_portfolio_folder_are_rejected(self):
        cookie = self.signed_in_cookie()
        for path in ('/reports/..%2Fsecret.html', '/reports/yang/..%2F..%2Fsecret.html', '/reports/yang%2F..%2Fx.html',
                     '/reports/daily-report-yang-llm-generated.html', '/reports/yang/old/x.html'):
            with self.subTest(path=path):
                self.assertEqual(400, self.request('GET', path, cookie=cookie)[0].status)
        self.assertEqual([], self.storage.tokens_used)

    # ---- Google sign-in --------------------------------------------------------------------------------------

    def start_sign_in(self) -> tuple[str, str]:
        """Returns (state from Google's consent URL, the state cookie header)."""
        response, _ = self.request('GET', '/auth/login')
        self.assertEqual(302, response.status)
        consent = urllib.parse.urlsplit(response.getheader('Location'))
        self.assertEqual('accounts.google.com', consent.netloc)
        params = urllib.parse.parse_qs(consent.query)
        self.assertEqual([self.base_url + '/auth/callback'], params['redirect_uri'])
        self.assertIn('https://www.googleapis.com/auth/devstorage.read_only', params['scope'][0])
        self.assertEqual(['S256'], params['code_challenge_method'])
        state_cookie = response.getheader('Set-Cookie').split(';')[0]
        self.assertIn('HttpOnly', response.getheader('Set-Cookie'))
        return params['state'][0], state_cookie

    def test_sign_in_creates_a_session_used_for_the_reports(self):
        state, state_cookie = self.start_sign_in()
        token = {'access_token': 'fresh-token', 'expires_in': 3599, 'id_token': id_token('hil@example.com'),
                 'scope': 'openid https://www.googleapis.com/auth/userinfo.email '
                          'https://www.googleapis.com/auth/devstorage.read_only'}
        with mock.patch.object(GoogleSignIn, '_exchange_code', return_value=token) as exchange:
            response, _ = self.request('GET', f'/auth/callback?state={state}&code=auth-code', cookie=state_cookie)
        self.assertEqual(302, response.status)
        self.assertEqual('auth-code', exchange.call_args.args[0])
        session_cookie = next(cookie for cookie in response.msg.get_all('Set-Cookie')
                              if cookie.startswith(report_viewer.SESSION_COOKIE + '=') and 'Max-Age=0' not in cookie)
        self.assertIn('HttpOnly', session_cookie)
        self.assertIn('SameSite=Lax', session_cookie)

        response, body = self.request('GET', '/api/reports', cookie=session_cookie.split(';')[0])
        self.assertEqual(200, response.status)
        self.assertEqual('hil@example.com', json.loads(body)['user'])
        self.assertEqual(['fresh-token'], self.storage.tokens_used)

    def test_callback_without_the_browsers_state_cookie_is_rejected(self):
        state, _ = self.start_sign_in()
        with mock.patch.object(GoogleSignIn, '_exchange_code') as exchange:
            response, _ = self.request('GET', f'/auth/callback?state={state}&code=auth-code')
        self.assertEqual(400, response.status)
        exchange.assert_not_called()

    def test_callback_state_is_single_use(self):
        state, state_cookie = self.start_sign_in()
        token = {'access_token': 't', 'id_token': id_token('a@example.com'),
                 'scope': 'openid email https://www.googleapis.com/auth/devstorage.read_only'}
        with mock.patch.object(GoogleSignIn, '_exchange_code', return_value=token):
            self.request('GET', f'/auth/callback?state={state}&code=c', cookie=state_cookie)
            response, _ = self.request('GET', f'/auth/callback?state={state}&code=c', cookie=state_cookie)
        self.assertEqual(400, response.status)

    def test_sign_in_without_storage_scope_is_rejected(self):
        state, state_cookie = self.start_sign_in()
        token = {'access_token': 't', 'id_token': id_token('a@example.com'), 'scope': 'openid email'}
        with mock.patch.object(GoogleSignIn, '_exchange_code', return_value=token):
            response, _ = self.request('GET', f'/auth/callback?state={state}&code=c', cookie=state_cookie)
        self.assertEqual(400, response.status)
        self.assertNotIn(report_viewer.SESSION_COOKIE + '=',
                         ' '.join(c for c in response.msg.get_all('Set-Cookie') or [] if 'Max-Age=0' not in c))

    def test_sign_out_ends_the_session_and_revokes_the_token(self):
        cookie = self.signed_in_cookie()
        with mock.patch.object(GoogleSignIn, 'revoke') as revoke:
            response, _ = self.request('POST', '/auth/logout', cookie=cookie)
        self.assertEqual(303, response.status)
        revoke.assert_called_once_with(USER_TOKEN)
        self.assertEqual(401, self.request('GET', '/api/reports', cookie=cookie)[0].status)

    # ---- security hardening ----------------------------------------------------------------------------------

    def test_every_response_has_the_hardening_headers_and_no_cors(self):
        cookie = self.signed_in_cookie()
        for method, path, cookie_header in (('GET', '/', None), ('GET', '/api/reports', None),
                                            ('GET', '/api/reports', cookie), ('GET', f'/reports/{DAILY_YANG}', cookie),
                                            ('GET', '/auth/login', None), ('GET', '/nope', None),
                                            ('POST', '/auth/logout', None)):
            with self.subTest(method=method, path=path, signed_in=bool(cookie_header)):
                connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
                headers = {'Host': f'localhost:{self.port}', 'Origin': 'https://evil.example'}
                if cookie_header:
                    headers['Cookie'] = cookie_header
                connection.request(method, path, headers=headers)
                response = connection.getresponse()
                response.read()
                connection.close()
                self.assertEqual('no-store', response.getheader('Cache-Control'))
                self.assertEqual('nosniff', response.getheader('X-Content-Type-Options'))
                self.assertEqual('no-referrer', response.getheader('Referrer-Policy'))
                self.assertIsNone(response.getheader('Access-Control-Allow-Origin'))
                self.assertIsNone(response.getheader('Strict-Transport-Security'))  # plain http here

    def test_page_csp_allows_only_its_own_inline_script(self):
        response, body = self.request('GET', '/')
        csp = dict(directive.strip().split(' ', 1) for directive in response.getheader('Content-Security-Policy')
                   .split(';'))
        scripts = re.findall(rb'<script>(.*?)</script>', body, re.DOTALL)
        self.assertEqual(1, len(scripts))
        expected = "'sha256-" + base64.b64encode(hashlib.sha256(scripts[0]).digest()).decode() + "'"
        self.assertEqual(expected, csp['script-src'])
        self.assertEqual("'none'", csp['frame-ancestors'])
        self.assertEqual("'none'", csp['object-src'])
        self.assertEqual("'self'", csp['frame-src'])
        self.assertNotRegex(body.decode(), r'\son[a-z]+\s*=')  # inline event handlers would be blocked by the CSP

    def test_report_csp_blocks_scripts_forms_and_framing_by_other_sites(self):
        response, _ = self.request('GET', f'/reports/{DAILY_YANG}', cookie=self.signed_in_cookie())
        csp = response.getheader('Content-Security-Policy')
        for directive in ("default-src 'none'", "form-action 'none'", "frame-ancestors 'self'", "base-uri 'none'"):
            self.assertIn(directive, csp)
        self.assertNotIn('script-src', csp)  # falls back to default-src 'none'

    def test_reflected_input_is_escaped(self):
        payload = '<script>alert(1)</script>'
        response, body = self.request('GET', '/auth/callback?error=' + urllib.parse.quote(payload))
        self.assertEqual(401, response.status)
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;', body)
        self.assertNotIn(payload.encode(), body)

        response, body = self.request('GET', '/reports/yang/' + urllib.parse.quote('<img src=x onerror=alert(1)>.html'),
                                      cookie=self.signed_in_cookie())
        self.assertEqual(400, response.status)
        self.assertNotIn(b'<img', body)
        self.assertIn(b'&lt;img', body)

        response, body = self.request('GET', '/' + urllib.parse.quote(payload))
        self.assertEqual(404, response.status)
        self.assertEqual('application/json', response.getheader('Content-Type'))

    def test_only_get_and_post_are_served(self):
        for method in ('PUT', 'DELETE', 'PATCH', 'OPTIONS', 'TRACE', 'HEAD'):
            with self.subTest(method=method):
                self.assertEqual(501, self.request(method, '/api/reports', cookie=self.signed_in_cookie())[0].status)
        self.assertEqual(404, self.request('POST', '/api/reports')[0].status)

    def test_sign_out_needs_post_so_a_link_or_image_cant_trigger_it(self):
        cookie = self.signed_in_cookie()
        self.assertEqual(404, self.request('GET', '/auth/logout', cookie=cookie)[0].status)
        self.assertEqual(200, self.request('GET', '/api/reports', cookie=cookie)[0].status)

    def login_redirect_uri(self, **request_args) -> str:
        response, _ = self.request('GET', '/auth/login', **request_args)
        self.assertEqual(302, response.status)
        return urllib.parse.parse_qs(urllib.parse.urlsplit(response.getheader('Location')).query)['redirect_uri'][0]

    def test_sign_in_works_at_any_address_the_browser_used(self):
        self.assertEqual('http://services.example/auth/callback', self.login_redirect_uri(host='services.example'))
        self.assertEqual('http://10.0.0.5:8081/auth/callback', self.login_redirect_uri(host='10.0.0.5:8081'))

    def test_reverse_proxy_headers_give_the_public_https_address(self):
        response, _ = self.request('GET', '/auth/login', host='localhost:8081', extra_headers={
            'X-Forwarded-Host': 'services.example, proxy.internal', 'X-Forwarded-Proto': 'https'})
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(response.getheader('Location')).query)
        self.assertEqual(['https://services.example/auth/callback'], params['redirect_uri'])
        self.assertIn('Secure', response.getheader('Set-Cookie'))
        self.assertEqual('max-age=31536000', response.getheader('Strict-Transport-Security'))

    def test_callback_exchanges_the_code_with_the_redirect_uri_the_sign_in_started_with(self):
        response, _ = self.request('GET', '/auth/login', host='services.example',
                                   extra_headers={'X-Forwarded-Proto': 'https'})
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(response.getheader('Location')).query)['state'][0]
        state_cookie = response.getheader('Set-Cookie').split(';')[0]
        token = {'access_token': 't', 'id_token': id_token('hil@example.com'),
                 'scope': 'openid email https://www.googleapis.com/auth/devstorage.read_only'}
        with mock.patch.object(GoogleSignIn, '_exchange_code', return_value=token) as exchange:
            self.request('GET', f'/auth/callback?state={state}&code=c', cookie=state_cookie, host='other.example')
        self.assertEqual('https://services.example/auth/callback', exchange.call_args.kwargs['redirect_uri'])

    def test_malformed_host_is_rejected_at_sign_in(self):
        for host in ('evil.example/path', 'evil.example@x', 'a b', '"><script>'):
            with self.subTest(host=host):
                response, body = self.request('GET', '/auth/login', host=host)
                self.assertEqual(400, response.status)
                self.assertNotIn(b'<script>', body)
        response, _ = self.request('GET', '/auth/login', extra_headers={'X-Forwarded-Host': 'evil.example/x'})
        self.assertEqual(400, response.status)

    def test_public_base_url_pins_sign_in_to_one_address(self):
        self.httpd.RequestHandlerClass.app.public_base_url = 'https://services.example'
        self.assertEqual('https://services.example/auth/callback', self.login_redirect_uri(host='services.example'))
        response, body = self.request('GET', '/auth/login', host='other.example')
        self.assertEqual(400, response.status)
        self.assertIn(b'only works at https://services.example', body)

    def test_https_deployment_sends_hsts_and_secure_cookies(self):
        self.httpd.RequestHandlerClass.app.public_base_url = 'https://services.example'
        response, _ = self.request('GET', '/auth/login', host='services.example')
        self.assertEqual(302, response.status)
        self.assertEqual('max-age=31536000', response.getheader('Strict-Transport-Security'))
        self.assertIn('Secure', response.getheader('Set-Cookie'))
        self.assertEqual('max-age=31536000', self.request('GET', '/', host='services.example')[0]
                         .getheader('Strict-Transport-Security'))

    def test_slow_client_is_disconnected(self):
        with mock.patch.object(report_viewer.ReportViewerHandler, 'timeout', 1):
            with socket.create_connection(('127.0.0.1', self.port), timeout=10) as client:
                client.sendall(b'GET /api/reports HTTP/1.1\r\nHost: localhost')  # never finishes the request
                started = time.monotonic()
                self.assertEqual(b'', client.recv(100))  # the server closed the connection
                self.assertLess(time.monotonic() - started, 5)

    def test_server_closes_idle_connections_by_default(self):
        self.assertEqual(report_viewer.REQUEST_TIMEOUT_SECONDS, report_viewer.ReportViewerHandler.timeout)
        self.assertLessEqual(report_viewer.REQUEST_TIMEOUT_SECONDS, 60)


class SignInUnitTest(unittest.TestCase):
    def test_finish_requires_matching_state(self):
        sign_in = GoogleSignIn(OAuthClient('id', 'secret'))
        _, state = sign_in.start('http://localhost/auth/callback')
        with self.assertRaises(SignInError):
            sign_in.finish(query_state=state, cookie_state='other', code='c')


class MemoryBoundsTest(unittest.TestCase):
    """Unauthenticated requests must not be able to grow the server's memory without limit."""

    def test_pending_sign_ins_are_capped_dropping_the_oldest(self):
        sign_in = GoogleSignIn(OAuthClient('id', 'secret'))
        token = {'access_token': 't', 'id_token': id_token('a@example.com'),
                 'scope': 'openid email https://www.googleapis.com/auth/devstorage.read_only'}
        with mock.patch.object(google_sign_in, 'MAX_PENDING_SIGN_INS', 3):
            states = [sign_in.start('http://localhost/auth/callback')[1] for _ in range(5)]
        self.assertEqual(3, len(sign_in._pending))
        with self.assertRaisesRegex(SignInError, 'expired or was already used'):
            sign_in.finish(query_state=states[0], cookie_state=states[0], code='c')
        with mock.patch.object(GoogleSignIn, '_exchange_code', return_value=token):
            self.assertEqual('a@example.com', sign_in.finish(query_state=states[-1], cookie_state=states[-1],
                                                             code='c').email)

    def test_expired_sessions_are_purged_when_a_session_is_created(self):
        sessions = SessionStore()
        sessions.create(SignedInUser('old@example.com', 't1', time.time() - 1))
        current = sessions.create(SignedInUser('new@example.com', 't2', time.time() + 3600))
        self.assertEqual([current], list(sessions._sessions))


class OAuthClientConfigTest(unittest.TestCase):
    def setUp(self):  # never read the real default file in tests
        patcher = mock.patch('google_sign_in.DEFAULT_OAUTH_CLIENT_FILE', '/nonexistent/client_secret.json')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_client_is_an_error(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            OAuthClient.from_env()

    def test_default_file_is_used_when_nothing_is_set(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'web': {'client_id': 'default-id', 'client_secret': 'default-secret'}}, f)
        try:
            with mock.patch('google_sign_in.DEFAULT_OAUTH_CLIENT_FILE', f.name), \
                    mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(OAuthClient('default-id', 'default-secret'), OAuthClient.from_env())
                # ... but explicit environment variables win over it
                with mock.patch.dict(os.environ, {'OAUTH_CLIENT_ID': 'env-id', 'OAUTH_CLIENT_SECRET': 'env-secret'}):
                    self.assertEqual(OAuthClient('env-id', 'env-secret'), OAuthClient.from_env())
        finally:
            os.unlink(f.name)

    def test_reads_web_client_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'web': {'client_id': 'id', 'client_secret': 'secret'}}, f)
        try:
            with mock.patch.dict(os.environ, {'OAUTH_CLIENT_FILE': f.name}, clear=True):
                self.assertEqual(OAuthClient('id', 'secret'), OAuthClient.from_env())
        finally:
            os.unlink(f.name)

    def test_rejects_non_web_client_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'installed': {'client_id': 'id', 'client_secret': 'secret'}}, f)
        try:
            with mock.patch.dict(os.environ, {'OAUTH_CLIENT_FILE': f.name}, clear=True), \
                    self.assertRaises(ValueError):
                OAuthClient.from_env()
        finally:
            os.unlink(f.name)

    def test_server_refuses_to_start_without_sign_in(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit) as raised:
            report_viewer.main()
        self.assertIn('only runs with Google sign-in', str(raised.exception))


class BindServerTest(unittest.TestCase):
    def test_falls_back_to_next_port_when_first_is_taken(self):
        taken = ThreadingHTTPServer(('127.0.0.1', 0), report_viewer.ReportViewerHandler)
        free = ThreadingHTTPServer(('127.0.0.1', 0), report_viewer.ReportViewerHandler)
        free_port = free.server_address[1]
        free.server_close()
        try:
            bound = report_viewer.bind_server('127.0.0.1', (taken.server_address[1], free_port))
            self.assertEqual(free_port, bound.server_address[1])
            bound.server_close()
        finally:
            taken.server_close()

    def test_raises_when_no_port_can_be_bound(self):
        taken = ThreadingHTTPServer(('127.0.0.1', 0), report_viewer.ReportViewerHandler)
        try:
            with self.assertRaises(OSError):
                report_viewer.bind_server('127.0.0.1', (taken.server_address[1],))
        finally:
            taken.server_close()


if __name__ == '__main__':
    unittest.main()
