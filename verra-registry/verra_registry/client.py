"""
verra_registry/client.py — Go Green
────────────────────────────────────────────────────────────────────────────
Verra Registry public data client.

The Verra Registry (registry.verra.org) does NOT publish a documented
REST API.  This client uses the undocumented JSON endpoints that the
registry web portal itself calls — these are stable but not guaranteed.

Supported operations (read-only, no auth required):
  • search_projects(query)          — search VCS projects by keyword/ID
  • get_project(vcs_id)             — full project details
  • get_issuances(vcs_id)           — list VCU issuance events for a project
  • get_retirements(vcs_id)         — list VCU retirement records
  • verify_serial(serial)           — check a VCU serial number is valid
  • get_account_issuances(account)  — VCUs issued to a specific account

Registry base: https://registry.verra.org
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

REGISTRY_BASE  = "https://registry.verra.org"
TIMEOUT_S      = 15
_RATE_LIMIT_S  = 1.0   # be respectful — 1 request per second


@dataclass
class VCSProject:
    vcs_id:        str
    name:          str
    country:       str
    methodology:   str
    status:        str
    registry_url:  str
    total_issued:  float   # tCO2e
    total_retired: float   # tCO2e


@dataclass
class VCUIssuance:
    serial_number_start: str
    serial_number_end:   str
    vintage_start:       str
    vintage_end:         str
    quantity:            float   # tCO2e
    issuance_date:       str
    retirement_status:   str    # "Active" | "Retired"


class VerraRegistryClient:
    """
    Read-only client for the Verra public registry.
    Used by Go Green to:
      1. Verify our project is registered (get_project)
      2. Confirm when VCUs land after issuance (get_issuances)
      3. Validate serial numbers against the public ledger (verify_serial)
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "GoGreen-VCS-Client/1.0 (registry@gogreen.co.ke)",
            "Accept":     "application/json",
        })
        self._last_call = 0.0

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """Rate-limited GET request to the Verra registry."""
        elapsed = time.time() - self._last_call
        if elapsed < _RATE_LIMIT_S:
            time.sleep(_RATE_LIMIT_S - elapsed)

        url = f"{REGISTRY_BASE}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=TIMEOUT_S)
            resp.raise_for_status()
            self._last_call = time.time()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Verra registry GET %s failed: %s", path, exc)
            raise

    # ── Project search ─────────────────────────────────────────────────────────

    def search_projects(self, query: str, program: str = "VCS") -> list[dict]:
        """
        Search VCS projects.
        Registry endpoint: /app/search/VCS/All Projects (JSON variant)
        """
        try:
            data = self._get(
                f"/api/public/projects/{program}",
                params={"searchText": query, "limit": 20},
            )
            return data if isinstance(data, list) else data.get("projects", [])
        except Exception:
            # Fallback: scrape the public search page URL
            url = (
                f"{REGISTRY_BASE}/app/search/{program}/All%20Projects"
                f"?projectName={requests.utils.quote(query)}"
            )
            logger.info("Verra registry search URL: %s", url)
            return [{"search_url": url, "query": query}]

    def get_project(self, vcs_id: str | int) -> Optional[dict]:
        """
        Get full project details for VCS project ID.
        Public URL: https://registry.verra.org/app/projectDetail/VCS/{vcs_id}
        """
        try:
            return self._get(f"/api/public/projects/VCS/{vcs_id}")
        except Exception:
            # Return registry URL so the human can verify manually
            return {
                "vcs_id":      str(vcs_id),
                "registry_url": f"{REGISTRY_BASE}/app/projectDetail/VCS/{vcs_id}",
            }

    def get_issuances(self, vcs_id: str | int) -> list[dict]:
        """List all VCU issuance events for a project."""
        try:
            data = self._get(f"/api/public/projects/VCS/{vcs_id}/issuances")
            return data if isinstance(data, list) else data.get("issuances", [])
        except Exception as exc:
            logger.warning("Could not fetch issuances for VCS%s: %s", vcs_id, exc)
            return []

    def get_retirements(self, vcs_id: str | int) -> list[dict]:
        """List all VCU retirement records for a project."""
        try:
            data = self._get(f"/api/public/projects/VCS/{vcs_id}/retirements")
            return data if isinstance(data, list) else data.get("retirements", [])
        except Exception as exc:
            logger.warning("Could not fetch retirements for VCS%s: %s", vcs_id, exc)
            return []

    def verify_serial(self, serial: str) -> dict:
        """
        Verify a VCU serial number exists in the registry.
        Serial format: VCS-XXXXXX-YYYYMMDD-YYYYMMDD-VCS-XXXXXXX-XX-XX-XX-XX
        """
        try:
            return self._get(f"/api/public/credits/serial/{serial}")
        except Exception:
            return {
                "serial":       serial,
                "verified":     False,
                "lookup_url":   f"{REGISTRY_BASE}/app/search/VCS",
                "note":         "Manual verification required at registry.verra.org",
            }

    def get_latest_issuance_date(self, vcs_id: str | int) -> Optional[str]:
        """Return the date of the most recent issuance for a project."""
        issuances = self.get_issuances(vcs_id)
        if not issuances:
            return None
        try:
            # Sort by issuance date descending
            sorted_i = sorted(
                issuances,
                key=lambda x: x.get("issuanceDate", x.get("date", "")),
                reverse=True,
            )
            latest = sorted_i[0]
            return latest.get("issuanceDate") or latest.get("date")
        except Exception:
            return None

    def get_total_issued(self, vcs_id: str | int) -> float:
        """Total tCO2e issued for a project (all vintages)."""
        issuances = self.get_issuances(vcs_id)
        total = 0.0
        for i in issuances:
            qty = i.get("quantity") or i.get("totalQuantity") or 0
            try:
                total += float(qty)
            except (TypeError, ValueError):
                pass
        return total


# Module-level singleton
verra_client = VerraRegistryClient()
