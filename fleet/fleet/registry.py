"""
fleet/registry.py — Go Green
════════════════════════════════════════════════════════════════════════════
Unified fleet registry — all ride-hail + e-bike + matatu + BRT providers.

get_fleet_offers() fans out to all relevant adapters in parallel
and returns offers sorted by deal score, with fleet-type context.
════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .base import FleetAdapter, FleetType, RideOffer
from .ebike  import EcobodaaAdapter, EBodaAdapter, BoltBodaAdapter, RoamBodaAdapter
from .matatu import BasiGoMatatuAdapter, RoamMoveAdapter, OpibusMatatuAdapter
from .brt    import NamataBRTNdovuAdapter, NamataBRTLine2Adapter, NamataBRTKifaruAdapter

logger = logging.getLogger(__name__)

# ── Trust scores by provider ──────────────────────────────────────────────────
PROVIDER_TRUST: dict[str, float] = {
    "Ecobodaa":          0.82,
    "eBoda":             0.76,
    "Bolt Boda":         0.90,
    "Roam Boda":         0.84,
    "BasiGo Matatu":     0.88,
    "Roam Move":         0.86,
    "Opibus Matatu":     0.84,
    "NAMATA BRT Ndovu":  0.92,
    "NAMATA BRT Line 2": 0.90,
    "NAMATA BRT Kifaru": 0.88,
}

# ── Fleet registry ────────────────────────────────────────────────────────────

FLEET_REGISTRY: list[FleetAdapter] = [
    # E-bikes
    EcobodaaAdapter(),
    EBodaAdapter(),
    BoltBodaAdapter(),
    RoamBodaAdapter(),
    # Matatus
    BasiGoMatatuAdapter(),
    RoamMoveAdapter(),
    OpibusMatatuAdapter(),
    # BRT
    NamataBRTNdovuAdapter(),
    NamataBRTLine2Adapter(),
    NamataBRTKifaruAdapter(),
]

_REGISTRY_MAP: dict[str, FleetAdapter] = {a.PROVIDER_SLUG: a for a in FLEET_REGISTRY}


def get_fleet_by_type(fleet_type: FleetType) -> list[FleetAdapter]:
    """Return all adapters of a given fleet type."""
    return [a for a in FLEET_REGISTRY if a.FLEET_TYPE == fleet_type]


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(offer: RideOffer, all_prices: list[float]) -> int:
    mn, mx = min(all_prices), max(all_prices)
    price_score  = 100 * (mx - offer.price_kes) / (mx - mn) if mx > mn else 50.0
    rating_score = (offer.driver_rating / 5.0) * 100
    trust_score  = PROVIDER_TRUST.get(offer.provider, 0.80) * 100
    eta_score    = max(0.0, 100.0 - offer.eta_min * 3)
    eco_score    = min(100.0, offer.co2_saved_g / 10)   # bonus for high CO₂ savings
    return round(
        0.35 * price_score
        + 0.20 * rating_score
        + 0.20 * trust_score
        + 0.15 * eta_score
        + 0.10 * eco_score
    )


def _assign_badges(ranked: list[RideOffer]) -> None:
    if not ranked:
        return
    prices  = [o.price_kes    for o in ranked]
    etas    = [o.eta_min      for o in ranked]
    co2s    = [o.co2_saved_g  for o in ranked]

    idx_cheap   = prices.index(min(prices))
    idx_fast    = etas.index(min(etas))
    idx_eco     = co2s.index(max(co2s))

    for i, o in enumerate(ranked):
        if o.badge:                            continue   # already set by adapter
        if i == 0:    o.badge = "🏆 Best Deal"
        elif i == idx_cheap: o.badge = "💰 Cheapest"
        elif i == idx_fast:  o.badge = "⚡ Fastest ETA"
        elif i == idx_eco:   o.badge = "🌿 Greenest"


# ── Main entry point ──────────────────────────────────────────────────────────

def get_fleet_offers(
    pickup_lat:     float,
    pickup_lon:     float,
    drop_lat:       float,
    drop_lon:       float,
    fleet_types:    Optional[list[FleetType]] = None,
    max_results:    int   = 1,
    timeout_sec:    float = 10.0,
) -> list[RideOffer]:
    """
    Query all (or filtered) fleet adapters in parallel.
    Returns offers sorted by deal score, best first.

    Parameters
    ----------
    fleet_types  : optional filter — e.g. [FleetType.EBIKE, FleetType.MATATU]
                   None = all fleet types
    max_results  : offers per provider (default 1)
    """
    adapters = FLEET_REGISTRY
    if fleet_types:
        adapters = [a for a in FLEET_REGISTRY if a.FLEET_TYPE in fleet_types]

    all_offers: list[RideOffer] = []

    with ThreadPoolExecutor(max_workers=len(adapters)) as ex:
        futures = {
            ex.submit(a.get_offers, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results): a.PROVIDER_NAME
            for a in adapters
        }
        for f in as_completed(futures, timeout=timeout_sec + 2):
            name = futures[f]
            try:
                results = f.result(timeout=timeout_sec)
                all_offers.extend(results)
                logger.debug("Fleet %s → %d offer(s)", name, len(results))
            except Exception as exc:
                logger.warning("Fleet %s failed: %s", name, exc)

    if not all_offers:
        return []

    prices = [o.price_kes for o in all_offers]
    for o in all_offers:
        o.deal_score = _score(o, prices)

    all_offers.sort(key=lambda o: o.deal_score, reverse=True)
    _assign_badges(all_offers)

    return all_offers
