"""
fleet/brt.py — Go Green NAMATA BRT Electric Bus Adapters
══════════════════════════════════════════════════════════
Three BRT route adapters for Nairobi's NAMATA electric bus network.

BRT context (2025):
  • NAMATA (Nairobi Metropolitan Area Transport Authority) mandated
    all BRT vehicles be green (electric, hybrid, or biodiesel)
  • EU/Team Europe financing agreements expected H1 2025 for BRT Lines
  • E-bus consultant procured Nov 2024–Jul 2025 for Line 2 operationalisation
  • Grid capacity assessment for BRT Line 3 depot underway
  • BasiGo and Roam Rapid competing for government BRT tenders

BRT Lines:
  Ndovu (Line 1): Kangemi ↔ Imara Daima via Westlands, CBD, Nairobi West
  Line 2:         Githurai ↔ CBD (EU-financed electric, under procurement 2025)
  Kifaru (Line 4): Jogoo Road corridor — detailed service planning underway

VM0038 baseline for BRT buses:
  AFEC = 0.350 L/km diesel (full-size city bus, AMS-III.BC large bus default)
  EV   = 0.950 kWh/km (Roam Rapid / BasiGo full-size bus)
  Occupancy: 60 passengers average (BRT design capacity)
  → ~1,009g CO₂ saved per km  → ~16.8g CO₂ per passenger-km
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional
from .base import FleetAdapter, FleetType, RideOffer


@dataclass
class BRTStop:
    """A stop on a BRT route with name and coordinates."""
    name: str
    lat:  float
    lon:  float
    seq:  int          # sequence number along route


# ── BRT Route definitions ─────────────────────────────────────────────────────

BRT_NDOVU_STOPS = [
    BRTStop("Kangemi Terminus",    -1.2697, 36.7388, 1),
    BRTStop("Westlands Station",   -1.2636, 36.8030, 2),
    BRTStop("Museum Hill",         -1.2745, 36.8153, 3),
    BRTStop("Nairobi CBD Central", -1.2833, 36.8172, 4),
    BRTStop("Nairobi West",        -1.3050, 36.8220, 5),
    BRTStop("NextGen Mall",        -1.3100, 36.8270, 6),
    BRTStop("Imara Daima",         -1.3400, 36.8700, 7),
]

BRT_LINE2_STOPS = [
    BRTStop("Githurai 45",         -1.2050, 36.8880, 1),
    BRTStop("Kasarani",            -1.2180, 36.8970, 2),
    BRTStop("Thika Road Mall",     -1.2250, 36.8750, 3),
    BRTStop("Garden City",         -1.2300, 36.8800, 4),
    BRTStop("Pangani",             -1.2600, 36.8380, 5),
    BRTStop("CBD North",           -1.2750, 36.8220, 6),
    BRTStop("Nairobi CBD Central", -1.2833, 36.8172, 7),
]

BRT_KIFARU_STOPS = [
    BRTStop("Muthurwa",            -1.2850, 36.8350, 1),
    BRTStop("Jogoo Road East",     -1.2900, 36.8450, 2),
    BRTStop("Makadara",            -1.2950, 36.8550, 3),
    BRTStop("Donholm",             -1.3000, 36.8700, 4),
    BRTStop("Outering Road",       -1.3050, 36.8900, 5),
    BRTStop("Embakasi",            -1.3260, 36.8960, 6),
]

ALL_BRT_STOPS = {
    "ndovu":  BRT_NDOVU_STOPS,
    "line2":  BRT_LINE2_STOPS,
    "kifaru": BRT_KIFARU_STOPS,
}


def _nearest_stop(
    stops: list[BRTStop], lat: float, lon: float
) -> BRTStop:
    """Find the BRT stop nearest to given coordinates."""
    from .base import haversine_km
    return min(stops, key=lambda s: haversine_km(lat, lon, s.lat, s.lon))


def _fare_between(stops: list[BRTStop], from_stop: BRTStop, to_stop: BRTStop) -> float:
    """Flat BRT fare structure — KES 50 flat within CBD, KES 80 cross-city."""
    seg_diff = abs(to_stop.seq - from_stop.seq)
    if seg_diff == 0:   return 30.0
    if seg_diff <= 2:   return 50.0
    if seg_diff <= 4:   return 70.0
    return 80.0


class _BRTBase(FleetAdapter):
    """Shared logic for all BRT route adapters."""

    FLEET_TYPE       = FleetType.BRT
    EV_KWH_PER_KM    = 0.950     # Roam Rapid / BasiGo full-size bus
    AFEC_BASELINE    = 0.350     # diesel city bus AMS-III.BC
    SEATS            = 80
    OCCUPANCY_AVG    = 60.0
    BATTERY_SWAP     = False
    RANGE_KM         = 250.0

    ROUTE_KEY: str = ""     # set by subclass

    def get_offers(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
        max_results: int = 1,
    ) -> list[RideOffer]:
        stops      = ALL_BRT_STOPS.get(self.ROUTE_KEY, BRT_NDOVU_STOPS)
        from_stop  = _nearest_stop(stops, pickup_lat,  pickup_lon)
        to_stop    = _nearest_stop(stops, drop_lat,    drop_lon)

        # ETA: BRT runs every 5–12 min peak, 12–20 min off-peak
        eta  = random.randint(3, 12)
        fare = _fare_between(stops, from_stop, to_stop)

        from .base import haversine_km
        dist  = haversine_km(from_stop.lat, from_stop.lon, to_stop.lat, to_stop.lon)
        dur   = max(10, int(dist / 25 * 60))   # BRT avg ~25 km/h with stops

        # CO₂
        EF_DIESEL, WTT = 2.703, 1.21
        EF_GRID = 0.061
        be_kg = dist * self.AFEC_BASELINE * EF_DIESEL * WTT
        pe_kg = dist * self.EV_KWH_PER_KM * EF_GRID
        co2_g = max(be_kg - pe_kg, 0) * 1000
        co2_pax_g = co2_g / self.OCCUPANCY_AVG

        offer = RideOffer(
            provider        = self.PROVIDER_NAME,
            provider_slug   = self.PROVIDER_SLUG,
            fleet_type      = self.FLEET_TYPE,
            ride_type       = self.RIDE_TYPE,
            ev_model        = self.EV_MODEL,
            ev_manufacturer = self.EV_MANUFACTURER,
            color           = self.COLOR,
            logo_url        = self.LOGO_URL,
            distance_km     = round(dist, 2),
            pickup_lat      = from_stop.lat, pickup_lon = from_stop.lon,
            drop_lat        = to_stop.lat,   drop_lon   = to_stop.lon,
            price_kes       = fare,
            price_per_km    = round(fare / dist, 2) if dist > 0 else 0,
            driver_name     = "NAMATA Driver",
            driver_rating   = round(random.uniform(4.0, 4.8), 1),
            eta_min         = eta,
            duration_min    = dur,
            seats           = self.SEATS,
            occupancy_avg   = self.OCCUPANCY_AVG,
            range_km        = self.RANGE_KM,
            route_id        = self.ROUTE_KEY.upper(),
            route_name      = f"{from_stop.name} → {to_stop.name}",
            frequency_min   = random.randint(5, 15),
            co2_saved_g     = round(co2_g, 1),
            co2_per_pax_g   = round(co2_pax_g, 2),
            badge           = "🚌 BRT Electric",
            data_source     = "price_model",
            booking_url     = (
                f"https://namata.go.ke/brt/{self.ROUTE_KEY}"
                f"?from={from_stop.name}&to={to_stop.name}"
            ),
        )
        return [offer]


class NamataBRTNdovuAdapter(_BRTBase):
    """
    NAMATA BRT Line 1 — Ndovu route.
    Kangemi ↔ Imara Daima via Westlands, CBD, Nairobi West, NextGen Mall.
    First BRT line announced; service planning complete.
    Buses: BasiGo / Roam Rapid (competing for NAMATA tender).
    """

    PROVIDER_NAME   = "NAMATA BRT Ndovu"
    PROVIDER_SLUG   = "namata_ndovu"
    COLOR           = "#1d4ed8"          # NAMATA blue
    RIDE_TYPE       = "BRT Line 1 — Ndovu"
    EV_MODEL        = "Roam Rapid / BasiGo Electric Bus"
    EV_MANUFACTURER = "Roam Electric / BasiGo Kenya"
    ROUTE_KEY       = "ndovu"
    DELIVERY_RANGE  = (3, 12)


class NamataBRTLine2Adapter(_BRTBase):
    """
    NAMATA BRT Line 2 — Githurai ↔ CBD.
    EU/Team Europe-financed. E-bus consultant procured Nov 2024–Jul 2025.
    Grid capacity assessment for depot underway.
    Expected operational 2026.
    """

    PROVIDER_NAME   = "NAMATA BRT Line 2"
    PROVIDER_SLUG   = "namata_line2"
    COLOR           = "#7c3aed"
    RIDE_TYPE       = "BRT Line 2 — Githurai Corridor"
    EV_MODEL        = "BasiGo Electric Bus (EU-financed)"
    EV_MANUFACTURER = "BasiGo Kenya / CHTC"
    ROUTE_KEY       = "line2"
    DELIVERY_RANGE  = (5, 15)


class NamataBRTKifaruAdapter(_BRTBase):
    """
    NAMATA BRT Line 4 — Kifaru (Jogoo Road corridor).
    Detailed service planning underway; inclusive BRT infrastructure
    design with ITDP for vulnerable groups.
    """

    PROVIDER_NAME   = "NAMATA BRT Kifaru"
    PROVIDER_SLUG   = "namata_kifaru"
    COLOR           = "#059669"
    RIDE_TYPE       = "BRT Line 4 — Kifaru (Jogoo Road)"
    EV_MODEL        = "Opibus / Roam Electric Bus"
    EV_MANUFACTURER = "Opibus / Roam Electric Kenya"
    ROUTE_KEY       = "kifaru"
    DELIVERY_RANGE  = (5, 18)
