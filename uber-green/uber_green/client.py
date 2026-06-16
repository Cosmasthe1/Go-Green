"""
uber_green/client.py — Go Green
────────────────────────────────────────────────────────────────────────────
Uber Guest Rides API HTTP client.

Wraps:
  POST /v1/guests/trips/estimates   → get fare + ETA for all products
  POST /v1/guests/trips             → create (book) a trip
  GET  /v1/guests/trips/{id}        → get trip status / driver details
  GET  /v1/guests/trips/{id}/status → lightweight status poll

Features:
  • Automatic token refresh via auth.token_manager
  • 401 → invalidate token → retry once
  • Configurable timeout and retry strategy
  • Sandbox vs production URL via UBER_SANDBOX env var
  • x-uber-organizationuuid header injected when UBER_ORG_UUID is set
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from .auth import UBER_ORG_UUID, UBER_SANDBOX, token_manager
from .models import (
    CreateTripRequest,
    EstimatesResponse,
    GuestInfo,
    Location,
    TripDetail,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL    = "https://sandbox-api.uber.com" if UBER_SANDBOX else "https://api.uber.com"
TIMEOUT_S   = 12    # seconds per request
MAX_RETRIES = 1     # retry once on 401 (after token refresh)


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────

class UberAPIError(RuntimeError):
    def __init__(self, status: int, body: str, url: str) -> None:
        super().__init__(f"Uber API {status} at {url}: {body[:300]}")
        self.status = status
        self.body   = body
        self.url    = url


class UberRateLimitError(UberAPIError):
    """429 — back off and retry later."""


class UberNoProductsError(RuntimeError):
    """No matching Green/EV products found for this location."""


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class UberClient:
    """
    Thin, stateless HTTP client for the Uber Guest Rides API.

    All methods raise UberAPIError (or subclasses) on non-2xx responses.
    The caller (UberAdapter) is responsible for catching and falling back.
    """

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _headers(self, sandbox_run_uuid: Optional[str] = None) -> dict:
        headers = {
            "Authorization":  token_manager.get(),
            "Content-Type":   "application/json",
            "Accept-Language":"en_US",
        }
        if UBER_ORG_UUID:
            headers["x-uber-organizationuuid"] = UBER_ORG_UUID
        if sandbox_run_uuid:
            headers["x-uber-sandbox-runuuid"] = sandbox_run_uuid
        return headers

    def _request(
        self,
        method: str,
        path:   str,
        *,
        json:   Optional[dict] = None,
        params: Optional[dict] = None,
        sandbox_run_uuid: Optional[str] = None,
    ) -> dict:
        url = f"{BASE_URL}{path}"

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    json    = json,
                    params  = params,
                    headers = self._headers(sandbox_run_uuid),
                    timeout = TIMEOUT_S,
                )
            except requests.exceptions.Timeout as exc:
                raise UberAPIError(0, f"Timeout after {TIMEOUT_S}s", url) from exc
            except requests.exceptions.RequestException as exc:
                raise UberAPIError(0, str(exc), url) from exc

            if resp.status_code == 401 and attempt < MAX_RETRIES:
                logger.warning("Uber 401 — invalidating token and retrying")
                token_manager.invalidate()
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning("Uber rate-limited — Retry-After: %ds", retry_after)
                raise UberRateLimitError(429, resp.text, url)

            if not resp.ok:
                raise UberAPIError(resp.status_code, resp.text, url)

            try:
                return resp.json()
            except ValueError as exc:
                raise UberAPIError(resp.status_code, resp.text, url) from exc

        # Should never reach here
        raise UberAPIError(0, "Exceeded retry limit", url)

    # ── Public API methods ────────────────────────────────────────────────────

    def get_estimates(
        self,
        pickup:           Location,
        dropoff:          Location,
        sandbox_run_uuid: Optional[str] = None,
    ) -> EstimatesResponse:
        """
        POST /v1/guests/trips/estimates

        Returns all available products with fares and ETAs for the given
        pickup → dropoff route.

        The sandbox_run_uuid is required when testing against the Uber
        sandbox environment (obtain from the sandbox setup endpoints).
        In production leave it None.
        """
        body = {
            "pickup":  pickup.to_dict(),
            "dropoff": dropoff.to_dict(),
        }
        logger.info(
            "Uber estimates: (%.4f,%.4f) → (%.4f,%.4f) [%s]",
            pickup.latitude, pickup.longitude,
            dropoff.latitude, dropoff.longitude,
            "sandbox" if UBER_SANDBOX else "production",
        )
        raw = self._request(
            "POST",
            "/v1/guests/trips/estimates",
            json             = body,
            sandbox_run_uuid = sandbox_run_uuid,
        )
        return EstimatesResponse.from_dict(raw)

    def create_trip(
        self,
        request:          CreateTripRequest,
        sandbox_run_uuid: Optional[str] = None,
    ) -> TripDetail:
        """
        POST /v1/guests/trips

        Books a ride on-demand.  Returns a TripDetail with request_id,
        status, and initial driver/vehicle info (if already assigned).

        Pass fare_id from the estimates response to lock in the upfront fare.
        """
        logger.info(
            "Uber create trip: product=%s guest=%s %s",
            request.product_id,
            request.guest.phone_number,
            "(fare locked)" if request.fare_id else "(no fare lock)",
        )
        raw = self._request(
            "POST",
            "/v1/guests/trips",
            json             = request.to_dict(),
            sandbox_run_uuid = sandbox_run_uuid,
        )
        return TripDetail.from_dict(raw)

    def get_trip(self, request_id: str) -> TripDetail:
        """GET /v1/guests/trips/{request_id}"""
        raw = self._request("GET", f"/v1/guests/trips/{request_id}")
        return TripDetail.from_dict(raw)

    def get_trip_status(self, request_id: str) -> str:
        """
        GET /v1/guests/trips/{request_id}/status
        Returns the status string: processing | accepted | arriving |
                                   in_progress | completed | cancelled
        """
        raw = self._request("GET", f"/v1/guests/trips/{request_id}/status")
        return raw.get("status", "unknown")

    def cancel_trip(self, request_id: str) -> bool:
        """DELETE /v1/guests/trips/{request_id}  → True if cancelled."""
        try:
            self._request("DELETE", f"/v1/guests/trips/{request_id}")
            return True
        except UberAPIError as exc:
            logger.warning("Uber cancel trip %s failed: %s", request_id, exc)
            return False

    def poll_until_driver(
        self,
        request_id: str,
        max_wait_s: int = 120,
        interval_s: int = 5,
    ) -> TripDetail:
        """
        Poll GET /v1/guests/trips/{request_id} until a driver is assigned
        (status == 'accepted' | 'arriving') or timeout is reached.
        Returns the latest TripDetail regardless.
        """
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            detail = self.get_trip(request_id)
            if detail.status in ("accepted", "arriving", "in_progress"):
                return detail
            if detail.status in ("completed", "cancelled"):
                return detail
            time.sleep(interval_s)
        return self.get_trip(request_id)


# ── Module-level default client ───────────────────────────────────────────────
uber_client = UberClient()
