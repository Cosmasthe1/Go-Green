"""
providers.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
EV ride provider registry.

Providers: Uber, Bolt, Yego, Faras, Little Cabs, Wasili, Weego
All rides are EV-only. Each provider adapter returns RideOffer objects.

In production, replace _simulate() with real partner API calls.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Protocol


# ─────────────────────────────────────────────────────────────────────────────
# Geo helpers
# ─────────────────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RideOffer:
    provider:        str       # "Uber"
    provider_slug:   str       # "uber"  (for logo lookup)
    ride_type:       str       # "UberGreen", "Bolt EV", etc.
    ev_model:        str       # "Tesla Model 3", "BYD Atto 3", etc.
    distance_km:     float
    eta_min:         int       # driver ETA in minutes
    duration_min:    int       # estimated trip duration
    price_kes:       float     # fare in KES
    surge:           float     # surge multiplier (1.0 = no surge)
    driver_name:     str
    driver_rating:   float
    driver_phone:    str
    plate:           str
    seats:           int       # available seats
    co2_saved_g:     float     # grams of CO₂ saved vs ICE equivalent
    promo_code:      str       # "" if none
    logo_url:        str       # SVG / PNG URL (or base64 data URI)
    color:           str       # brand hex colour

    def fare_display(self) -> str:
        return f"KSh {self.price_kes:,.0f}"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# ─────────────────────────────────────────────────────────────────────────────
# Simulated provider adapters
# ─────────────────────────────────────────────────────────────────────────────

class _Base:
    provider:      str
    provider_slug: str
    color:         str
    logo_url:      str
    # per-km base rate in KES
    base_rate:     float = 50.0
    base_fare:     float = 100.0   # flag-fall
    ev_models:     list[str] = field(default_factory=list)
    ride_type:     str = "EV Ride"

    def get_offer(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> RideOffer | None:
        dist   = haversine_km(pickup_lat, pickup_lon, drop_lat, drop_lon)
        surge  = random.choice([1.0, 1.0, 1.0, 1.2, 1.5])
        price  = round((self.base_fare + self.base_rate * dist) * surge, -1)
        eta    = random.randint(2, 10)
        dur    = int(dist / 30 * 60) + random.randint(2, 8)   # ~30 km/h city speed
        co2    = dist * 120  # g saved vs avg ICE (120 g/km)

        # Random driver
        names   = ["James K.", "Amina W.", "Peter N.", "Grace O.", "Samuel M.",
                   "Faith A.", "Brian T.", "Lydia C.", "Dennis R.", "Sharon L."]
        models  = self.ev_models or ["BYD Atto 3", "Tesla Model 3", "Hyundai IONIQ 5"]
        plates  = ["KDA", "KDB", "KBZ", "KCA", "KCB", "KDA"]

        return RideOffer(
            provider       = self.provider,
            provider_slug  = self.provider_slug,
            ride_type      = self.ride_type,
            ev_model       = random.choice(models),
            distance_km    = round(dist, 2),
            eta_min        = eta,
            duration_min   = dur,
            price_kes      = price,
            surge          = surge,
            driver_name    = random.choice(names),
            driver_rating  = round(random.uniform(4.2, 5.0), 1),
            driver_phone   = f"+2547{random.randint(10000000, 99999999)}",
            plate          = f"{random.choice(plates)} {random.randint(100,999)} {random.choice('ABCDEFGH')}",
            seats          = random.choice([3, 3, 4, 4, 6]),
            co2_saved_g    = round(co2),
            promo_code     = random.choice(["", "", "", "GREEN10", "EVRIDE5"]),
            logo_url       = self.logo_url,
            color          = self.color,
        )


# ── Provider definitions ──────────────────────────────────────────────────────

class UberAdapter(_Base):
    provider      = "Uber"
    provider_slug = "uber"
    color         = "#000000"
    ride_type     = "Uber Green"
    base_rate     = 55.0
    base_fare     = 120.0
    ev_models     = ["Tesla Model 3", "Nissan Leaf", "BYD Han"]
    # Official Uber green SVG wordmark (simplified inline)
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%23000'/%3E%3Ctext x='10' y='22' fill='white' font-size='18' font-family='Arial' font-weight='bold'%3EUber%3C/text%3E%3C/svg%3E"


class BoltAdapter(_Base):
    provider      = "Bolt"
    provider_slug = "bolt"
    color         = "#34D186"
    ride_type     = "Bolt EV"
    base_rate     = 42.0
    base_fare     = 90.0
    ev_models     = ["BYD Atto 3", "MG ZS EV", "Kia EV6"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%2334D186'/%3E%3Ctext x='10' y='22' fill='white' font-size='18' font-family='Arial' font-weight='bold'%3EBolt%3C/text%3E%3C/svg%3E"


class YegoAdapter(_Base):
    provider      = "Yego"
    provider_slug = "yego"
    color         = "#FF6B00"
    ride_type     = "Yego EV"
    base_rate     = 48.0
    base_fare     = 100.0
    ev_models     = ["Hyundai IONIQ 5", "BYD Dolphin", "Chery Omoda E5"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%23FF6B00'/%3E%3Ctext x='10' y='22' fill='white' font-size='18' font-family='Arial' font-weight='bold'%3EYego%3C/text%3E%3C/svg%3E"


class FarasAdapter(_Base):
    provider      = "Faras"
    provider_slug = "faras"
    color         = "#1A56DB"
    ride_type     = "Faras Green"
    base_rate     = 40.0
    base_fare     = 85.0
    ev_models     = ["BYD Seal", "Volkswagen ID.4", "MG4 EV"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%231A56DB'/%3E%3Ctext x='10' y='22' fill='white' font-size='18' font-family='Arial' font-weight='bold'%3EFaras%3C/text%3E%3C/svg%3E"


class LittleCabsAdapter(_Base):
    provider      = "Little Cabs"
    provider_slug = "little"
    color         = "#FECC00"
    ride_type     = "Little EV"
    base_rate     = 45.0
    base_fare     = 95.0
    ev_models     = ["Nissan Leaf", "BYD e6", "JAC iEV7S"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%23FECC00'/%3E%3Ctext x='6' y='22' fill='%23333' font-size='13' font-family='Arial' font-weight='bold'%3ELittle%3C/text%3E%3C/svg%3E"


class WasiliAdapter(_Base):
    provider      = "Wasili"
    provider_slug = "wasili"
    color         = "#7C3AED"
    ride_type     = "Wasili EV"
    base_rate     = 38.0
    base_fare     = 80.0
    ev_models     = ["BYD Atto 3", "Great Wall ORA", "Chery Tiggo 7 E"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%237C3AED'/%3E%3Ctext x='6' y='22' fill='white' font-size='14' font-family='Arial' font-weight='bold'%3EWasili%3C/text%3E%3C/svg%3E"


class WeegoAdapter(_Base):
    provider      = "Weego"
    provider_slug = "weego"
    color         = "#059669"
    ride_type     = "Weego EV"
    base_rate     = 44.0
    base_fare     = 88.0
    ev_models     = ["BYD Yuan Plus", "Geely Geometry C", "Neta V"]
    logo_url      = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 30'%3E%3Crect width='80' height='30' fill='%23059669'/%3E%3Ctext x='6' y='22' fill='white' font-size='15' font-family='Arial' font-weight='bold'%3EWeego%3C/text%3E%3C/svg%3E"


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

ALL_PROVIDERS: list[_Base] = [
    UberAdapter(),
    BoltAdapter(),
    YegoAdapter(),
    FarasAdapter(),
    LittleCabsAdapter(),
    WasiliAdapter(),
    WeegoAdapter(),
]

PROVIDER_MAP: dict[str, _Base] = {p.provider: p for p in ALL_PROVIDERS}


def get_all_offers(
    pickup_lat: float, pickup_lon: float,
    drop_lat:   float, drop_lon:   float,
) -> list[RideOffer]:
    """Query all providers and return available offers sorted by price."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    offers = []
    with ThreadPoolExecutor(max_workers=len(ALL_PROVIDERS)) as ex:
        futs = {ex.submit(p.get_offer, pickup_lat, pickup_lon, drop_lat, drop_lon): p
                for p in ALL_PROVIDERS}
        for f in as_completed(futs):
            try:
                offer = f.result(timeout=5)
                if offer:
                    offers.append(offer)
            except Exception:
                pass
    offers.sort(key=lambda o: o.price_kes)
    return offers
