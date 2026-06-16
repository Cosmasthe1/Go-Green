"""
fleet/vm0038_ext.py — Go Green
════════════════════════════════════════════════════════════════════════════
Verra VM0038 v1.0 + VMR0004 v2.0 parameters for expanded fleet categories.

Extends carbon/verra_constants.py with:
  • E-Bike / E-Boda          (AMS-III.BC motorbike baseline)
  • Electric Matatu (SACCO)  (AMS-III.BC minibus baseline)
  • BRT Electric Bus         (AMS-III.BC large bus baseline)

All values cited from:
  VM0038 v1.0  Appendix 1 — default AFEC values by vehicle category
  AMS-III.BC   Table 1   — emission factor defaults
  IPCC 2006    Vol.2     — EF_fuel
  IEA 2024               — Kenya grid EF = 0.061 kgCO₂e/kWh
  WLTP / manufacturer datasheets for EV energy consumption
════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


# ── Grid & fuel emission factors ─────────────────────────────────────────────
EF_GRID_KENYA:  Final[float] = 0.061     # kgCO₂e/kWh   IEA 2024
EF_PETROL:      Final[float] = 2.296     # kgCO₂e/L     IPCC 2006
EF_DIESEL:      Final[float] = 2.703     # kgCO₂e/L     IPCC 2006
WTT_PETROL:     Final[float] = 1.19      # well-to-tank multiplier
WTT_DIESEL:     Final[float] = 1.21
ETA_L1:         Final[float] = 0.855     # L1 charger efficiency
ETA_L2:         Final[float] = 0.900     # L2 charger efficiency
ETA_DCFC:       Final[float] = 0.923     # DC fast charger
LEAKAGE:        Final[float] = 0.03      # 3% leakage
VCS_BUFFER:     Final[float] = 0.10      # 10% VCS buffer pool
NET_FACTOR:     Final[float] = (1 - LEAKAGE) * (1 - VCS_BUFFER)   # 0.873
VCU_PRICE_KES:  Final[float] = 1625.0    # ~$12.50 @ 130 KES/USD


class FleetCategory(str, Enum):
    """Extended fleet categories for VM0038 calculations."""
    # E-bikes
    EBIKE_MOTORBIKE  = "ebike_motorbike"    # standard e-boda boda
    EBIKE_CARGO      = "ebike_cargo"         # cargo e-bike / delivery
    # Matatus
    MATATU_MINIBUS   = "matatu_minibus"      # 9–19 seats
    MATATU_MIDIBUS   = "matatu_midibus"      # 20–35 seats
    # BRT buses
    BRT_STANDARD     = "brt_standard"        # standard BRT bus (80 seats)
    BRT_ARTICULATED  = "brt_articulated"     # articulated BRT (120 seats)
    # Existing (from verra_constants.py)
    PSV_PASSENGER_CAR = "psv_passenger_car"


@dataclass(frozen=True)
class FleetCarbonParams:
    """
    VM0038 carbon parameters for a fleet category.

    afec_l_per_km      : baseline ICE fuel consumption (L/km) — VM0038 Appendix 1
    fuel_type          : "petrol" | "diesel"
    ev_kwh_per_km      : EV energy consumption (kWh/km) — WLTP / manufacturer
    charger_type       : "L1" | "L2" | "DCFC"
    occupancy_avg      : average passengers (for per-pax CO₂)
    annual_km_default  : default annual VKT for fleet modelling
    category_label     : human-readable name
    icon               : emoji
    """
    afec_l_per_km:      float
    fuel_type:          str
    ev_kwh_per_km:      float
    charger_type:       str
    occupancy_avg:      float
    annual_km_default:  float
    category_label:     str
    icon:               str

    @property
    def ef_fuel(self) -> float:
        return EF_PETROL if self.fuel_type == "petrol" else EF_DIESEL

    @property
    def wtt(self) -> float:
        return WTT_PETROL if self.fuel_type == "petrol" else WTT_DIESEL

    @property
    def eta(self) -> float:
        return {"L1": ETA_L1, "L2": ETA_L2, "DCFC": ETA_DCFC}.get(self.charger_type, ETA_L2)

    def baseline_kg_per_km(self) -> float:
        """BE per km (kgCO₂e/km) — ICE baseline."""
        return self.afec_l_per_km * self.ef_fuel * self.wtt

    def project_kg_per_km(self) -> float:
        """PE per km (kgCO₂e/km) — EV project."""
        return (self.ev_kwh_per_km / self.eta) * EF_GRID_KENYA

    def net_kg_per_km(self) -> float:
        """Net ER per km (kgCO₂e/km) after leakage."""
        gross = max(self.baseline_kg_per_km() - self.project_kg_per_km(), 0.0)
        return gross * (1 - LEAKAGE)

    def vcu_per_km(self) -> float:
        """Tradeable VCUs per km (tCO₂e/km) after VCS buffer."""
        return (self.net_kg_per_km() / 1000.0) * (1 - VCS_BUFFER)

    def co2_saved_per_pax_km(self) -> float:
        """Grams CO₂ saved per passenger-km."""
        return (self.net_kg_per_km() * 1000) / max(self.occupancy_avg, 1)


# ── Fleet parameter registry ──────────────────────────────────────────────────

FLEET_VM0038_PARAMS: dict[FleetCategory, FleetCarbonParams] = {

    # ── E-Bike / E-Boda ───────────────────────────────────────────────────────
    # Baseline: petrol motorbike (AMS-III.BC default 0.035 L/km)
    # EV: Spiro / Roam Air motorbike (~0.012 kWh/km WLTP)
    FleetCategory.EBIKE_MOTORBIKE: FleetCarbonParams(
        afec_l_per_km     = 0.035,
        fuel_type         = "petrol",
        ev_kwh_per_km     = 0.012,
        charger_type      = "L1",
        occupancy_avg     = 1.2,           # rider + occasional pillion
        annual_km_default = 20_000,        # Nairobi boda avg ~55 km/day
        category_label    = "E-Bike / E-Boda Boda",
        icon              = "🏍️",
    ),

    # ── E-Cargo Bike ──────────────────────────────────────────────────────────
    # Baseline: petrol delivery motorbike (0.040 L/km loaded)
    FleetCategory.EBIKE_CARGO: FleetCarbonParams(
        afec_l_per_km     = 0.040,
        fuel_type         = "petrol",
        ev_kwh_per_km     = 0.015,
        charger_type      = "L1",
        occupancy_avg     = 1.0,
        annual_km_default = 15_000,
        category_label    = "E-Cargo Bike",
        icon              = "📦",
    ),

    # ── Matatu Minibus (9–19 seats) ───────────────────────────────────────────
    # Baseline: diesel minibus (AMS-III.BC 0.130 L/km)
    # EV: BasiGo P8 / Roam Move (~0.350 kWh/km manufacturer spec)
    FleetCategory.MATATU_MINIBUS: FleetCarbonParams(
        afec_l_per_km     = 0.130,
        fuel_type         = "diesel",
        ev_kwh_per_km     = 0.350,
        charger_type      = "L2",
        occupancy_avg     = 14.0,          # Nairobi matatu avg
        annual_km_default = 60_000,        # ~165 km/day per vehicle
        category_label    = "Electric Matatu (SACCO) — 9–19 seats",
        icon              = "🚐",
    ),

    # ── Matatu Midibus (20–35 seats) ──────────────────────────────────────────
    # Baseline: diesel midibus 0.180 L/km
    # EV: Opibus / CHTC conversion ~0.480 kWh/km
    FleetCategory.MATATU_MIDIBUS: FleetCarbonParams(
        afec_l_per_km     = 0.180,
        fuel_type         = "diesel",
        ev_kwh_per_km     = 0.480,
        charger_type      = "L2",
        occupancy_avg     = 25.0,
        annual_km_default = 55_000,
        category_label    = "Electric Matatu Midibus — 20–35 seats",
        icon              = "🚌",
    ),

    # ── BRT Standard Bus ──────────────────────────────────────────────────────
    # Baseline: diesel city bus (AMS-III.BC large bus 0.350 L/km)
    # EV: Roam Rapid / BasiGo full-size ~0.950 kWh/km
    FleetCategory.BRT_STANDARD: FleetCarbonParams(
        afec_l_per_km     = 0.350,
        fuel_type         = "diesel",
        ev_kwh_per_km     = 0.950,
        charger_type      = "DCFC",
        occupancy_avg     = 60.0,          # BRT design load factor
        annual_km_default = 70_000,        # ~192 km/day BRT operation
        category_label    = "BRT Electric Bus — Standard (80 seats)",
        icon              = "🚎",
    ),

    # ── BRT Articulated Bus ───────────────────────────────────────────────────
    FleetCategory.BRT_ARTICULATED: FleetCarbonParams(
        afec_l_per_km     = 0.480,
        fuel_type         = "diesel",
        ev_kwh_per_km     = 1.400,
        charger_type      = "DCFC",
        occupancy_avg     = 100.0,
        annual_km_default = 60_000,
        category_label    = "BRT Articulated Electric Bus (120 seats)",
        icon              = "🚎",
    ),

    # ── PSV Passenger Car (from existing system, repeated here for completeness)
    FleetCategory.PSV_PASSENGER_CAR: FleetCarbonParams(
        afec_l_per_km     = 0.090,
        fuel_type         = "petrol",
        ev_kwh_per_km     = 0.180,
        charger_type      = "L2",
        occupancy_avg     = 2.8,
        annual_km_default = 50_000,
        category_label    = "PSV Passenger Car / Ride-Hail",
        icon              = "🚕",
    ),
}


def get_carbon_params(category: FleetCategory) -> FleetCarbonParams:
    """Look up VM0038 parameters for a fleet category."""
    if category not in FLEET_VM0038_PARAMS:
        raise KeyError(f"No VM0038 params for category: {category}")
    return FLEET_VM0038_PARAMS[category]


def calculate_trip_carbon(
    category:    FleetCategory,
    distance_km: float,
) -> dict:
    """
    Calculate VM0038 GHG reductions for a single trip.
    Returns a dict compatible with the existing CarbonAgent.
    """
    p = get_carbon_params(category)
    be_kg   = p.baseline_kg_per_km() * distance_km
    pe_kg   = p.project_kg_per_km()  * distance_km
    gross   = max(be_kg - pe_kg, 0.0)
    leak_kg = gross * LEAKAGE
    net_kg  = gross - leak_kg
    vcu     = (net_kg / 1000.0) * (1 - VCS_BUFFER)

    return {
        "vehicle_category":       category.value,
        "category_label":         p.category_label,
        "distance_km":            round(distance_km, 3),
        "baseline_emissions_kg":  round(be_kg,  4),
        "project_emissions_kg":   round(pe_kg,  4),
        "gross_reduction_kg":     round(gross,  4),
        "leakage_kg":             round(leak_kg,4),
        "net_reduction_kg":       round(net_kg, 4),
        "gross_vcu":              round(vcu / NET_FACTOR, 8),
        "net_vcu":                round(vcu,    8),
        "vcu_value_kes":          round(vcu * VCU_PRICE_KES, 4),
        "trees_equivalent":       round(vcu * 45, 4),
        "co2_saved_per_pax_g":    round(p.co2_saved_per_pax_km() * distance_km, 2),
        "methodology":            "Verra VM0038 v1.0",
        "charger_type":           p.charger_type,
    }


def project_fleet_annual_vcu(
    category:             FleetCategory,
    fleet_size:           int,
    annual_km_per_vehicle: float | None = None,
) -> dict:
    """Project annual VCU earnings for a homogeneous fleet."""
    p      = get_carbon_params(category)
    km     = annual_km_per_vehicle or p.annual_km_default
    total  = calculate_trip_carbon(category, km * fleet_size)
    return {
        "category":          category.value,
        "fleet_size":        fleet_size,
        "annual_km_total":   km * fleet_size,
        "annual_net_vcu":    round(total["net_vcu"], 4),
        "annual_vcu_kes":    round(total["vcu_value_kes"], 2),
        "vcu_per_vehicle":   round(total["net_vcu"] / fleet_size, 6),
        "co2_kg_per_km":     round(p.net_kg_per_km(), 5),
        "co2_per_pax_g_km":  round(p.co2_saved_per_pax_km(), 3),
        "7yr_total_vcu":     round(total["net_vcu"] * 7, 3),
        "7yr_value_kes":     round(total["vcu_value_kes"] * 7, 2),
    }
