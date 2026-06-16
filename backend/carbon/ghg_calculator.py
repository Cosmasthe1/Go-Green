"""
ghg_calculator.py — Go Green Carbon Credit Engine 🌿
────────────────────────────────────────────────────────────────────────────
Core GHG emission reduction calculator implementing Verra VM0038 v1.0.

Covers all fleet categories:
  Transport  : E-Bike, PSV Car, Minibus, Transit Bus, Light/Heavy Truck
  Construction: Excavator, Wheel Loader, Crane, Forklift

VM0038 Core Formula (per monitoring period y):
  ER_y = BE_y - PE_y - LE_y

  BE_y = Σ [VKT_i,y × AFEC_i,y × EF_fuel_i × WTT_i]        Baseline Emissions
  PE_y = Σ [EC_j,y / η_j] × EF_grid_y                         Project Emissions
  LE_y = ER_y × leakage_pct                                    Leakage
  VCU_y = ER_y × NET_VCU_FACTOR                                Verified Carbon Units

Where:
  VKT     = Vehicle kilometres travelled
  AFEC    = Adjusted fuel economy coefficient (L/km)
  EF_fuel = Fuel CO2 emission factor (kgCO2e/L)
  WTT     = Well-to-tank upstream multiplier
  EC      = Electricity consumed at charger (kWh)
  η       = Charger efficiency
  EF_grid = Grid electricity emission factor (tCO2e/kWh)
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .verra_constants import (
    CHARGER_EFFICIENCY,
    CHARGER_SPECS,
    CONSTRUCTION_PARAMS,
    EF_DIESEL_KG_PER_L,
    EF_GRID_KENYA_KG_PER_KWH,
    EF_GRID_KENYA_TCO2_PER_KWH,
    EF_PETROL_KG_PER_L,
    LEAKAGE_DISCOUNT_PCT,
    NET_VCU_FACTOR,
    VCU_PRICE_KES,
    VCU_PRICE_USD,
    VCS_BUFFER_PCT,
    VEHICLE_PARAMS,
    VehicleCategory,
    WTT_DIESEL,
    WTT_PETROL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TripCarbonResult:
    """Carbon credit result for a single EV trip (VM0038 per-VKT basis)."""

    # Inputs
    vehicle_category:     VehicleCategory
    distance_km:          float
    charger_type:         str
    vehicle_label:        str
    vehicle_icon:         str

    # VM0038 components (kgCO2e)
    baseline_emissions_kg:  float   # BE — what ICE would have emitted
    project_emissions_kg:   float   # PE — grid electricity emissions
    gross_reduction_kg:     float   # BE - PE
    leakage_kg:             float   # LE
    net_reduction_kg:       float   # ER = BE - PE - LE

    # VCU outputs
    gross_vcu:            float     # tCO2e before buffer
    net_vcu:              float     # tCO2e after leakage + buffer (tradeable)
    vcu_value_usd:        float
    vcu_value_kes:        float

    # Context
    trees_equivalent:     float     # 1 tCO2 ≈ 45 trees/year
    km_driven_ice_equiv:  float     # km an ICE car would need to offset this
    petrol_saved_litres:  float     # hypothetical petrol not burned

    # Methodology reference
    methodology:          str = "Verra VM0038 v1.0"
    additionality:        str = "VMD0049 positive list — Kenya EV penetration <5%"

    def to_dict(self) -> dict:
        return {k: (v.value if isinstance(v, VehicleCategory) else v)
                for k, v in self.__dict__.items()}


@dataclass
class FleetCarbonResult:
    """Aggregated carbon credit result for a fleet over a monitoring period."""

    fleet_name:           str
    period_label:         str        # e.g. "2025 Q1"
    vehicles:             list[dict] # per-vehicle breakdown

    # Totals
    total_vkt_km:         float
    total_baseline_tco2:  float
    total_project_tco2:   float
    total_leakage_tco2:   float
    total_net_reduction_tco2: float
    gross_vcu:            float
    net_vcu:              float      # tradeable Verified Carbon Units
    vcu_value_usd:        float
    vcu_value_kes:        float

    # Breakdown
    by_category:          dict[str, float]   # category → net tCO2e
    by_charger:           dict[str, float]   # charger type → tCO2e

    methodology:          str = "Verra VM0038 v1.0 + VMR0004 v2.0"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ConstructionCarbonResult:
    """Carbon result for construction machinery (VMR0004 v2.0 / AMS-III.BC)."""

    machine_category:     VehicleCategory
    machine_label:        str
    operating_hours:      float

    baseline_diesel_l:    float
    baseline_emissions_kg: float
    project_emissions_kg:  float
    net_reduction_kg:      float
    net_vcu:               float
    vcu_value_usd:         float
    vcu_value_kes:         float

    methodology:           str = "Verra VMR0004 v2.0 + AMS-III.BC"

    def to_dict(self) -> dict:
        return {k: (v.value if isinstance(v, VehicleCategory) else v)
                for k, v in self.__dict__.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Core calculator
# ─────────────────────────────────────────────────────────────────────────────

class GHGCalculator:
    """
    Verra VM0038 v1.0 GHG emission reduction calculator.

    All transport vehicles use the VKT (vehicle-km-travelled) approach.
    Construction machinery uses the operating-hours approach (VMR0004 v2.0).
    """

    # ── Per-trip calculation (primary Go Green use case) ─────────────────────

    @staticmethod
    def calculate_trip(
        vehicle_category: VehicleCategory,
        distance_km:      float,
        charger_type:     Optional[str] = None,
        electricity_kwh:  Optional[float] = None,
    ) -> TripCarbonResult:
        """
        Calculate GHG emission reductions for a single EV trip.

        VM0038 equations applied:
          BE = distance_km × AFEC × EF_fuel × WTT_factor          (kgCO2e)
          PE = (electricity_kwh / charger_efficiency) × EF_grid    (kgCO2e)
          ER = BE - PE                                              (kgCO2e)
          LE = ER × leakage_pct
          Net ER = ER - LE

        Parameters
        ----------
        vehicle_category : VehicleCategory enum
        distance_km      : km driven as EV
        charger_type     : "L1" | "L2" | "DCFC" (default from vehicle params)
        electricity_kwh  : actual metered kWh (if None, estimated from ev_kwh_per_km)
        """
        if vehicle_category in (
            VehicleCategory.CONSTRUCTION_EXCAVATOR,
            VehicleCategory.CONSTRUCTION_LOADER,
            VehicleCategory.CONSTRUCTION_CRANE,
            VehicleCategory.CONSTRUCTION_FORKLIFT,
        ):
            raise ValueError(
                "Use calculate_construction() for construction machinery categories."
            )

        params = VEHICLE_PARAMS[vehicle_category]
        charger = charger_type or params.charger_type

        # ── Baseline Emissions (BE) ───────────────────────────────────────────
        ef_fuel = (EF_PETROL_KG_PER_L if params.fuel_type == "petrol"
                   else EF_DIESEL_KG_PER_L)
        wtt     = WTT_PETROL if params.fuel_type == "petrol" else WTT_DIESEL
        be_kg   = distance_km * params.afec_l_per_km * ef_fuel * wtt

        # ── Project Emissions (PE) ────────────────────────────────────────────
        # Energy consumed at charger (metered or estimated)
        if electricity_kwh is None:
            electricity_kwh = distance_km * params.ev_kwh_per_km

        η     = CHARGER_EFFICIENCY.get(charger, 0.90)
        pe_kg = (electricity_kwh / η) * EF_GRID_KENYA_KG_PER_KWH

        # ── Gross reduction ───────────────────────────────────────────────────
        gross_kg = max(be_kg - pe_kg, 0.0)

        # ── Leakage (LE) ─────────────────────────────────────────────────────
        leakage_kg = gross_kg * LEAKAGE_DISCOUNT_PCT

        # ── Net reduction ─────────────────────────────────────────────────────
        net_kg  = gross_kg - leakage_kg

        # ── VCU conversion ────────────────────────────────────────────────────
        # 1 VCU = 1 tCO2e
        gross_vcu = gross_kg / 1000.0
        net_vcu   = gross_vcu * NET_VCU_FACTOR

        # ── Context metrics ───────────────────────────────────────────────────
        trees_eq      = net_vcu * 45.0          # 1 tCO2 ≈ 45 trees/yr
        km_ice_equiv  = net_kg / (params.afec_l_per_km * ef_fuel * wtt) if net_kg > 0 else 0
        petrol_saved  = distance_km * params.afec_l_per_km

        return TripCarbonResult(
            vehicle_category     = vehicle_category,
            distance_km          = round(distance_km, 3),
            charger_type         = charger,
            vehicle_label        = params.category_label,
            vehicle_icon         = params.icon,
            baseline_emissions_kg= round(be_kg,     4),
            project_emissions_kg = round(pe_kg,     4),
            gross_reduction_kg   = round(gross_kg,  4),
            leakage_kg           = round(leakage_kg,4),
            net_reduction_kg     = round(net_kg,    4),
            gross_vcu            = round(gross_vcu, 8),
            net_vcu              = round(net_vcu,   8),
            vcu_value_usd        = round(net_vcu * VCU_PRICE_USD, 6),
            vcu_value_kes        = round(net_vcu * VCU_PRICE_KES, 4),
            trees_equivalent     = round(trees_eq,  4),
            km_driven_ice_equiv  = round(km_ice_equiv, 2),
            petrol_saved_litres  = round(petrol_saved, 3),
        )

    # ── Construction machinery (VMR0004 / AMS-III.BC) ─────────────────────────

    @staticmethod
    def calculate_construction(
        machine_category: VehicleCategory,
        operating_hours:  float,
        charger_type:     Optional[str] = None,
    ) -> ConstructionCarbonResult:
        """
        VMR0004 v2.0 fuel-to-electricity displacement for non-road machinery.

        BE = operating_hours × diesel_l_per_hour × EF_diesel × WTT_diesel
        PE = (ev_kwh_per_hour × operating_hours / η) × EF_grid
        """
        if machine_category not in CONSTRUCTION_PARAMS:
            raise ValueError(f"Not a construction category: {machine_category}")

        mp     = CONSTRUCTION_PARAMS[machine_category]
        charger = charger_type or mp.charger_type
        η      = CHARGER_EFFICIENCY.get(charger, 0.923)

        baseline_l  = operating_hours * mp.diesel_l_per_hour
        be_kg       = baseline_l * EF_DIESEL_KG_PER_L * WTT_DIESEL
        ev_kwh      = operating_hours * mp.ev_kwh_per_hour
        pe_kg       = (ev_kwh / η) * EF_GRID_KENYA_KG_PER_KWH
        gross_kg    = max(be_kg - pe_kg, 0.0)
        leakage_kg  = gross_kg * LEAKAGE_DISCOUNT_PCT
        net_kg      = gross_kg - leakage_kg
        net_vcu     = (net_kg / 1000.0) * NET_VCU_FACTOR

        return ConstructionCarbonResult(
            machine_category      = machine_category,
            machine_label         = mp.label,
            operating_hours       = round(operating_hours, 2),
            baseline_diesel_l     = round(baseline_l, 2),
            baseline_emissions_kg = round(be_kg,  4),
            project_emissions_kg  = round(pe_kg,  4),
            net_reduction_kg      = round(net_kg, 4),
            net_vcu               = round(net_vcu, 8),
            vcu_value_usd         = round(net_vcu * VCU_PRICE_USD, 4),
            vcu_value_kes         = round(net_vcu * VCU_PRICE_KES, 2),
        )

    # ── Fleet-level aggregation ────────────────────────────────────────────────

    @classmethod
    def calculate_fleet(
        cls,
        fleet_name:   str,
        period_label: str,
        vehicles: list[dict],
    ) -> FleetCarbonResult:
        """
        Aggregate VM0038 results across a mixed fleet.

        Each vehicle dict:
          {
            "category":       VehicleCategory,
            "count":          int,
            "annual_km":      float,      (transport) or
            "annual_hours":   float,      (construction)
            "charger_type":   str,        optional
          }
        """
        total_vkt       = 0.0
        total_be        = 0.0
        total_pe        = 0.0
        total_le        = 0.0
        total_net       = 0.0
        by_category:    dict[str, float] = {}
        by_charger:     dict[str, float] = {}
        vehicle_rows:   list[dict]       = []

        for v in vehicles:
            cat   = v["category"]
            count = v.get("count", 1)
            params = VEHICLE_PARAMS.get(cat)

            if params and params.sector == "construction":
                hours  = v.get("annual_hours", CONSTRUCTION_PARAMS[cat].typical_hours_day * 250)
                result = cls.calculate_construction(cat, hours * count, v.get("charger_type"))
                net_tco2 = result.net_reduction_kg / 1000
                charger  = result.machine_category.value
            else:
                km     = v.get("annual_km", params.annual_km_default if params else 30_000)
                result = cls.calculate_trip(cat, km * count, v.get("charger_type"))
                net_tco2 = result.net_reduction_kg / 1000
                charger  = result.charger_type
                total_vkt += km * count

            total_be  += (result.baseline_emissions_kg if hasattr(result, "baseline_emissions_kg") else 0) / 1000
            total_pe  += (result.project_emissions_kg  if hasattr(result, "project_emissions_kg")  else 0) / 1000
            total_le  += (result.leakage_kg if hasattr(result, "leakage_kg") else
                          result.net_reduction_kg * LEAKAGE_DISCOUNT_PCT) / 1000
            total_net += net_tco2

            label = cat.value
            by_category[label] = by_category.get(label, 0) + net_tco2
            by_charger[charger]  = by_charger.get(charger, 0) + net_tco2
            vehicle_rows.append({"category": label, "count": count, "net_tco2": round(net_tco2, 4)})

        gross_vcu = total_net / NET_VCU_FACTOR
        net_vcu   = total_net

        return FleetCarbonResult(
            fleet_name              = fleet_name,
            period_label            = period_label,
            vehicles                = vehicle_rows,
            total_vkt_km            = round(total_vkt),
            total_baseline_tco2     = round(total_be,  4),
            total_project_tco2      = round(total_pe,  4),
            total_leakage_tco2      = round(total_le,  4),
            total_net_reduction_tco2= round(total_net, 4),
            gross_vcu               = round(gross_vcu, 4),
            net_vcu                 = round(net_vcu,   4),
            vcu_value_usd           = round(net_vcu * VCU_PRICE_USD, 2),
            vcu_value_kes           = round(net_vcu * VCU_PRICE_KES, 2),
            by_category             = {k: round(v, 4) for k, v in by_category.items()},
            by_charger              = {k: round(v, 4) for k, v in by_charger.items()},
        )

    # ── Annual projection ─────────────────────────────────────────────────────

    @staticmethod
    def project_annual_credits(
        vehicle_category: VehicleCategory,
        fleet_size:       int,
        annual_km_per_vehicle: Optional[float] = None,
    ) -> dict:
        """Project annual VCU earnings for a fleet of identical vehicles."""
        params  = VEHICLE_PARAMS[vehicle_category]
        ann_km  = annual_km_per_vehicle or params.annual_km_default
        result  = GHGCalculator.calculate_trip(vehicle_category, ann_km * fleet_size)

        return {
            "vehicle_category":    vehicle_category.value,
            "fleet_size":          fleet_size,
            "annual_km_total":     ann_km * fleet_size,
            "annual_net_vcu":      round(result.net_vcu, 4),
            "annual_vcu_usd":      round(result.vcu_value_usd, 2),
            "annual_vcu_kes":      round(result.vcu_value_kes, 2),
            "tco2_per_vehicle":    round(result.net_reduction_kg / fleet_size / 1000, 4),
            "monthly_vcu":         round(result.net_vcu / 12, 4),
            "crediting_7yr_vcu":   round(result.net_vcu * 7, 2),
            "crediting_7yr_usd":   round(result.vcu_value_usd * 7, 2),
        }
