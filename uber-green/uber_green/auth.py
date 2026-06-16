"""
uber_green/auth.py — Go Green
────────────────────────────────────────────────────────────────────────────
Uber OAuth 2.0  client_credentials  token manager.

Scope required: guests.trips
Endpoint:       POST https://auth.uber.com/oauth/v2/token
Docs:           https://developer.uber.com/docs/guest-rides/guides/authentication

Token lifetime: 30 days (2 592 000 s) — refreshed automatically when
                less than 60 s remain (safety margin).

Usage:
    from uber_green.auth import token_manager
    token = token_manager.get()          # returns str or raises UberAuthError
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config  (set in .env or CI secrets)
# ─────────────────────────────────────────────────────────────────────────────

UBER_CLIENT_ID     = os.environ.get("UBER_CLIENT_ID",     "")
UBER_CLIENT_SECRET = os.environ.get("UBER_CLIENT_SECRET", "")
UBER_SANDBOX       = os.environ.get("UBER_SANDBOX", "true").lower() == "true"

# Organisation UUID for Uber for Business (U4B) 3P apps.
# Required in x-uber-organizationuuid header for b2b endpoints.
UBER_ORG_UUID      = os.environ.get("UBER_ORG_UUID", "")

AUTH_URL           = "https://auth.uber.com/oauth/v2/token"
SCOPE              = "guests.trips"
REQUEST_TIMEOUT    = 10   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────

class UberAuthError(RuntimeError):
    """Raised when we cannot obtain a valid Uber access token."""


class UberCredentialsMissing(UberAuthError):
    """Raised when UBER_CLIENT_ID or UBER_CLIENT_SECRET are not set."""


# ─────────────────────────────────────────────────────────────────────────────
# Token model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Token:
    access_token: str
    expires_at:   float   # Unix timestamp
    scope:        str = SCOPE

    @property
    def is_valid(self) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at - 60

    def bearer(self) -> str:
        return f"Bearer {self.access_token}"


# ─────────────────────────────────────────────────────────────────────────────
# Token manager (thread-safe singleton)
# ─────────────────────────────────────────────────────────────────────────────

class _TokenManager:
    """
    Thread-safe OAuth2 token manager.
    Fetches a new token only when the cached one is expired or missing.
    """

    def __init__(self) -> None:
        self._token:  Optional[_Token] = None
        self._lock    = threading.Lock()

    # ── Public ────────────────────────────────────────────────────────────────

    def get(self) -> str:
        """
        Return a valid Bearer token string.
        Raises UberCredentialsMissing / UberAuthError on failure.
        """
        with self._lock:
            if self._token and self._token.is_valid:
                return self._token.bearer()
            self._token = self._fetch()
            return self._token.bearer()

    def invalidate(self) -> None:
        """Force token refresh on next call (e.g. after a 401 response)."""
        with self._lock:
            self._token = None

    @property
    def is_configured(self) -> bool:
        """True when credentials env vars are set."""
        return bool(UBER_CLIENT_ID and UBER_CLIENT_SECRET)

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch(self) -> _Token:
        if not self.is_configured:
            raise UberCredentialsMissing(
                "Set UBER_CLIENT_ID and UBER_CLIENT_SECRET environment variables. "
                "Register at https://developer.uber.com"
            )

        logger.info(
            "Uber: fetching OAuth2 token (sandbox=%s, scope=%s)", UBER_SANDBOX, SCOPE
        )

        try:
            resp = requests.post(
                AUTH_URL,
                # Uber requires form-encoded — JSON is NOT supported
                data={
                    "client_id":     UBER_CLIENT_ID,
                    "client_secret": UBER_CLIENT_SECRET,
                    "grant_type":    "client_credentials",
                    "scope":         SCOPE,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise UberAuthError(f"Uber auth network error: {exc}") from exc

        if resp.status_code == 401:
            raise UberAuthError(
                "Uber auth failed (401) — check UBER_CLIENT_ID / UBER_CLIENT_SECRET. "
                "Make sure your app has the 'guests.trips' scope enabled in the "
                "Uber Developer Dashboard."
            )

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise UberAuthError(f"Uber auth HTTP {resp.status_code}: {resp.text[:200]}") from exc

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise UberAuthError(f"Uber auth: missing access_token in response: {data}")

        expires_in = int(data.get("expires_in", 2_592_000))   # default 30 days
        t = _Token(
            access_token = token,
            expires_at   = time.time() + expires_in,
            scope        = data.get("scope", SCOPE),
        )
        logger.info(
            "Uber: token obtained — expires in %dd %dh",
            expires_in // 86400,
            (expires_in % 86400) // 3600,
        )
        return t


# ── Singleton ─────────────────────────────────────────────────────────────────
token_manager = _TokenManager()
