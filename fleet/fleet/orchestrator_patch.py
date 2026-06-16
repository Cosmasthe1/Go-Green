"""
fleet/orchestrator_patch.py — Go Green
════════════════════════════════════════════════════════════════════════════
Patches GoGreenOrchestrator to include e-bikes, matatu SACCOs, and BRT
buses alongside the existing ride-hail providers.

Two patch modes:

  Mode 1 — APPEND (default)
    Keeps the 7 existing ride-hail providers AND adds all new fleet types.
    Riders see ALL options in one ranked list — cheapest BRT fare at top,
    fastest e-boda next, best-value taxi after that.

  Mode 2 — REPLACE
    Replaces the ride-hail simulation entirely with the full fleet registry.
    Use when you no longer need the old providers.py simulation.

Usage in app.py (one-liner):
    from fleet.orchestrator_patch import patch_orchestrator
    from orchestrator_agent import GoGreenOrchestrator
    patch_orchestrator(GoGreenOrchestrator, mode="append")
════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Literal

from .registry import FLEET_REGISTRY, get_fleet_offers, FleetType
from .vm0038_ext import FleetCategory, calculate_trip_carbon

logger = logging.getLogger(__name__)


def patch_orchestrator(
    orchestrator_class,
    mode: Literal["append", "replace"] = "append",
    fleet_types: list[FleetType] | None = None,
) -> None:
    """
    Patch GoGreenOrchestrator.ride.get_offers() to include the expanded fleet.

    Parameters
    ----------
    mode         : "append" keeps existing providers + adds new ones
                   "replace" uses only the fleet registry
    fleet_types  : optional filter — e.g. [FleetType.EBIKE] to only add e-bikes
    """
    original_init = orchestrator_class.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        # Capture the original get_offers method
        _original_get_offers = self.ride.get_offers

        def expanded_get_offers(
            pickup_lat: float, pickup_lon: float,
            drop_lat:   float, drop_lon:   float,
        ) -> list[dict]:

            # ── Ride-hail offers (original) ───────────────────────────────────
            if mode == "append":
                try:
                    rh_offers = _original_get_offers(
                        pickup_lat, pickup_lon, drop_lat, drop_lon
                    )
                except Exception as exc:
                    logger.warning("Original get_offers failed: %s", exc)
                    rh_offers = []
            else:
                rh_offers = []

            # ── Fleet offers (new) ─────────────────────────────────────────────
            try:
                fleet_offers = get_fleet_offers(
                    pickup_lat, pickup_lon, drop_lat, drop_lon,
                    fleet_types=fleet_types,
                    max_results=1,
                )
                # Convert fleet RideOffer → dict shape expected by orchestrator
                fleet_dicts = [_fleet_to_dict(o) for o in fleet_offers]
            except Exception as exc:
                logger.warning("Fleet get_offers failed: %s", exc)
                fleet_dicts = []

            # ── Merge + re-rank ────────────────────────────────────────────────
            all_offers = rh_offers + fleet_dicts

            if not all_offers:
                return []

            # Unified deal-score sort
            prices = [o.get("price_kes", 999) for o in all_offers]
            mn, mx = min(prices), max(prices)

            def score(o: dict) -> float:
                ps = 100 * (mx - o["price_kes"]) / (mx - mn) if mx > mn else 50
                rs = (o.get("driver_rating", 4.5) / 5.0) * 100
                es = min(100, o.get("co2_saved_g", 0) / 10)
                ts = 85  # trust default
                return 0.40 * ps + 0.25 * rs + 0.20 * ts + 0.15 * es

            all_offers.sort(key=score, reverse=True)

            # Re-assign badges
            _prices  = [o["price_kes"]   for o in all_offers]
            _etas    = [o.get("eta_min", 5) for o in all_offers]
            _co2s    = [o.get("co2_saved_g", 0) for o in all_offers]
            idx_cheap = _prices.index(min(_prices))
            idx_fast  = _etas.index(min(_etas))
            idx_eco   = _co2s.index(max(_co2s))

            for i, o in enumerate(all_offers):
                if i == 0:                     o["badge"] = "🏆 Best Overall"
                elif i == idx_cheap:           o["badge"] = "💰 Cheapest"
                elif i == idx_fast:            o["badge"] = "⚡ Fastest"
                elif i == idx_eco:             o["badge"] = "🌿 Greenest"
                elif not o.get("badge"):       o["badge"] = ""

            logger.info(
                "Expanded fleet: %d ride-hail + %d fleet = %d total offers",
                len(rh_offers), len(fleet_dicts), len(all_offers),
            )
            return all_offers

        self.ride.get_offers = expanded_get_offers

        # ── Also patch the carbon agent to handle new categories ──────────────
        _original_process_trip = self.carbon.process_trip

        def expanded_process_trip(
            phone, trip_id, vehicle_category, distance_km, charger_type="L2",
        ):
            # Try the original carbon agent first (handles PSV_PASSENGER_CAR etc.)
            try:
                return _original_process_trip(
                    phone, trip_id, vehicle_category, distance_km, charger_type
                )
            except Exception:
                pass

            # Fallback to fleet VM0038 extension for new categories
            try:
                fc = FleetCategory(vehicle_category.value
                                   if hasattr(vehicle_category, "value")
                                   else str(vehicle_category))
                result = calculate_trip_carbon(fc, distance_km)
                logger.info(
                    "Fleet carbon: %s %.2f km → %.8f VCU",
                    fc.value, distance_km, result["net_vcu"],
                )
                return result
            except Exception as exc:
                logger.warning("Fleet carbon calculation failed: %s", exc)
                return {}

        self.carbon.process_trip = expanded_process_trip

        logger.info(
            "GoGreenOrchestrator patched with expanded fleet "
            "(mode=%s, %d new adapters)",
            mode, len(FLEET_REGISTRY),
        )

    orchestrator_class.__init__ = patched_init


# ── Conversion helper ─────────────────────────────────────────────────────────

def _fleet_to_dict(offer) -> dict:
    """
    Convert a fleet.base.RideOffer to the dict shape that
    GoGreenOrchestrator, WhatsApp agent, and Ionic app expect.
    """
    d = offer.to_dict()

    # Ensure all keys the orchestrator depends on are present
    d.setdefault("provider",      offer.provider)
    d.setdefault("provider_slug", offer.provider_slug)
    d.setdefault("ride_type",     offer.ride_type)
    d.setdefault("ev_model",      offer.ev_model)
    d.setdefault("price_kes",     offer.price_kes)
    d.setdefault("eta_min",       offer.eta_min)
    d.setdefault("duration_min",  offer.duration_min)
    d.setdefault("distance_km",   offer.distance_km)
    d.setdefault("co2_saved_g",   offer.co2_saved_g)
    d.setdefault("driver_name",   offer.driver_name)
    d.setdefault("driver_rating", offer.driver_rating)
    d.setdefault("driver_phone",  offer.driver_phone)
    d.setdefault("plate",         offer.plate)
    d.setdefault("surge",         offer.surge)
    d.setdefault("promo_code",    offer.promo_code)
    d.setdefault("in_stock",      offer.in_stock)
    d.setdefault("seats",         offer.seats)
    d.setdefault("store_region",  offer.store_region)
    d.setdefault("data_source",   offer.data_source)

    # Fleet-specific extras (used by the mobile app)
    d["fleet_type"]      = offer.fleet_type.value
    d["battery_swap"]    = offer.battery_swap
    d["route_id"]        = offer.route_id
    d["route_name"]      = offer.route_name
    d["sacco_name"]      = offer.sacco_name
    d["occupancy_avg"]   = offer.occupancy_avg
    d["co2_per_pax_g"]   = offer.co2_per_pax_g
    d["ev_manufacturer"] = offer.ev_manufacturer
    d["frequency_min"]   = getattr(offer, "frequency_min", 0)

    return d
