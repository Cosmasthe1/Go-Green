"""
fleet/base.py — Go Green Expanded Fleet
════════════════════════════════════════
Shared base class and RideOffer model for all new fleet adapters.
Extends the providers/base.py pattern with fleet-specific fields:
  • fleet_type          (EBIKE / MATATU / BRT)
  • battery_swap        (e-bikes with swappable batteries)
  • route_id            (BRT / fixed-route vehicles)
  • sacco_name          (matatu SACCO)
  • occupancy_avg       (for per-passenger CO₂ calculation)
  • ev_manufacturer     (Roam, BasiGo, Ecobodaa, etc.)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FleetType(str, Enum):
    EBIKE   = "ebike"
    MATATU  = "matatu"
    BRT     = "brt"
    TAXI    = "taxi"    # existing ride-hail


@dataclass
class RideOffer:
    """Unified offer model — superset of providers/base.py RideOffer."""

    # Identity
    provider:       str
    provider_slug:  str
    fleet_type:     FleetType
    ride_type:      str
    ev_model:       str
    ev_manufacturer: str           # Roam, BasiGo, Ecobodaa, CHTC, etc.
    color:          str
    logo_url:       str
    store_region:   str = "africa"

    # Geography
    distance_km:    float = 0.0
    pickup_lat:     float = 0.0
    pickup_lon:     float = 0.0
    drop_lat:       float = 0.0
    drop_lon:       float = 0.0

    # Pricing (KES)
    price_kes:      float = 0.0
    price_per_km:   float = 0.0
    currency:       str   = "KES"
    surge:          float = 1.0

    # Driver / crew
    driver_name:    str   = ""
    driver_rating:  float = 4.5
    driver_phone:   str   = ""
    plate:          str   = ""

    # Logistics
    eta_min:        int   = 5
    duration_min:   int   = 15
    seats:          int   = 1
    occupancy_avg:  float = 1.0   # average passengers (for per-pax CO₂)
    in_stock:       bool  = True

    # Fleet-specific
    battery_swap:   bool          = False   # e-bikes: swappable battery
    range_km:       float         = 0.0     # single-charge / single-swap range
    route_id:       str           = ""      # BRT route code
    route_name:     str           = ""      # BRT route human name
    sacco_name:     str           = ""      # Matatu SACCO
    frequency_min:  int           = 0       # BRT: minutes between buses

    # Environment
    co2_saved_g:    float  = 0.0    # grams CO₂ saved vs ICE equivalent
    co2_per_pax_g:  float  = 0.0    # per-passenger CO₂ saved

    # Extras
    promo_code:     str   = ""
    badge:          str   = ""
    deal_score:     int   = 0
    booking_url:    str   = ""
    data_source:    str   = "price_model"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["fleet_type"] = self.fleet_type.value
        return d

    @property
    def fare_display(self) -> str:
        return f"KSh {self.price_kes:,.0f}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a  = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


class FleetAdapter:
    """Base class for all Go Green fleet adapters."""

    PROVIDER_NAME:    str = ""
    PROVIDER_SLUG:    str = ""
    FLEET_TYPE:       FleetType = FleetType.TAXI
    COLOR:            str = "#00e87a"
    LOGO_URL:         str = ""
    EV_MODEL:         str = ""
    EV_MANUFACTURER:  str = ""
    RIDE_TYPE:        str = ""
    BASE_FARE_KES:    float = 50.0
    RATE_PER_KM_KES:  float = 30.0
    DELIVERY_RANGE:   tuple = (3, 10)
    SEATS:            int   = 1
    OCCUPANCY_AVG:    float = 1.0
    BATTERY_SWAP:     bool  = False
    RANGE_KM:         float = 100.0
    EV_KWH_PER_KM:    float = 0.015    # e-bike default
    AFEC_BASELINE:    float = 0.035    # baseline ICE fuel use (L/km)
    BOOKING_DEEP_LINK: str  = ""

    _DRIVERS = [
        "James K.", "Amina W.", "Peter N.", "Grace O.",
        "Samuel M.", "Brian T.", "Lydia C.", "Dennis R.",
    ]
    _PLATES = ["KDA", "KDB", "KBZ", "KCA", "KCB"]

    def get_offers(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
        max_results: int = 1,
    ) -> list[RideOffer]:
        """Override in subclass. Falls back to price model."""
        return [
            self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, i)
            for i in range(max_results)
        ]

    def _make_offer(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
        variant: int = 0,
    ) -> RideOffer:
        dist  = haversine_km(pickup_lat, pickup_lon, drop_lat, drop_lon)
        surge = random.choice([1.0, 1.0, 1.0, 1.15, 1.3])
        price = round((self.BASE_FARE_KES + self.RATE_PER_KM_KES * dist) * surge, -1)
        dmin, dmax = self.DELIVERY_RANGE
        eta   = dmin + random.randint(0, dmax - dmin)
        dur   = int(dist / 20 * 60) + random.randint(2, 8)  # 20 km/h avg for boda

        # CO₂ saved vs ICE baseline
        EF_PETROL, WTT   = 2.296, 1.19
        EF_GRID          = 0.061
        be_kg = dist * self.AFEC_BASELINE * EF_PETROL * WTT
        pe_kg = (dist * self.EV_KWH_PER_KM) * EF_GRID
        co2_g = max(be_kg - pe_kg, 0) * 1000
        co2_pax_g = co2_g / self.OCCUPANCY_AVG

        return RideOffer(
            provider        = self.PROVIDER_NAME,
            provider_slug   = self.PROVIDER_SLUG,
            fleet_type      = self.FLEET_TYPE,
            ride_type       = self.RIDE_TYPE,
            ev_model        = self.EV_MODEL,
            ev_manufacturer = self.EV_MANUFACTURER,
            color           = self.COLOR,
            logo_url        = self.LOGO_URL,
            distance_km     = round(dist, 2),
            pickup_lat=pickup_lat, pickup_lon=pickup_lon,
            drop_lat=drop_lat,     drop_lon=drop_lon,
            price_kes       = price,
            price_per_km    = self.RATE_PER_KM_KES,
            surge           = surge,
            driver_name     = random.choice(self._DRIVERS),
            driver_rating   = round(random.uniform(4.1, 5.0), 1),
            driver_phone    = f"+2547{random.randint(10000000, 99999999)}",
            plate           = f"{random.choice(self._PLATES)} {random.randint(100,999)} {chr(random.randint(65,72))}",
            eta_min         = eta,
            duration_min    = dur,
            seats           = self.SEATS,
            occupancy_avg   = self.OCCUPANCY_AVG,
            battery_swap    = self.BATTERY_SWAP,
            range_km        = self.RANGE_KM,
            co2_saved_g     = round(co2_g, 1),
            co2_per_pax_g   = round(co2_pax_g, 1),
            booking_url     = self.BOOKING_DEEP_LINK.format(
                pickup_lat=pickup_lat, pickup_lon=pickup_lon,
                drop_lat=drop_lat, drop_lon=drop_lon,
            ) if self.BOOKING_DEEP_LINK else "",
            data_source     = "price_model",
        )
