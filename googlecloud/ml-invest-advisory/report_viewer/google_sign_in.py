"""
Google sign-in (beta) for the report viewer: the OAuth 2.0 authorization code flow with PKCE, plus a session store.

Purpose:
  A visitor signs in with their Google account and grants read-only Cloud Storage access. The server keeps the
  resulting access token in memory, under a random session ID that the browser holds in an HttpOnly cookie, and
  calls Cloud Storage with it. There's no fallback to any server-side credential: no session, no reports.

Flow:
  1. GoogleSignIn.start()  -> Google's consent URL, plus a one-time `state` value that the caller also stores in a
                              short-lived cookie (binds the callback to this browser, preventing login CSRF).
  2. Google redirects to REDIRECT_PATH with ?code=...&state=...
  3. GoogleSignIn.finish() -> checks `state`, exchanges the code (with the PKCE verifier) for an access token.
  4. SessionStore.create() -> session ID for the cookie. Sessions end when the access token expires (~1 hour;
                              no refresh token is requested or stored), on sign-out, or on server restart.

Requirements:
  Python 3.10+, standard library only. An OAuth 2.0 client ID of type "Web application" whose authorized redirect
  URIs include https://<each address the viewer is opened at>/auth/callback; see README.md.
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
REVOCATION_ENDPOINT = 'https://oauth2.googleapis.com/revoke'
# openid + email only identify the user for display; devstorage.read_only is what Cloud Storage checks.
SCOPES = ('openid', 'email', 'https://www.googleapis.com/auth/devstorage.read_only')
REDIRECT_PATH = '/auth/callback'
# OAuth client JSON used when neither OAUTH_CLIENT_FILE nor OAUTH_CLIENT_ID/OAUTH_CLIENT_SECRET is set.
DEFAULT_OAUTH_CLIENT_FILE = ('/home/hil/Encfs/confidential/secrets/'
                             'client_secret_603410815034-35d82rt5p1t0n4mijg5j14g5etjoqnih.apps.googleusercontent.com.json')
PENDING_SIGN_IN_SECONDS = 10 * 60
# Anyone can start a sign-in without being signed in, so the pending ones are capped: past this many, the oldest is
# dropped. This bounds the memory that a flood of /auth/login requests can use (about 1 MB per 2,500 sign-ins).
MAX_PENDING_SIGN_INS = 10_000
# Ends a session this long before its access token expires, so a request never carries an expired token.
TOKEN_EXPIRY_MARGIN_SECONDS = 60
TIMEOUT_SECONDS = 30


class SignInError(Exception):
    """The sign-in callback was invalid, or Google refused the code exchange."""


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> 'OAuthClient':
        """
        Reads, in this order: OAUTH_CLIENT_FILE (the client JSON downloaded from the Google Cloud console);
        OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET; DEFAULT_OAUTH_CLIENT_FILE if it exists. Raises ValueError if none
        is available, or if a client file isn't a "Web application" client.
        """
        client_file = os.environ.get('OAUTH_CLIENT_FILE')
        client_id, client_secret = os.environ.get('OAUTH_CLIENT_ID'), os.environ.get('OAUTH_CLIENT_SECRET')
        if not client_file and not (client_id and client_secret) and os.path.isfile(DEFAULT_OAUTH_CLIENT_FILE):
            client_file = DEFAULT_OAUTH_CLIENT_FILE
        if client_file:
            with open(client_file, encoding='utf-8') as f:
                config = json.load(f)
            web = config.get('web')
            if not web:
                raise ValueError(f'{client_file} is not a "Web application" OAuth client (no "web" key)')
            return cls(web['client_id'], web['client_secret'])
        if client_id and client_secret:
            return cls(client_id, client_secret)
        raise ValueError(f'no OAuth client configured: set OAUTH_CLIENT_FILE, or OAUTH_CLIENT_ID and '
                         f'OAUTH_CLIENT_SECRET, or create {DEFAULT_OAUTH_CLIENT_FILE} (see README.md)')


@dataclass(frozen=True)
class SignedInUser:
    email: str
    access_token: str
    expires_at: float  # time.time() after which the session is over


class GoogleSignIn:
    def __init__(self, client: OAuthClient):
        self.client = client
        # state -> (PKCE code verifier, redirect URI, expiry time)
        self._pending: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.Lock()

    def start(self, redirect_uri: str) -> tuple[str, str]:
        """
        Returns (Google's consent URL to redirect the browser to, the state value to bind to the browser).
        redirect_uri is <the address the browser used>/auth/callback; Google refuses it unless it is an authorized
        redirect URI of the OAuth client, and finish() sends the same one.
        """
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b'=')
        with self._lock:
            self._drop_expired_pending()
            while len(self._pending) >= MAX_PENDING_SIGN_INS:
                del self._pending[next(iter(self._pending))]  # the oldest; dicts keep insertion order
            self._pending[state] = (code_verifier, redirect_uri, time.time() + PENDING_SIGN_IN_SECONDS)
        params = {
            'client_id': self.client.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(SCOPES),
            'state': state,
            'code_challenge': code_challenge.decode(),
            'code_challenge_method': 'S256',
            'access_type': 'online',  # no refresh token
            'include_granted_scopes': 'true',
        }
        return f'{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}', state

    def finish(self, query_state: str, cookie_state: str, code: str) -> SignedInUser:
        """
        Completes the sign-in started by start(). query_state is the callback's ?state=, cookie_state the value
        stored in the browser at start(); both must match an unexpired, unused sign-in. Raises SignInError.
        """
        if not query_state or not secrets.compare_digest(query_state, cookie_state or ''):
            raise SignInError('the sign-in did not start in this browser, or it took too long; please try again')
        with self._lock:
            self._drop_expired_pending()
            pending = self._pending.pop(query_state, None)
        if not pending:
            raise SignInError('the sign-in expired or was already used; please try again')
        if not code:
            raise SignInError('Google returned no authorization code')

        token = self._exchange_code(code, code_verifier=pending[0], redirect_uri=pending[1])
        missing = set(SCOPES) - set(token.get('scope', '').split()) - {'openid', 'email'}
        if missing:
            raise SignInError('read access to Cloud Storage was not granted; sign in again and allow it')
        return SignedInUser(email=_email_from_id_token(token.get('id_token', '')),
                            access_token=token['access_token'],
                            expires_at=time.time() + int(token.get('expires_in', 3600)) - TOKEN_EXPIRY_MARGIN_SECONDS)

    @staticmethod
    def revoke(access_token: str) -> None:
        """Best-effort revocation of an access token at sign-out."""
        request = urllib.request.Request(REVOCATION_ENDPOINT, data=urllib.parse.urlencode({'token': access_token})
                                         .encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS).close()
        except urllib.error.URLError:
            pass

    def _exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> dict:
        body = urllib.parse.urlencode({
            'code': code,
            'client_id': self.client.client_id,
            'client_secret': self.client.client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
        }).encode()
        request = urllib.request.Request(TOKEN_ENDPOINT, data=body,
                                         headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise SignInError(f'Google refused the sign-in (HTTP {error.code})') from error
        except urllib.error.URLError as error:
            raise SignInError(f'Google is unreachable: {error.reason}') from error

    def _drop_expired_pending(self) -> None:
        now = time.time()
        for state in [state for state, (*_, expires_at) in self._pending.items() if expires_at < now]:
            del self._pending[state]


class SessionStore:
    """In-memory sessions: random session ID -> SignedInUser. Thread-safe."""

    def __init__(self):
        self._sessions: dict[str, SignedInUser] = {}
        self._lock = threading.Lock()

    def create(self, user: SignedInUser) -> str:
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            # Sessions that are never used again would otherwise stay in memory after they expire.
            now = time.time()
            for expired in [sid for sid, other in self._sessions.items() if other.expires_at <= now]:
                del self._sessions[expired]
            self._sessions[session_id] = user
        return session_id

    def get(self, session_id: str | None) -> SignedInUser | None:
        """The session's user, or None if there's no such session or its access token expired."""
        if not session_id:
            return None
        with self._lock:
            user = self._sessions.get(session_id)
            if user and user.expires_at <= time.time():
                del self._sessions[session_id]
                return None
            return user

    def delete(self, session_id: str | None) -> SignedInUser | None:
        with self._lock:
            return self._sessions.pop(session_id, None) if session_id else None


def _email_from_id_token(id_token: str) -> str:
    """
    The email claim of an ID token, for display only. The token comes straight from Google's token endpoint over
    TLS, so its signature needn't be checked (OpenID Connect Core 3.1.3.7); access decisions never use it.
    """
    try:
        payload = id_token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return claims.get('email', 'unknown account')
    except (IndexError, ValueError):
        return 'unknown account'
