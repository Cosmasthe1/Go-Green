"""
verra_constants.py — Go Green Carbon Credit Engine 🌿
────────────────────────────────────────────────────────────────────────────
All constants, emission factors, and parameters derived from:

  PRIMARY METHODOLOGY
  • Verra VM0038 v1.0 — Methodology for Electric Vehicle Charging Systems
    https://verra.org/methodologies/vm0038-methodology-for-electric-vehicle-charging-systems-v1-0/

  SUPPORTING REFERENCES
  • VMD0049 — Activity Method for Determining Additionality of EV Charging Systems
  • VMR0004 v2.0 — Improved Efficiency of Fleet Vehicles (Oct 2024)
  • AMS-III.BC — CDM Small-Scale Methodology, Emission Reductions Through
                  Improved Efficiency of Vehicle Fleets
  • IPCC AR6 GWP-100 values (CH4 = 27.9, N2O = 273)
  • IEA Emission Factors 2024 (Kenya grid)
  • UNFCCC CDM Tool 03 — Tool to calculate project or leakage CO2 emissions
                          from fossil fuel combustion

Units throughout:
  • Distances   : km
  • Energy      : kWh
  • Emissions   : tCO2e (metric tonnes CO₂-equivalent)
  • Fuel        : litres (L)
  • Power       : kW
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Final


# ─────────────────────────────────────────────────────────────────────────────
# 1. GWP-100 (IPCC AR6, Table 7.SM.7)
# ─────────────────────────────────────────────────────────────────────────────

GWP_CH4: Final[float] = 27.9    # CH4 → CO2e (fossil methane)
GWP_N2O: Final[float] = 273.0   # N2O → CO2e


# ─────────────────────────────────────────────────────────────────────────────
# 2. Grid Emission Factor — Kenya (EF_grid)
#    Source: IEA Emission Factors 2024; Kenya >90% renewable electricity
#    Value: 0.061 tCO2e / MWh = 0.000061 tCO2e / kWh
#    (geothermal + hydro dominant; marginal grid factor used for conservatism)
#    VM0038 §4.2: Use country/regional grid emission factor (tCO2/MWh)
# ─────────────────────────────────────────────────────────────────────────────

EF_GRID_KENYA_TCO2_PER_KWH: Final[float] = 0.000061   # tCO2e / kWh
EF_GRID_KENYA_KG_PER_KWH:   Final[float] = 0.061      # kgCO2e / kWh

# Charging system efficiency factors (VM0038 §4.3)
CHARGER_EFFICIENCY = {
    "L1":   0.855,   # Level 1 AC (120V) — 85.5%
    "L2":   0.900,   # Level 2 AC (240V) — 90.0%
    "DCFC": 0.923,   # DC Fast Charger   — 92.3% (VM0038 default)
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Fuel emission factors (EF_fuel) — VM0038 §4.1 / IPCC 2006 Vol 2
#    Units: kgCO2e / litre
# ─────────────────────────────────────────────────────────────────────────────

EF_PETROL_KG_PER_L:   Final[float] = 2.296   # gasoline / petrol
EF_DIESEL_KG_PER_L:   Final[float] = 2.703   # diesel
EF_LPG_KG_PER_L:      Final[float] = 1.554   # liquefied petroleum gas
EF_CNG_KG_PER_KG:     Final[float] = 2.750   # compressed natural gas (per kg)

# WTT (Well-to-Tank) upstream multiplier  (DEFRA / VM0038 guidance)
WTT_PETROL: Final[float] = 1.19   # +19% upstream
WTT_DIESEL: Final[float] = 1.21   # +21% upstream


# ─────────────────────────────────────────────────────────────────────────────
# 4. Vehicle Fleet Categories & Baseline Parameters
#    VM0038 Appendix 1 / AMS-III.BC Table 1
#    AFEC = Adjusted Fuel Economy Coefficient (L or kWh per km for ICE baseline)
#    EV_CONSUMPTION = kWh per km (EV project vehicle)
# ─────────────────────────────────────────────────────────────────────────────

class VehicleCategory(str, Enum):
    """
    VM0038 / VMR0004 fleet vehicle categories supported by Go Green.
    Aligns with AMS-III.BC vehicle classifications.
    """
    E_BIKE            = "e_bike"           # Electric bicycle / e-cargo bike
    PSV_PASSENGER_CAR = "psv_passenger_car"  # PSV / taxi / ride-hail car (≤8 seats)
    MINIBUS           = "minibus"          # Matatu / minibus PSV (9-25 seats)
    TRANSIT_BUS       = "transit_bus"      # Full-size transit / BRT bus (>25 seats)
    LIGHT_TRUCK       = "light_truck"      # Light commercial vehicle / delivery van
    HEAVY_TRUCK       = "heavy_truck"      # Heavy goods vehicle
    CONSTRUCTION_EXCAVATOR = "construction_excavator"   # Excavator
    CONSTRUCTION_LOADER    = "construction_loader"      # Wheel loader
    CONSTRUCTION_CRANE     = "construction_crane"       # Tower / mobile crane
    CONSTRUCTION_FORKLIFT  = "construction_forklift"    # Forklift


@dataclass(frozen=True)
class VehicleParams:
    """
    Per-category parameters for VM0038 GHG calculation.

    afec_l_per_km        : Baseline ICE fuel consumption (L/km)
                           Source: VM0038 Appendix 1 / AMS-III.BC defaults
    fuel_type            : Primary fuel of displaced ICE vehicle
    ev_kwh_per_km        : EV energy consumption (kWh/km)
                           Source: manufacturer specs / WLTP averages
    co2_per_km_baseline  : kgCO2e/km for ICE baseline (computed = afec × EF_fuel × WTT)
    occupancy_factor     : Average passengers (for per-passenger credit calculation)
    annual_km_default    : Default annual distance for project monitoring
    charger_type         : Default charger level for this fleet type
    vcu_per_km           : Pre-computed Verified Carbon Units per km (tCO2e/km)
    category_label       : Human-readable name
    """
    afec_l_per_km:       float
    fuel_type:           str        # "petrol" | "diesel" | "lpg"
    ev_kwh_per_km:       float
    co2_per_km_baseline: float      # kgCO2e / km  (ICE)
    occupancy_factor:    float
    annual_km_default:   float
    charger_type:        str
    vcu_per_km:          float      # tCO2e saved per km driven as EV
    category_label:      str
    sector:              str        # "transport" | "construction"
    icon:                str        # emoji


# Pre-computed helper
def _baseline_co2(afec: float, fuel: str, wtt: bool = True) -> float:
    ef   = {"petrol": EF_PETROL_KG_PER_L, "diesel": EF_DIESEL_KG_PER_L, "lpg": EF_LPG_KG_PER_L}[fuel]
    mult = {"petrol": WTT_PETROL, "diesel": WTT_DIESEL, "lpg": 1.0}[fuel] if wtt else 1.0
    return round(afec * ef * mult, 6)   # kgCO2e / km

def _vcu_per_km(baseline_kgco2_per_km: float, ev_kwh_per_km: float,
                charger: str = "L2") -> float:
    """
    VM0038 core formula per km:
      ER = BE - PE  (tCO2e)
      BE = baseline_kgco2_per_km / 1000
      PE = ev_kwh_per_km * EF_grid * (1/charger_efficiency)  [tCO2e/km]
    """
    pe = ev_kwh_per_km * EF_GRID_KENYA_KG_PER_KWH / CHARGER_EFFICIENCY[charger] / 1000
    er = (baseline_kgco2_per_km / 1000) - pe
    return round(max(er, 0.0), 8)   # tCO2e / km


# ─────────────────────────────────────────────────────────────────────────────
# 5. Vehicle parameter registry (all fleet categories)
# ─────────────────────────────────────────────────────────────────────────────

_p = VehicleParams   # alias

VEHICLE_PARAMS: dict[VehicleCategory, VehicleParams] = {

    # ── E-Bike ────────────────────────────────────────────────────────────────
    # Baseline: petrol moped/motorbike (AMS-III.BC default: 0.035 L/km)
    VehicleCategory.E_BIKE: _p(
        afec_l_per_km       = 0.035,
        fuel_type           = "petrol",
        ev_kwh_per_km       = 0.010,   # typical cargo e-bike
        co2_per_km_baseline = _baseline_co2(0.035, "petrol"),
        occupancy_factor    = 1.0,
        annual_km_default   = 8_000,
        charger_type        = "L1",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.035,"petrol"), 0.010, "L1"),
        category_label      = "E-Bike / E-Cargo Bike",
        sector              = "transport",
        icon                = "🚲",
    ),

    # ── PSV Passenger Car (ride-hail / taxi) ──────────────────────────────────
    # Baseline: petrol sedan, Kenya fleet avg ~0.090 L/km (mixed city/highway)
    VehicleCategory.PSV_PASSENGER_CAR: _p(
        afec_l_per_km       = 0.090,
        fuel_type           = "petrol",
        ev_kwh_per_km       = 0.180,   # BYD Atto3 / Tesla Model 3 city
        co2_per_km_baseline = _baseline_co2(0.090, "petrol"),
        occupancy_factor    = 2.8,     # avg taxi occupancy Nairobi
        annual_km_default   = 50_000,
        charger_type        = "L2",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.090,"petrol"), 0.180, "L2"),
        category_label      = "PSV Passenger Car (Ride-Hail / Taxi)",
        sector              = "transport",
        icon                = "🚕",
    ),

    # ── Minibus (Matatu) ──────────────────────────────────────────────────────
    # Baseline: diesel minibus 0.130 L/km (AMS-III.BC Bus category)
    VehicleCategory.MINIBUS: _p(
        afec_l_per_km       = 0.130,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.350,   # Yutong E6 / BYD ebus minibus
        co2_per_km_baseline = _baseline_co2(0.130, "diesel"),
        occupancy_factor    = 14.0,    # matatu avg
        annual_km_default   = 60_000,
        charger_type        = "L2",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.130,"diesel"), 0.350, "L2"),
        category_label      = "Minibus / Matatu PSV (9–25 seats)",
        sector              = "transport",
        icon                = "🚐",
    ),

    # ── Transit Bus ───────────────────────────────────────────────────────────
    # Baseline: diesel city bus 0.350 L/km (UITP / AMS-III.BC large bus)
    VehicleCategory.TRANSIT_BUS: _p(
        afec_l_per_km       = 0.350,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.950,   # Yutong E18 BRT bus
        co2_per_km_baseline = _baseline_co2(0.350, "diesel"),
        occupancy_factor    = 60.0,    # BRT avg
        annual_km_default   = 70_000,
        charger_type        = "DCFC",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.350,"diesel"), 0.950, "DCFC"),
        category_label      = "Transit Bus / BRT (>25 seats)",
        sector              = "transport",
        icon                = "🚌",
    ),

    # ── Light Truck / Delivery Van ────────────────────────────────────────────
    VehicleCategory.LIGHT_TRUCK: _p(
        afec_l_per_km       = 0.120,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.300,
        co2_per_km_baseline = _baseline_co2(0.120, "diesel"),
        occupancy_factor    = 1.5,
        annual_km_default   = 40_000,
        charger_type        = "L2",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.120,"diesel"), 0.300, "L2"),
        category_label      = "Light Commercial / Delivery Van",
        sector              = "transport",
        icon                = "🚚",
    ),

    # ── Heavy Truck ───────────────────────────────────────────────────────────
    VehicleCategory.HEAVY_TRUCK: _p(
        afec_l_per_km       = 0.400,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 1.500,
        co2_per_km_baseline = _baseline_co2(0.400, "diesel"),
        occupancy_factor    = 2.0,
        annual_km_default   = 80_000,
        charger_type        = "DCFC",
        vcu_per_km          = _vcu_per_km(_baseline_co2(0.400,"diesel"), 1.500, "DCFC"),
        category_label      = "Heavy Goods Vehicle (Truck)",
        sector              = "transport",
        icon                = "🚛",
    ),

    # ── Construction: Excavator ───────────────────────────────────────────────
    # VMR0004 v2.0 / AMS-III.BC non-road mobile machinery
    # Baseline: diesel excavator ~0.220 L/hr operating ÷ 1.5 km/hr effective
    # Using fuel per hour → converted: ~12L/hr × 8hr/day → per-km via work hours
    # For construction machinery, VM0038 uses operating hours × fuel_rate
    VehicleCategory.CONSTRUCTION_EXCAVATOR: _p(
        afec_l_per_km       = 0.000,   # N/A — uses per-hour below
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.000,   # N/A
        co2_per_km_baseline = 0.000,   # calculated per-hour instead
        occupancy_factor    = 1.0,
        annual_km_default   = 0,
        charger_type        = "DCFC",
        vcu_per_km          = 0.0,
        category_label      = "Construction: Excavator",
        sector              = "construction",
        icon                = "⛏️",
    ),

    # ── Construction: Wheel Loader ────────────────────────────────────────────
    VehicleCategory.CONSTRUCTION_LOADER: _p(
        afec_l_per_km       = 0.000,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.000,
        co2_per_km_baseline = 0.000,
        occupancy_factor    = 1.0,
        annual_km_default   = 0,
        charger_type        = "DCFC",
        vcu_per_km          = 0.0,
        category_label      = "Construction: Wheel Loader",
        sector              = "construction",
        icon                = "🏗️",
    ),

    # ── Construction: Crane ───────────────────────────────────────────────────
    VehicleCategory.CONSTRUCTION_CRANE: _p(
        afec_l_per_km       = 0.000,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.000,
        co2_per_km_baseline = 0.000,
        occupancy_factor    = 1.0,
        annual_km_default   = 0,
        charger_type        = "DCFC",
        vcu_per_km          = 0.0,
        category_label      = "Construction: Crane",
        sector              = "construction",
        icon                = "🏗️",
    ),

    # ── Construction: Forklift ────────────────────────────────────────────────
    VehicleCategory.CONSTRUCTION_FORKLIFT: _p(
        afec_l_per_km       = 0.000,
        fuel_type           = "diesel",
        ev_kwh_per_km       = 0.000,
        co2_per_km_baseline = 0.000,
        occupancy_factor    = 1.0,
        annual_km_default   = 0,
        charger_type        = "L2",
        vcu_per_km          = 0.0,
        category_label      = "Construction: Forklift",
        sector              = "construction",
        icon                = "🏗️",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Construction machinery: fuel-based emission parameters
#    Source: VMR0004 v2.0 / EPA AP-42 / JRC (Joint Research Centre)
#    Units: diesel_l_per_hour (L/h), ev_kwh_per_hour (kWh/h)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConstructionMachineParams:
    diesel_l_per_hour:  float   # baseline diesel consumption
    ev_kwh_per_hour:    float   # electric equivalent consumption
    typical_hours_day:  float   # standard operating hours/day
    charger_type:       str
    label:              str
    icon:               str

CONSTRUCTION_PARAMS: dict[VehicleCategory, ConstructionMachineParams] = {
    VehicleCategory.CONSTRUCTION_EXCAVATOR: ConstructionMachineParams(
        diesel_l_per_hour  = 12.0,   # medium excavator (18–25 t)
        ev_kwh_per_hour    = 45.0,   # Volvo EC230 Electric equivalent
        typical_hours_day  = 8.0,
        charger_type       = "DCFC",
        label              = "Excavator (18–25 t)",
        icon               = "⛏️",
    ),
    VehicleCategory.CONSTRUCTION_LOADER: ConstructionMachineParams(
        diesel_l_per_hour  = 9.0,    # wheel loader (2–5 t bucket)
        ev_kwh_per_hour    = 32.0,   # Volvo L25 Electric
        typical_hours_day  = 8.0,
        charger_type       = "DCFC",
        label              = "Wheel Loader (2–5 t)",
        icon               = "🏗️",
    ),
    VehicleCategory.CONSTRUCTION_CRANE: ConstructionMachineParams(
        diesel_l_per_hour  = 18.0,   # mobile crane (50–100 t)
        ev_kwh_per_hour    = 65.0,
        typical_hours_day  = 8.0,
        charger_type       = "DCFC",
        label              = "Mobile Crane (50–100 t)",
        icon               = "🏗️",
    ),
    VehicleCategory.CONSTRUCTION_FORKLIFT: ConstructionMachineParams(
        diesel_l_per_hour  = 3.5,    # diesel forklift (2–5 t)
        ev_kwh_per_hour    = 8.5,    # electric forklift
        typical_hours_day  = 8.0,
        charger_type       = "L2",
        label              = "Forklift (2–5 t)",
        icon               = "🏗️",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# 7. VCU pricing & additionality
#    VMD0049 additionality positive list: Kenya EV market penetration < 5%
#    (EV penetration Kenya 2024: ~0.3% → ADDITIONAL)
# ─────────────────────────────────────────────────────────────────────────────

VCU_PRICE_USD: Final[float]  = 12.50   # conservative spot price (Verra registry avg)
VCU_PRICE_KES: Final[float]  = 1_625.0  # at 130 KES/USD

KENYA_EV_MARKET_PENETRATION: Final[float] = 0.003   # ~0.3% → additional per VMD0049
IS_ADDITIONAL:                Final[bool]  = KENYA_EV_MARKET_PENETRATION < 0.05

# VM0038 §5: Crediting period
CREDITING_PERIOD_YEARS: Final[int]  = 7    # renewable 2x (max 21 years)
VERIFICATION_FREQUENCY: Final[str]  = "annual"

# Leakage discount (VM0038 §6 — typically 0–5% for EV fleet projects)
LEAKAGE_DISCOUNT_PCT: Final[float]  = 0.03   # 3% conservative

# VCS buffer pool deduction (permanence buffer — ~10% of credits)
VCS_BUFFER_PCT: Final[float]  = 0.10

# Net VCU multiplier (after leakage & buffer)
NET_VCU_FACTOR: Final[float]  = (1 - LEAKAGE_DISCOUNT_PCT) * (1 - VCS_BUFFER_PCT)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Charging hardware network tiers
#    For fleet adoption monitoring (VM0038 §7 monitoring plan)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChargerSpec:
    level:          str
    power_kw:       float
    efficiency:     float
    install_cost_usd: float
    daily_sessions_max: int
    label:          str

CHARGER_SPECS: dict[str, ChargerSpec] = {
    "L1": ChargerSpec("L1", 1.4,  0.855, 800,    4,   "Level 1 AC (1.4 kW)"),
    "L2": ChargerSpec("L2", 7.4,  0.900, 2_500,  12,  "Level 2 AC (7.4 kW)"),
    "L2_22": ChargerSpec("L2_22", 22.0, 0.900, 5_000, 20, "Level 2 AC (22 kW)"),
    "DCFC_50":  ChargerSpec("DCFC_50",  50.0,  0.923, 25_000, 30, "DC Fast Charger (50 kW)"),
    "DCFC_150": ChargerSpec("DCFC_150", 150.0, 0.923, 60_000, 40, "DC Fast Charger (150 kW)"),
}
