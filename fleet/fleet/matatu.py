"""
fleet/matatu.py — Go Green Electric Matatu SACCO Adapters
═══════════════════════════════════════════════════════════
Three electric matatu adapters covering Kenya's PSV SACCO ecosystem.

Market context (2025):
  • BasiGo launched first electric matatu SACCO pilot July 2025:
    - 4NTE SACCO: Nyahururu–Nyeri and Nyahururu–Nakuru routes
    - Manchester SACCO: Thika–Nairobi corridor
    - 16 and 19-seater electric vans, 300 km range, 1.5 hr charge
    - Pay-As-You-Drive leasing model
  • BasiGo has 500 preorders from bus operators, 35+ buses operating in Nairobi
  • Roam Move: smaller bus, KES 20/km vs KES 50–60/km diesel
  • Opibus: assembled first electric bus in Kenya, commercial launch 2022+

VM0038 baseline for matatus:
  AFEC = 0.130 L/km diesel (AMS-III.BC minibus default)
  EV   = 0.350 kWh/km (BasiGo / Roam Move specification)
  Occupancy: 14 average passengers (Nairobi matatu avg)
  → ~350–400g CO₂ saved per km
  → ~25–28g CO₂ saved per passenger-km
"""

from __future__ import annotations

import random
from .base import FleetAdapter, FleetType, RideOffer


# Nairobi matatu route data
MATATU_ROUTES = {
    "11":  {"name": "CBD–Westlands",         "fare": 50,  "km": 4.2},
    "23":  {"name": "CBD–Karen",              "fare": 70,  "km": 16.5},
    "34":  {"name": "CBD–Githurai",           "fare": 60,  "km": 14.0},
    "44":  {"name": "CBD–South B",            "fare": 50,  "km": 5.8},
    "58":  {"name": "CBD–Kasarani",           "fare": 65,  "km": 13.0},
    "100": {"name": "CBD–Kikuyu",             "fare": 80,  "km": 20.0},
    "237": {"name": "CBD–Ruiru",              "fare": 90,  "km": 25.0},
    "105": {"name": "Thika–Nairobi",          "fare": 130, "km": 45.0},
    "76":  {"name": "Nyahururu–Nyeri",        "fare": 350, "km": 100.0},
    "77":  {"name": "Nyahururu–Nakuru",       "fare": 300, "km": 85.0},
}


class BasiGoMatatuAdapter(FleetAdapter):
    """
    BasiGo electric matatu — Pay-As-You-Drive SACCO model.

    Partnerships: 4NTE SACCO, Manchester Travellers Coach, plus
                  500+ preorders from Nairobi bus operators.
    Bus spec:     BasiGo P8 — 16/19-seater, 300 km range, 1.5 hr charge.
                  Assembled in Kenya from CHTC (China) CKD kits.
    Pricing:      Fixed route fares (NTSA-regulated PSV)
    API:          No public API — route-based price model
    """

    PROVIDER_NAME    = "BasiGo Matatu"
    PROVIDER_SLUG    = "basigo_matatu"
    FLEET_TYPE       = FleetType.MATATU
    COLOR            = "#16a34a"
    RIDE_TYPE        = "BasiGo Electric Matatu"
    EV_MODEL         = "BasiGo P8 (16/19-seater)"
    EV_MANUFACTURER  = "BasiGo Kenya / CHTC"
    BASE_FARE_KES    = 50.0
    RATE_PER_KM_KES  = 5.0              # regulated PSV fare ~KES 5/km
    DELIVERY_RANGE   = (5, 20)          # wait at stage
    SEATS            = 16
    OCCUPANCY_AVG    = 14.0             # avg Nairobi matatu occupancy
    BATTERY_SWAP     = False
    RANGE_KM         = 300.0
    EV_KWH_PER_KM    = 0.350            # BasiGo P8 spec
    AFEC_BASELINE    = 0.130            # diesel minibus AMS-III.BC
    BOOKING_DEEP_LINK = (
        "https://basigo.africa/ride"
        "?pickup_lat={pickup_lat}&pickup_lon={pickup_lon}"
        "&drop_lat={drop_lat}&drop_lon={drop_lon}"
    )

    # Active SACCOs
    SACCOS = ["4NTE SACCO", "Manchester SACCO", "Citi Hoppa", "KBS", "Metro Trans"]

    def get_offers(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
        max_results: int = 1,
    ) -> list[RideOffer]:
        offers = []
        # Select relevant routes based on proximity
        routes = list(MATATU_ROUTES.items())
        random.shuffle(routes)

        for route_id, route in routes[:max_results]:
            offer = self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, len(offers))
            offer.price_kes    = route["fare"]
            offer.route_id     = route_id
            offer.route_name   = route["name"]
            offer.sacco_name   = random.choice(self.SACCOS)
            offer.duration_min = max(15, int(route["km"] / 25 * 60))
            offer.badge        = "🚐 SACCO Electric"
            offer.frequency_min = random.randint(8, 25)
            offers.append(offer)

        return offers or [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, 0)]


class RoamMoveAdapter(FleetAdapter):
    """
    Roam Move — Roam Electric's matatu-segment electric bus.
    Competes directly with diesel matatus.
    Running cost: KES 20/km vs KES 50–60/km for diesel equivalent.
    Assembled in Kenya by Roam Electric (formerly Opibus).
    """

    PROVIDER_NAME    = "Roam Move"
    PROVIDER_SLUG    = "roam_move"
    FLEET_TYPE       = FleetType.MATATU
    COLOR            = "#f97316"
    RIDE_TYPE        = "Roam Move Electric Bus"
    EV_MODEL         = "Roam Move (14-seater)"
    EV_MANUFACTURER  = "Roam Electric (Kenya)"
    BASE_FARE_KES    = 55.0
    RATE_PER_KM_KES  = 5.5
    DELIVERY_RANGE   = (8, 25)
    SEATS            = 14
    OCCUPANCY_AVG    = 12.0
    BATTERY_SWAP     = False
    RANGE_KM         = 200.0
    EV_KWH_PER_KM    = 0.300
    AFEC_BASELINE    = 0.130
    BOOKING_DEEP_LINK = (
        "https://roamelectric.com/move"
        "?lat={pickup_lat}&lon={pickup_lon}"
        "&dlat={drop_lat}&dlon={drop_lon}"
    )

    SACCOS = ["Roam SACCO", "Forward Travelers", "Double M", "Stagecoach"]

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = []
        routes = list(MATATU_ROUTES.items())
        random.shuffle(routes)
        for route_id, route in routes[:max_results]:
            offer = self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, len(offers))
            offer.price_kes   = int(route["fare"] * 1.1)   # slight premium
            offer.route_id    = route_id
            offer.route_name  = route["name"]
            offer.sacco_name  = random.choice(self.SACCOS)
            offer.badge       = "🇰🇪 Roam Electric"
            offer.frequency_min = random.randint(10, 30)
            offers.append(offer)
        return offers or [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, 0)]


class OpibusMatatuAdapter(FleetAdapter):
    """
    Opibus Electric Matatu — Opibus conversion (diesel → electric).
    Opibus launched Kenya's first electric bus commercially and
    has converted existing diesel matatu bodies to electric drivetrains,
    making electrification accessible to existing SACCO fleets.
    """

    PROVIDER_NAME    = "Opibus Matatu"
    PROVIDER_SLUG    = "opibus_matatu"
    FLEET_TYPE       = FleetType.MATATU
    COLOR            = "#0369a1"
    RIDE_TYPE        = "Opibus Electric Matatu"
    EV_MODEL         = "Opibus Electric Conversion (26-seater)"
    EV_MANUFACTURER  = "Opibus Kenya"
    BASE_FARE_KES    = 60.0
    RATE_PER_KM_KES  = 5.5
    DELIVERY_RANGE   = (10, 30)
    SEATS            = 26
    OCCUPANCY_AVG    = 20.0
    BATTERY_SWAP     = False
    RANGE_KM         = 250.0
    EV_KWH_PER_KM    = 0.400
    AFEC_BASELINE    = 0.130
    BOOKING_DEEP_LINK = (
        "https://opibus.com/ride"
        "?pickup_lat={pickup_lat}&pickup_lon={pickup_lon}"
        "&drop_lat={drop_lat}&drop_lon={drop_lon}"
    )

    SACCOS = ["City Bus SACCO", "Umoinner SACCO", "Nairobi Transport", "2NK SACCO"]

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = []
        routes = list(MATATU_ROUTES.items())
        random.shuffle(routes)
        for route_id, route in routes[:max_results]:
            offer = self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, len(offers))
            offer.price_kes   = route["fare"]
            offer.route_id    = route_id
            offer.route_name  = route["name"]
            offer.sacco_name  = random.choice(self.SACCOS)
            offer.badge       = "🔋 Diesel→EV Conversion"
            offer.frequency_min = random.randint(15, 40)
            offers.append(offer)
        return offers or [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, 0)]
