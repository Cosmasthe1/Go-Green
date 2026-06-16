"""
fleet/ebike.py — Go Green E-Bike Network Adapters
═══════════════════════════════════════════════════
Four e-boda-boda adapters covering Nairobi's electric motorcycle taxi market.

Market context (2025):
  • Electric motorcycles captured 10% of new Kenyan registrations by Aug 2025
    (up from 0.5% in 2021) — Africa's fastest-growing e2W market
  • Bolt: 40% of its Nairobi motorcycle fleet electric by late 2025
  • Spiro bikes cost ~$800 vs $1,300–1,500 for petrol equivalents
  • M-KOPA: 5,000+ electric motorbike sales via PAYGO financing
  • Ecobodaa: PAYGO battery swap platform, PREO-funded, Nairobi-assembled

VM0038 baseline for all e-bikes:
  AFEC = 0.035 L/km (petrol motorbike, AMS-III.BC default)
  EV   = 0.012 kWh/km (electric motorbike WLTP range ÷ battery kWh)
  → ~50–60g CO₂ saved per km
"""

from __future__ import annotations

from .base import FleetAdapter, FleetType


class EcobodaaAdapter(FleetAdapter):
    """
    Ecobodaa — Africa's first e-boda assembled in Nairobi.
    Founded by two Kenyan engineers. PREO-funded. PAYGO battery swap.

    Pricing: competitive with petrol boda (KES 100–150 per trip, short routes)
    Battery: swappable — riders exchange depleted packs at swap shops near roads
    API:     no public API — price model + deep-link to Ecobodaa app
    """

    PROVIDER_NAME    = "Ecobodaa"
    PROVIDER_SLUG    = "ecobodaa"
    FLEET_TYPE       = FleetType.EBIKE
    COLOR            = "#00a651"          # Ecobodaa brand green
    RIDE_TYPE        = "Ecobodaa E-Boda"
    EV_MODEL         = "Ecobodaa Custom E-Motorbike"
    EV_MANUFACTURER  = "Ecobodaa (Nairobi-assembled)"
    BASE_FARE_KES    = 80.0
    RATE_PER_KM_KES  = 28.0
    DELIVERY_RANGE   = (2, 6)
    SEATS            = 1
    OCCUPANCY_AVG    = 1.2              # occasional pillion
    BATTERY_SWAP     = True
    RANGE_KM         = 80.0            # per swap
    EV_KWH_PER_KM    = 0.012
    AFEC_BASELINE    = 0.035            # petrol motorbike
    BOOKING_DEEP_LINK = (
        "https://ecobodaa.bike/ride"
        "?lat={pickup_lat}&lon={pickup_lon}"
        "&dlat={drop_lat}&dlon={drop_lon}"
    )

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, i)
                  for i in range(max_results)]
        for o in offers:
            o.badge = "🇰🇪 Nairobi-Made"
        return offers


class EBodaAdapter(FleetAdapter):
    """
    eBoda — Generic electric boda-boda network.
    Covers riders on Spiro, M-KOPA, and Mogo electric motorbikes
    operating independently or through aggregator platforms.

    Spiro bikes: ~$800 (40% cheaper than petrol equivalent)
    M-KOPA: PAYGO — riders pay daily instalments matching their earnings
    Range: 80–120 km depending on model
    """

    PROVIDER_NAME    = "eBoda"
    PROVIDER_SLUG    = "eboda"
    FLEET_TYPE       = FleetType.EBIKE
    COLOR            = "#0ea5e9"
    RIDE_TYPE        = "eBoda Electric"
    EV_MODEL         = "Spiro / M-KOPA E-Motorbike"
    EV_MANUFACTURER  = "Spiro / M-KOPA"
    BASE_FARE_KES    = 70.0
    RATE_PER_KM_KES  = 25.0             # cheapest e-boda option
    DELIVERY_RANGE   = (1, 5)
    SEATS            = 1
    OCCUPANCY_AVG    = 1.2
    BATTERY_SWAP     = False
    RANGE_KM         = 100.0
    EV_KWH_PER_KM    = 0.012
    AFEC_BASELINE    = 0.035
    BOOKING_DEEP_LINK = (
        "https://eboda.co.ke/book"
        "?pickup_lat={pickup_lat}&pickup_lon={pickup_lon}"
        "&drop_lat={drop_lat}&drop_lon={drop_lon}"
    )

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, i)
                  for i in range(max_results)]
        for o in offers:
            o.badge = "💰 Most Affordable"
        return offers


class BoltBodaAdapter(FleetAdapter):
    """
    Bolt Boda — Bolt's electric motorcycle fleet.
    By late 2025 Bolt reported 40% of its Nairobi motorcycle fleet
    operating on electric bikes, making it the city's largest EV
    ride-hailing motorcycle provider (Ethical Business Africa, Mar 2026).

    Pricing: consistent with Bolt's standard motorcycle rates in Nairobi.
    API: Bolt partner API (no public access — price model used)
    """

    PROVIDER_NAME    = "Bolt Boda"
    PROVIDER_SLUG    = "bolt_boda"
    FLEET_TYPE       = FleetType.EBIKE
    COLOR            = "#34D186"         # Bolt brand green
    RIDE_TYPE        = "Bolt E-Boda"
    EV_MODEL         = "Spiro / Ampersand E-Motorbike"
    EV_MANUFACTURER  = "Spiro / Ampersand"
    BASE_FARE_KES    = 75.0
    RATE_PER_KM_KES  = 27.0
    DELIVERY_RANGE   = (2, 7)
    SEATS            = 1
    OCCUPANCY_AVG    = 1.2
    BATTERY_SWAP     = True
    RANGE_KM         = 90.0
    EV_KWH_PER_KM    = 0.012
    AFEC_BASELINE    = 0.035
    BOOKING_DEEP_LINK = (
        "https://bolt.eu/go/ride"
        "?pickup_lat={pickup_lat}&pickup_lng={pickup_lon}"
        "&dropoff_lat={drop_lat}&dropoff_lng={drop_lon}"
        "&type=moto&source=gogreen"
    )

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, i)
                  for i in range(max_results)]
        for o in offers:
            o.badge = "⚡ 40% EV Fleet"
        return offers


class RoamBodaAdapter(FleetAdapter):
    """
    Roam Boda — Roam Electric e-motorbike taxi.
    Roam (formerly Opibus) assembles EVs in Kenya.
    Their Roam Air motorbike competes directly in the boda-boda market.
    Cost: KES 20/km to run vs KES 50–60/km for diesel equivalent.

    API: no public API — price model + Roam app deep-link
    """

    PROVIDER_NAME    = "Roam Boda"
    PROVIDER_SLUG    = "roam_boda"
    FLEET_TYPE       = FleetType.EBIKE
    COLOR            = "#f97316"         # Roam orange
    RIDE_TYPE        = "Roam E-Boda"
    EV_MODEL         = "Roam Air Electric Motorbike"
    EV_MANUFACTURER  = "Roam Electric (Kenya)"
    BASE_FARE_KES    = 85.0
    RATE_PER_KM_KES  = 30.0
    DELIVERY_RANGE   = (3, 8)
    SEATS            = 1
    OCCUPANCY_AVG    = 1.2
    BATTERY_SWAP     = False
    RANGE_KM         = 120.0
    EV_KWH_PER_KM    = 0.011            # Roam Air is efficient
    AFEC_BASELINE    = 0.035
    BOOKING_DEEP_LINK = (
        "https://roamelectric.com/ride"
        "?lat={pickup_lat}&lon={pickup_lon}"
        "&dlat={drop_lat}&dlon={drop_lon}"
    )

    def get_offers(self, pickup_lat, pickup_lon, drop_lat, drop_lon, max_results=1):
        offers = [self._make_offer(pickup_lat, pickup_lon, drop_lat, drop_lon, i)
                  for i in range(max_results)]
        for o in offers:
            o.badge = "🇰🇪 Roam Electric"
        return offers
