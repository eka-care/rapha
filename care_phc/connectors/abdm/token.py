"""Access token manager for Eka ABDM Connect.

    POST {BASE}/connect-auth/v1/account/login
    {client_id, client_secret, sharing_key?}
    -> {access_token, expires_in, refresh_token, refresh_expires_in}

Cached in memory with a TTL slightly under expires_in, refreshed on 401, and
single-flight so a burst of concurrent calls triggers one login rather than a
thundering herd. Never persisted, never logged.

`transport` is injected so this is testable without a network or a credential.
"""
from __future__ import annotations

import threading
import time

LOGIN_PATH = "/connect-auth/v1/account/login"
REFRESH_PATH = "/connect-auth/v1/account/refresh"

# Renew this far before the server's expiry, so a token never expires in flight.
SKEW_SECONDS = 60


class TokenManager:
    def __init__(self, base_url, client_id, client_secret, transport,
                 sharing_key=None, now=time.monotonic):
        self._base = base_url.rstrip("/")
        self._id = client_id
        self._secret = client_secret
        self._sharing_key = sharing_key
        self._post = transport
        self._now = now
        self._lock = threading.Lock()
        self._token = None
        self._refresh_token = None
        self._expires_at = 0.0
        self.logins = 0          # observable for tests; not a metric

    def _store(self, payload):
        self._token = payload["access_token"]
        self._refresh_token = payload.get("refresh_token")
        # A short or missing expires_in must not produce a token we treat as
        # valid forever, nor one already expired. Clamp rather than trust.
        ttl = max(float(payload.get("expires_in") or 0) - SKEW_SECONDS, 30.0)
        self._expires_at = self._now() + ttl

    def _login(self):
        body = {"client_id": self._id, "client_secret": self._secret}
        if self._sharing_key:
            body["sharing_key"] = self._sharing_key
        self.logins += 1
        self._store(self._post(self._base + LOGIN_PATH, body))

    def token(self):
        """A valid access token. Single-flight: one login per expiry, not per caller."""
        if self._token and self._now() < self._expires_at:
            return self._token
        with self._lock:
            # Another thread may have refreshed while we waited for the lock.
            if self._token and self._now() < self._expires_at:
                return self._token
            if self._refresh_token:
                try:
                    self._store(self._post(self._base + REFRESH_PATH,
                                           {"refresh_token": self._refresh_token}))
                    return self._token
                except Exception:
                    # A dead refresh token is not fatal; fall back to a login.
                    self._refresh_token = None
            self._login()
            return self._token

    def invalidate(self):
        """Called on a 401 so the next token() re-authenticates."""
        with self._lock:
            self._expires_at = 0.0

    def __repr__(self):
        # Never let a secret reach a log line or a traceback.
        state = "valid" if self._token and self._now() < self._expires_at else "stale"
        return f"<TokenManager {self._base} {state}>"
