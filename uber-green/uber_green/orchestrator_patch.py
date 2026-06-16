"""
uber_green/orchestrator_patch.py — Go Green
────────────────────────────────────────────────────────────────────────────
Wires the live UberGreenAdapter into GoGreenOrchestrator's booking flow.

Drop-in replacement for the provider simulation in orchestrator_agent.py.

Changes made to the orchestrator:
  1. RideAgent.get_offers()  →  calls UberGreenAdapter.get_offers() (live API)
  2. _handle_confirmation()  →  calls UberGreenAdapter.book_ride() (real trip)
  3. _check_payment()        →  polls UberGreenAdapter.get_status() for driver

Usage (in orchestrator_agent.py):
    from uber_green.orchestrator_patch import patch_orchestrator
    patch_orchestrator(GoGreenOrchestrator)
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .adapter import DataSource, UberGreenAdapter

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Module-level adapter singleton ────────────────────────────────────────────
_uber = UberGreenAdapter()


# ─────────────────────────────────────────────────────────────────────────────
# Patched RideAgent.get_offers
# ─────────────────────────────────────────────────────────────────────────────

def _live_get_offers(
    pickup_lat: float, pickup_lon: float,
    drop_lat:   float, drop_lon:   float,
) -> list[dict]:
    """
    Replaces RideAgent._fetch_rides tool.
    Returns list of RideOffer.to_dict() — same shape as the old simulation.
    """
    offers = _uber.get_offers(pickup_lat, pickup_lon, drop_lat, drop_lon)
    result = []
    for o in offers:
        d = o.to_dict()
        # Normalise field names to match what the UI and carbon agent expect
        d.setdefault("provider",       o.provider)
        d.setdefault("provider_slug",  o.provider_slug)
        d.setdefault("ride_type",      o.ride_type)
        d.setdefault("ev_model",       o.ev_model)
        d.setdefault("price_kes",      o.price_kes)
        d.setdefault("eta_min",        o.eta_min)
        d.setdefault("duration_min",   o.duration_min)
        d.setdefault("distance_km",    o.distance_km)
        d.setdefault("co2_saved_g",    o.co2_saved_g)
        d.setdefault("driver_name",    o.driver_name)
        d.setdefault("driver_rating",  o.driver_rating)
        d.setdefault("driver_phone",   o.driver_phone)
        d.setdefault("plate",          o.plate)
        d.setdefault("surge",          o.surge)
        d.setdefault("promo_code",     "")
        d.setdefault("in_stock",       True)
        d.setdefault("seats",          o.seats)
        d["data_source"] = o.data_source.value
        result.append(d)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Patched _handle_confirmation — real booking via Uber API
# ─────────────────────────────────────────────────────────────────────────────

def live_book_ride(
    offer:          dict,
    phone:          str,
    pickup:         str,
    destination:    str,
    pickup_lat:     float, pickup_lon: float,
    drop_lat:       float, drop_lon:   float,
) -> dict:
    """
    Book a real Uber Green trip.

    Returns a dict with:
      success          bool
      request_id       str   — Uber trip ID for status polling
      status           str   — initial status ("processing")
      customer_msg     str   — human-readable confirmation
      driver_name      str   — populated after driver assignment
      driver_phone     str
      plate            str
      ev_model         str
    """
    product_id = offer.get("product_id", "")
    fare_id    = offer.get("fare_id", "")

    # If this is a price-model offer (no product_id), return a simulated booking
    if not product_id or offer.get("data_source") == DataSource.PRICE_MODEL.value:
        logger.info("Uber booking: price-model offer — returning simulated booking")
        return _simulated_booking(offer, phone)

    try:
        rider_name = offer.get("driver_name") or "Go Green Rider"   # will be replaced
        detail = _uber.book_ride(
            product_id      = product_id,
            fare_id         = fare_id,
            pickup_lat      = pickup_lat, pickup_lon = pickup_lon,
            drop_lat        = drop_lat,   drop_lon   = drop_lon,
            rider_name      = rider_name,
            rider_phone     = phone,
            pickup_address  = pickup,
            dropoff_address = destination,
        )

        return {
            "success":       True,
            "request_id":    detail.request_id,
            "status":        detail.status,
            "customer_msg":  (
                f"✅ Uber Green booked! Trip ID: {detail.request_id}\n"
                f"Status: {detail.status}. Your driver is on the way."
            ),
            "driver_name":   detail.driver.name  if detail.driver  else "",
            "driver_phone":  detail.driver.phone_number if detail.driver else "",
            "plate":         detail.vehicle.license_plate if detail.vehicle else "",
            "ev_model":      (
                f"{detail.vehicle.make} {detail.vehicle.model}"
                if detail.vehicle and detail.vehicle.make else offer.get("ev_model", "EV")
            ),
        }

    except Exception as exc:
        logger.error("Uber live booking failed: %s", exc)
        return {
            "success":      False,
            "error":        str(exc),
            "customer_msg": f"⚠️ Booking failed: {exc}. Please try again.",
        }


def _simulated_booking(offer: dict, phone: str) -> dict:
    """Fallback booking result when no live API credentials are set."""
    import random
    trip_id = f"GG-{int(time.time())}"
    return {
        "success":      True,
        "request_id":   trip_id,
        "status":       "processing",
        "customer_msg": (
            f"Booking confirmed (demo mode — set UBER_CLIENT_ID to go live)\n"
            f"Trip ID: {trip_id}"
        ),
        "driver_name":  offer.get("driver_name", ""),
        "driver_phone": offer.get("driver_phone", ""),
        "plate":        offer.get("plate", ""),
        "ev_model":     offer.get("ev_model", "EV"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Patched trip status polling
# ─────────────────────────────────────────────────────────────────────────────

def poll_driver_assignment(request_id: str, max_wait_s: int = 90) -> dict:
    """
    Poll until Uber assigns a driver.
    Returns enriched driver + vehicle dict for the WhatsApp confirmation message.
    """
    try:
        detail = _uber.poll_driver(request_id, max_wait_s=max_wait_s)
        return {
            "status":       detail.status,
            "driver_name":  detail.driver.name  if detail.driver  else "",
            "driver_phone": detail.driver.phone_number if detail.driver else "",
            "driver_rating":detail.driver.rating if detail.driver else 4.8,
            "plate":        detail.vehicle.license_plate if detail.vehicle else "",
            "ev_model":     (
                f"{detail.vehicle.make} {detail.vehicle.model}"
                if detail.vehicle and detail.vehicle.make else ""
            ),
            "eta_min":      detail.eta or 5,
        }
    except Exception as exc:
        logger.warning("Uber poll failed: %s", exc)
        return {"status": "unknown", "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Monkey-patch helper
# ─────────────────────────────────────────────────────────────────────────────

def patch_orchestrator(orchestrator_class) -> None:
    """
    Patches the GoGreenOrchestrator class to use live Uber API calls.

    Call once at startup:
        from uber_green.orchestrator_patch import patch_orchestrator
        from orchestrator_agent import GoGreenOrchestrator
        patch_orchestrator(GoGreenOrchestrator)
    """
    import types

    original_init = orchestrator_class.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        # Replace the RideAgent's simulated fetch with live Uber API
        original_get_offers = self.ride.get_offers

        def patched_get_offers(plat, plon, dlat, dlon):
            live = _live_get_offers(plat, plon, dlat, dlon)
            if live:
                logger.info(
                    "Uber live offers: %d product(s) [%s]",
                    len(live),
                    live[0].get("data_source", "?"),
                )
            return live if live else original_get_offers(plat, plon, dlat, dlon)

        self.ride.get_offers = patched_get_offers
        logger.info("GoGreenOrchestrator patched with live UberGreenAdapter")

    orchestrator_class.__init__ = patched_init
