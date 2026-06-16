"""
uber_green/fx.py — Go Green
────────────────────────────────────────────────────────────────────────────
Exchange rate helper — USD → KES conversion for Uber fare normalisation.

Uses Open Exchange Rates (free tier) or falls back to the CBK/hardcoded rate.
Rates are cached for 1 hour.

Set OPENEXCHANGERATES_APP_ID in .env for live rates.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Fallback rate (CBK mid-rate, May 2026)
_FALLBACK_KES = 130.0
_CACHE_TTL    = 3600   # 1 hour

_cached_rate: Optional[float] = None
_cache_ts:    float = 0.0

OXR_APP_ID = os.environ.get("OPENEXCHANGERATES_APP_ID", "")


def usd_to_kes(usd: float = 1.0) -> float:
    """Convert USD amount to KES using latest cached rate."""
    rate = _get_rate()
    return round(usd * rate, 2)


def _get_rate() -> float:
    global _cached_rate, _cache_ts

    if _cached_rate and time.time() - _cache_ts < _CACHE_TTL:
        return _cached_rate

    rate = _fetch_rate()
    _cached_rate = rate
    _cache_ts    = time.time()
    return rate


def _fetch_rate() -> float:
    if not OXR_APP_ID:
        logger.debug("FX: no OPENEXCHANGERATES_APP_ID — using fallback rate %.2f", _FALLBACK_KES)
        return _FALLBACK_KES

    try:
        resp = requests.get(
            "https://openexchangerates.org/api/latest.json",
            params={"app_id": OXR_APP_ID, "symbols": "KES"},
            timeout=5,
        )
        resp.raise_for_status()
        rate = float(resp.json()["rates"]["KES"])
        logger.info("FX: USD/KES = %.4f (live)", rate)
        return rate
    except Exception as exc:
        logger.warning("FX: live rate fetch failed (%s) — using fallback %.2f", exc, _FALLBACK_KES)
        return _FALLBACK_KES
