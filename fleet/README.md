# 🌿 Go Green — Expanded Fleet Module

> **E-Bikes · Matatu SACCOs · BRT Routes · Verra VM0038 Carbon Credits**

Adds 10 new fleet adapters to Go Green, covering every major electric transport category in Nairobi.

---

## Fleet Categories Added

### E-Bike Networks (4 adapters)

| Provider | Model | Notes |
|----------|-------|-------|
| **Ecobodaa** | Ecobodaa Custom E-Motorbike | Nairobi-assembled, PREO-funded, PAYGO battery swap |
| **eBoda** | Spiro / M-KOPA E-Motorbike | Cheapest option; M-KOPA PAYGO financing |
| **Bolt Boda** | Spiro / Ampersand | 40% of Bolt's Nairobi moto fleet electric (2025) |
| **Roam Boda** | Roam Air | Kenyan-assembled by Roam Electric; 120 km range |

**VM0038 baseline:** petrol motorbike AFEC = 0.035 L/km · EV = 0.012 kWh/km → ~50–60g CO₂/km saved

---

### Matatu SACCOs — Electric (3 adapters)

| Provider | Model | SACCO Partners |
|----------|-------|----------------|
| **BasiGo Matatu** | BasiGo P8 (16/19-seat) | 4NTE SACCO, Manchester SACCO — launched Jul 2025 |
| **Roam Move** | Roam Move (14-seat) | Roam SACCO, Forward Travelers |
| **Opibus Matatu** | Opibus Conversion (26-seat) | City Bus, Umoinner SACCO |

**Context:** BasiGo launched Kenya's first electric SACCO pilot in July 2025 on Nyahururu–Nyeri, Nyahururu–Nakuru, and Thika–Nairobi corridors. 500+ preorders, 35+ buses already operating in Nairobi.

**VM0038 baseline:** diesel minibus AFEC = 0.130 L/km · EV = 0.350 kWh/km → ~350g CO₂/km, ~25g CO₂/passenger-km

---

### BRT Routes — NAMATA Electric (3 adapters)

| Route | Corridor | Status |
|-------|----------|--------|
| **Ndovu (Line 1)** | Kangemi ↔ Imara Daima via CBD | Service planning complete |
| **Line 2** | Githurai ↔ CBD | EU/Team Europe financed; e-bus consultant procured Nov 2024–Jul 2025 |
| **Kifaru (Line 4)** | Jogoo Road corridor | Detailed service planning underway |

**VM0038 baseline:** diesel city bus AFEC = 0.350 L/km · EV = 0.950 kWh/km → ~1,009g CO₂/km, ~16.8g CO₂/passenger-km

---

## File Structure

```
fleet/
├── __init__.py           Module exports
├── base.py               FleetAdapter base class + RideOffer model
├── ebike.py              Ecobodaa, eBoda, BoltBoda, RoamBoda adapters
├── matatu.py             BasiGo, RoamMove, Opibus SACCO adapters
├── brt.py                NAMATA BRT Ndovu, Line 2, Kifaru adapters
├── vm0038_ext.py         VM0038 parameters for all new fleet categories
├── registry.py           Unified parallel fleet registry + scoring
└── orchestrator_patch.py One-line patch for GoGreenOrchestrator
```

---

## VM0038 Parameters Summary

| Category | AFEC (L/km) | EV (kWh/km) | Occupancy | CO₂/km saved | CO₂/pax-km |
|----------|------------|-------------|-----------|--------------|------------|
| E-Boda Boda | 0.035 petrol | 0.012 | 1.2 | ~52g | ~43g |
| E-Cargo Bike | 0.040 petrol | 0.015 | 1.0 | ~60g | ~60g |
| Matatu (9–19 seats) | 0.130 diesel | 0.350 | 14.0 | ~351g | ~25g |
| Matatu Midibus | 0.180 diesel | 0.480 | 25.0 | ~492g | ~20g |
| BRT Standard (80 seats) | 0.350 diesel | 0.950 | 60.0 | ~1,009g | ~16.8g |
| BRT Articulated (120 seats) | 0.480 diesel | 1.400 | 100.0 | ~1,376g | ~13.8g |

---

## Setup — Two Lines

```python
# In app.py, before GoGreenOrchestrator() is instantiated:
from fleet.orchestrator_patch import patch_orchestrator
from orchestrator_agent import GoGreenOrchestrator

patch_orchestrator(GoGreenOrchestrator, mode="append")
```

`mode="append"` keeps existing ride-hail providers (Uber, Bolt, etc.) and adds all new fleet types.  
`mode="replace"` uses only the new fleet registry.

---

## Filtering by Fleet Type

```python
from fleet import FleetType
from fleet.orchestrator_patch import patch_orchestrator

# Only add e-bikes and matatus, not BRT
patch_orchestrator(
    GoGreenOrchestrator,
    mode="append",
    fleet_types=[FleetType.EBIKE, FleetType.MATATU],
)
```

---

## Direct Usage

```python
from fleet import get_fleet_offers, FleetType

# All fleet types
offers = get_fleet_offers(-1.2636, 36.8030, -1.3180, 36.7070)
for o in offers:
    print(f"{o.provider:<20} {o.ride_type:<30} KSh {o.price_kes:>6,.0f}  "
          f"🌱 {o.co2_saved_g:.0f}g  {o.badge}")

# E-bikes only
ebike_offers = get_fleet_offers(
    -1.2636, 36.8030, -1.3180, 36.7070,
    fleet_types=[FleetType.EBIKE],
)

# VM0038 projection for a matatu SACCO fleet
from fleet.vm0038_ext import project_fleet_annual_vcu, FleetCategory
projection = project_fleet_annual_vcu(FleetCategory.MATATU_MINIBUS, fleet_size=50)
print(f"50 electric matatus → {projection['annual_net_vcu']:.2f} VCUs/yr "
      f"(KSh {projection['annual_vcu_kes']:,.0f})")
```

---

## Carbon Credit Projections (illustrative)

| Fleet | Size | Annual VCUs | Annual KES |
|-------|------|-------------|------------|
| 100 e-boda riders | 100 | ~4.0 | ~6,500 |
| 20 BasiGo matatus | 20 | ~148 | ~240,350 |
| 5 NAMATA BRT buses | 5 | ~243 | ~394,875 |
| Mixed (50 boda + 10 matatu + 2 BRT) | 62 | ~152 | ~246,750 |

---

## References

- [BasiGo Kenya](https://basigo.africa) — electric matatu launch Jul 2025
- [Roam Electric](https://roamelectric.com) — Roam Air, Roam Move
- [Ecobodaa](https://ecobodaa.bike) — Nairobi-assembled e-boda, PREO-funded
- [NAMATA BRT](https://namata.go.ke) — Nairobi Metropolitan Area BRT
- [Bolt Africa EV](https://blog.bolt.eu) — 40% EV motorcycle fleet 2025
- [VM0038 v1.0](https://verra.org/methodologies/vm0038-methodology-for-electric-vehicle-charging-systems-v1-0/)
- [AMS-III.BC](https://cdm.unfccc.int/methodologies) — fleet vehicle efficiency
