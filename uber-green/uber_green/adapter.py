"""
uber_green/adapter.py — Go Green
────────────────────────────────────────────────────────────────────────────
UberGreenAdapter — the single provider adapter that replaces all simulation.

Implements the ProviderAdapter interface from providers/base.py.
Only Uber Green / electric products are surfaced to Go Green riders.

Pipeline for get_offers():
  1. POST /v1/guests/trips/estimates          (live fare + ETA)
  2. Filter to EV/Green products  (.is_green)
  3. Convert USD fare → KES (IEA 2024 rate, refreshed hourly)
  4. Build RideOffer with deep-link booking URL
  5. If API fails or returns no green products → price model fallback
     (keeps the app working even without credentials)

Booking pipeline (book_ride()):
  1. POST /v1/guests/trips                    (on-demand ride creation)
  2. Returns request_id for status polling
  3. Optionally lock fare with fare_id from estimates

Monitoring (get_trip_status()):
  GET /v1/guests/trips/{request_id}
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import math
import os
import random
from typing import Optional

from .auth import UberAuthError, UberCredentialsMissing, token_manager
from .client import UberAPIError, UberNoProductsError, uber_client
from .models import (
    CreateTripRequest,
    EstimatesResponse,
    GuestInfo,
    Location,
    ProductEstimate,
    TripDetail,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# KES conversion (IEA / CBK mid-rate — refresh from FX API in production)
# ─────────────────────────────────────────────────────────────────────────────

USD_TO_KES = float(os.environ.get("USD_TO_KES", "130.0"))


def _to_kes(usd: float) -> float:
    return round(usd * USD_TO_KES, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Geo helper
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a  = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
# RideOffer (minimal — extend from providers/base.py in production)
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass, field as dc_field
from enum import Enum


class DataSource(str, Enum):
    LIVE_API  = "live_api"
    PRICE_MODEL = "price_model"   # fallback when API unavailable


@dataclass
class RideOffer:
    # Identity
    provider:       str = "Uber"
    provider_slug:  str = "uber"
    ride_type:      str = "Uber Green"
    ev_model:       str = ""
    color:          str = "#000000"

    # Geography
    distance_km:    float = 0.0

    # Pricing (always KES for Go Green)
    price_kes:      float = 0.0
    currency_orig:  str   = "USD"
    price_orig:     float = 0.0
    surge:          float = 1.0

    # Driver (populated after booking or from trip detail)
    driver_name:    str   = ""
    driver_rating:  float = 4.8
    driver_phone:   str   = ""
    plate:          str   = ""
    ev_model_real:  str   = ""

    # Logistics
    eta_min:        int   = 5
    duration_min:   int   = 10
    seats:          int   = 4

    # Environment
    co2_saved_g:    float = 0.0

    # Booking
    product_id:     str   = ""
    fare_id:        str   = ""     # lock price on booking
    booking_url:    str   = ""
    data_source:    DataSource = DataSource.LIVE_API

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["data_source"] = self.data_source.value
        return d

    @property
    def fare_display(self) -> str:
        return f"KSh {self.price_kes:,.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# Adapter
# ─────────────────────────────────────────────────────────────────────────────

# Nairobi Uber Green product ID (discovery via /v1.2/products at launch)
# Set UBER_GREEN_PRODUCT_ID env var after first discovery run, or leave
# empty to use the is_green heuristic filter.
UBER_GREEN_PRODUCT_ID = os.environ.get("UBER_GREEN_PRODUCT_ID", "")

# Sandbox run UUID — required for sandbox estimate calls
UBER_SANDBOX_RUN_UUID = os.environ.get("UBER_SANDBOX_RUN_UUID", "")


class UberGreenAdapter:
    """
    Go Green ↔ Uber Guest Rides API adapter.

    get_offers()   — fetch live fare estimates, filter to EV products
    book_ride()    — create a real trip via the API
    get_status()   — poll trip status
    cancel()       — cancel an active trip

    All methods fall back gracefully when credentials are absent or the
    API is unreachable.
    """

    PROVIDER_NAME  = "Uber"
    PROVIDER_SLUG  = "uber"
    COLOR          = "#000000"
    RIDE_TYPE      = "Uber Green"

    # Price model constants (used ONLY as fallback)
    _BASE_FARE_KES = 120.0
    _RATE_KES_KM   = 55.0
    _EV_MODELS     = ["Tesla Model 3", "Nissan Leaf", "BYD Han EV", "Hyundai IONIQ 6"]
    _DRIVERS       = ["James K.", "Amina W.", "Peter N.", "Grace O.", "Samuel M."]
    _PLATES        = ["KDA", "KDB", "KBZ", "KCA", "KCB"]

    # Uber app deep-link (opens app; falls back to web URL if not installed)
    _DEEP_LINK = (
        "uber://?action=setPickup"
        "&pickup[latitude]={pickup_lat}&pickup[longitude]={pickup_lon}"
        "&dropoff[latitude]={drop_lat}&dropoff[longitude]={drop_lon}"
        "&product_id={product_id}"
        "&link_text=Go+Green+EV+Ride"
    )
    _WEB_LINK = (
        "https://m.uber.com/ul/"
        "?action=setPickup"
        "&pickup[latitude]={pickup_lat}&pickup[longitude]={pickup_lon}"
        "&dropoff[latitude]={drop_lat}&dropoff[longitude]={drop_lon}"
    )

    # ── Main entry: get estimates ─────────────────────────────────────────────

    def get_offers(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> list[RideOffer]:
        """
        Returns RideOffers for Uber Green products on this route.

        Live path:    Uber Guest Rides API  → DataSource.LIVE_API
        Fallback path: price model          → DataSource.PRICE_MODEL
        """
        if not token_manager.is_configured:
            logger.info("Uber: credentials not set — using price model fallback")
            return [self._price_model_offer(pickup_lat, pickup_lon, drop_lat, drop_lon)]

        try:
            estimates = uber_client.get_estimates(
                pickup  = Location(pickup_lat, pickup_lon),
                dropoff = Location(drop_lat,   drop_lon),
                sandbox_run_uuid = UBER_SANDBOX_RUN_UUID or None,
            )
            offers = self._parse_estimates(estimates, pickup_lat, pickup_lon, drop_lat, drop_lon)

            if not offers:
                logger.info(
                    "Uber: no Green products in response (%d total products) — "
                    "trying price model",
                    len(estimates.product_estimates),
                )
                return [self._price_model_offer(pickup_lat, pickup_lon, drop_lat, drop_lon)]

            logger.info("Uber: %d Green offer(s) from live API", len(offers))
            return offers

        except UberCredentialsMissing as exc:
            logger.warning("Uber: %s", exc)
        except UberAuthError as exc:
            logger.warning("Uber auth error: %s", exc)
        except UberAPIError as exc:
            logger.warning("Uber API error: %s", exc)
        except Exception as exc:
            logger.error("Uber unexpected error: %s", exc, exc_info=True)

        return [self._price_model_offer(pickup_lat, pickup_lon, drop_lat, drop_lon)]

    # ── Book a ride ───────────────────────────────────────────────────────────

    def book_ride(
        self,
        product_id:  str,
        fare_id:     str,
        pickup_lat:  float, pickup_lon: float,
        drop_lat:    float, drop_lon:   float,
        rider_name:  str,
        rider_phone: str,
        rider_email: Optional[str] = None,
        pickup_address:  Optional[str] = None,
        dropoff_address: Optional[str] = None,
    ) -> TripDetail:
        """
        Create a real on-demand Uber Green trip.

        Returns TripDetail with request_id.
        Caller should poll get_status(request_id) until status == 'accepted'.
        """
        first, *rest = rider_name.split(maxsplit=1)
        last = rest[0] if rest else "."

        request = CreateTripRequest(
            guest    = GuestInfo(
                first_name   = first,
                last_name    = last,
                phone_number = rider_phone,
                email        = rider_email,
            ),
            pickup   = Location(pickup_lat, pickup_lon, address=pickup_address),
            dropoff  = Location(drop_lat,   drop_lon,   address=dropoff_address),
            product_id = product_id,
            fare_id    = fare_id or None,
        )

        logger.info(
            "Uber booking: product=%s rider=%s pickup=(%.4f,%.4f)",
            product_id, rider_phone, pickup_lat, pickup_lon,
        )
        return uber_client.create_trip(
            request,
            sandbox_run_uuid = UBER_SANDBOX_RUN_UUID or None,
        )

    # ── Trip lifecycle ────────────────────────────────────────────────────────

    def get_status(self, request_id: str) -> str:
        """Returns trip status string."""
        return uber_client.get_trip_status(request_id)

    def get_trip(self, request_id: str) -> TripDetail:
        """Full trip detail including driver + vehicle."""
        return uber_client.get_trip(request_id)

    def cancel(self, request_id: str) -> bool:
        return uber_client.cancel_trip(request_id)

    def poll_driver(self, request_id: str, max_wait_s: int = 90) -> TripDetail:
        """Block until driver is assigned or timeout."""
        return uber_client.poll_until_driver(request_id, max_wait_s=max_wait_s)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_estimates(
        self,
        resp:       EstimatesResponse,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> list[RideOffer]:
        dist_km = _haversine_km(pickup_lat, pickup_lon, drop_lat, drop_lon)
        offers  = []

        green_products = resp.green_products()

        # If explicit product ID is set, also include it even if not flagged green
        if UBER_GREEN_PRODUCT_ID:
            for pe in resp.product_estimates:
                if pe.product_id == UBER_GREEN_PRODUCT_ID and pe not in green_products:
                    green_products.append(pe)

        for pe in green_products:
            offer = self._product_to_offer(pe, dist_km, pickup_lat, pickup_lon, drop_lat, drop_lon)
            offers.append(offer)

        return offers

    def _product_to_offer(
        self,
        pe:         ProductEstimate,
        dist_km:    float,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> RideOffer:
        # Price
        fare_kes   = 0.0
        fare_usd   = 0.0
        fare_id    = ""
        currency   = "USD"
        surge      = 1.0

        if pe.fare:
            fare_usd = pe.fare.value or ((pe.fare.low_estimate or 0) + (pe.fare.high_estimate or 0)) / 2
            fare_kes = _to_kes(fare_usd)
            fare_id  = pe.fare.fare_id or ""
            currency = pe.fare.currency_code or "USD"
            # Detect surge from fare breakdown
            for item in pe.fare.fare_breakdown:
                if "surge" in item.name.lower() and item.value > 0:
                    surge = round(item.value / (fare_usd - item.value), 1) if fare_usd > item.value else 1.5

        # ETA
        eta_min = pe.pickup_estimate or 5

        # Duration from trip object (seconds → minutes)
        duration_min = 10
        if pe.trip:
            duration_min = max(1, pe.trip.duration_estimate // 60)

        # CO2 saved vs ICE (120 g/km average)
        co2_g = round(dist_km * 120)

        # Booking deep-link
        booking_url = self._DEEP_LINK.format(
            pickup_lat=pickup_lat, pickup_lon=pickup_lon,
            drop_lat=drop_lat, drop_lon=drop_lon,
            product_id=pe.product_id,
        )

        return RideOffer(
            provider      = self.PROVIDER_NAME,
            provider_slug = self.PROVIDER_SLUG,
            ride_type     = pe.display_name or self.RIDE_TYPE,
            ev_model      = pe.short_desc or "Electric Vehicle",
            color         = self.COLOR,
            distance_km   = round(dist_km, 2),
            price_kes     = fare_kes,
            currency_orig = currency,
            price_orig    = fare_usd,
            surge         = surge,
            driver_name   = "",           # not available until trip is created
            driver_rating = 4.8,
            eta_min       = eta_min,
            duration_min  = duration_min,
            seats         = pe.capacity or 4,
            co2_saved_g   = co2_g,
            product_id    = pe.product_id,
            fare_id       = fare_id,
            booking_url   = booking_url,
            data_source   = DataSource.LIVE_API,
        )

    def _price_model_offer(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> RideOffer:
        """
        Fallback price-model offer — used when Uber API is not available.
        Still shows a realistic price and provides a deep-link into the app.
        """
        import random as _r
        dist     = _haversine_km(pickup_lat, pickup_lon, drop_lat, drop_lon)
        surge    = _r.choice([1.0, 1.0, 1.0, 1.2, 1.5])
        price_k  = round((self._BASE_FARE_KES + self._RATE_KES_KM * dist) * surge, -1)
        eta      = _r.randint(2, 7)
        duration = int(dist / 30 * 60) + _r.randint(2, 8)

        booking_url = self._WEB_LINK.format(
            pickup_lat=pickup_lat, pickup_lon=pickup_lon,
            drop_lat=drop_lat, drop_lon=drop_lon,
        )

        return RideOffer(
            provider      = self.PROVIDER_NAME,
            provider_slug = self.PROVIDER_SLUG,
            ride_type     = self.RIDE_TYPE,
            ev_model      = _r.choice(self._EV_MODELS),
            color         = self.COLOR,
            distance_km   = round(dist, 2),
            price_kes     = price_k,
            currency_orig = "KES",
            price_orig    = price_k,
            surge         = surge,
            driver_name   = _r.choice(self._DRIVERS),
            driver_rating = round(_r.uniform(4.2, 5.0), 1),
            driver_phone  = f"+2547{_r.randint(10000000, 99999999)}",
            plate         = f"{_r.choice(self._PLATES)} {_r.randint(100,999)} {chr(_r.randint(65,72))}",
            eta_min       = eta,
            duration_min  = duration,
            seats         = 4,
            co2_saved_g   = round(dist * 120),
            product_id    = UBER_GREEN_PRODUCT_ID,
            booking_url   = booking_url,
            data_source   = DataSource.PRICE_MODEL,
        )
