"""
carbon_agent.py — Go Green Carbon Credit Engine 🌿
────────────────────────────────────────────────────────────────────────────
AI agent that wraps the GHG calculator, provides natural language explanations,
generates Verra-compliant monitoring reports, and answers carbon credit queries.

Integrates with the Go Green orchestrator so every completed EV trip
automatically accrues verified carbon credits to the rider's account.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base_agent import BaseAgent, LongTermMemory
from carbon.ghg_calculator import GHGCalculator
from carbon.verra_constants import (
    CREDITING_PERIOD_YEARS, IS_ADDITIONAL, NET_VCU_FACTOR,
    VCU_PRICE_KES, VCU_PRICE_USD, VEHICLE_PARAMS,
    VehicleCategory, CONSTRUCTION_PARAMS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Rider carbon ledger
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CarbonLedgerEntry:
    entry_id:         str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trip_id:          str   = ""
    phone:            str   = ""
    timestamp:        float = field(default_factory=time.time)
    vehicle_category: str   = ""
    distance_km:      float = 0.0
    net_vcu:          float = 0.0        # tCO2e
    vcu_value_kes:    float = 0.0
    baseline_kg:      float = 0.0
    net_reduction_kg: float = 0.0
    charger_type:     str   = ""
    methodology:      str   = "Verra VM0038 v1.0"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class CarbonLedger:
    """Per-rider carbon credit ledger backed by LongTermMemory."""

    def __init__(self, memory: LongTermMemory) -> None:
        self._mem = memory

    def record(self, phone: str, entry: CarbonLedgerEntry) -> None:
        key = f"carbon:{phone}:{entry.entry_id}"
        self._mem.remember(key, entry.to_dict())

    def get_entries(self, phone: str) -> list[CarbonLedgerEntry]:
        raw = self._mem.search(f"carbon:{phone}:")
        return [CarbonLedgerEntry(**v) for v in raw.values()]

    def total_vcu(self, phone: str) -> float:
        return sum(e.net_vcu for e in self.get_entries(phone))

    def total_co2_saved_kg(self, phone: str) -> float:
        return sum(e.net_reduction_kg for e in self.get_entries(phone))

    def total_value_kes(self, phone: str) -> float:
        return sum(e.vcu_value_kes for e in self.get_entries(phone))

    def summary(self, phone: str) -> dict:
        entries = self.get_entries(phone)
        return {
            "phone":          phone,
            "total_trips":    len(entries),
            "total_vcu":      round(self.total_vcu(phone), 6),
            "total_co2_kg":   round(self.total_co2_saved_kg(phone), 3),
            "total_value_kes":round(self.total_value_kes(phone), 2),
            "entries":        [e.to_dict() for e in entries[-10:]],  # last 10
        }


# ─────────────────────────────────────────────────────────────────────────────
# Carbon Agent
# ─────────────────────────────────────────────────────────────────────────────

class CarbonAgent(BaseAgent):
    """
    AI agent responsible for:
      1. Calculating GHG reductions per trip (VM0038)
      2. Accruing VCUs to rider ledger
      3. Generating natural-language carbon summaries
      4. Answering Verra methodology questions
      5. Generating monitoring report data
    """

    name   = "CarbonAgent"
    system = textwrap.dedent("""\
        You are the Go Green Carbon Credit Specialist, an expert in:
          • Verra VM0038 v1.0 Methodology for Electric Vehicle Charging Systems
          • VMR0004 v2.0 Improved Efficiency of Fleet Vehicles
          • VMD0049 Additionality for EV Charging Systems
          • GHG Protocol Scope 1/2/3 accounting for transport fleets
          • Kenya grid emission factors and EV market conditions

        Your role:
          1. Calculate and explain GHG emission reductions in plain language
          2. Convert reductions to Verified Carbon Units (VCUs)
          3. Generate Verra-compliant monitoring report sections
          4. Provide riders with personalised carbon impact summaries
          5. Answer questions about carbon credits, methodology, and pricing

        Always cite the specific VM0038 formula components when explaining calculations.
        Express CO2 savings in multiple relatable units (trees, km driven, petrol saved).
        Be encouraging — every EV trip contributes to Kenya's climate goals.

        Kenya context:
          • Grid: >90% renewable (geothermal + hydro) — EF = 0.061 kgCO2e/kWh
          • EV market penetration: ~0.3% → ADDITIONAL under VMD0049
          • Carbon price: ~$12.50/tCO2e (VCU spot)
          • Crediting period: 7 years (renewable)
    """)

    def __init__(self, model: str | None = None) -> None:
        super().__init__(model=model)
        self._ledger: CarbonLedger | None = None   # set by orchestrator
        self._register_tools()

    def set_ledger(self, ledger: CarbonLedger) -> None:
        self._ledger = ledger

    def _register_tools(self) -> None:

        # ── Trip calculator ───────────────────────────────────────────────────
        self._tool_registry.register(
            {
                "name": "calculate_trip_carbon",
                "description": "Calculate Verra VM0038 GHG emission reductions for an EV trip.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vehicle_category": {
                            "type": "string",
                            "enum": [c.value for c in VehicleCategory],
                            "description": "Vehicle category enum value",
                        },
                        "distance_km":   {"type": "number", "description": "Distance in km"},
                        "charger_type":  {"type": "string", "enum": ["L1","L2","DCFC"]},
                    },
                    "required": ["vehicle_category", "distance_km"],
                },
            },
            self._tool_calculate_trip,
        )

        # ── Fleet calculator ──────────────────────────────────────────────────
        self._tool_registry.register(
            {
                "name": "calculate_fleet_carbon",
                "description": "Aggregate VM0038 GHG reductions across a mixed EV fleet.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "fleet_name":   {"type": "string"},
                        "period_label": {"type": "string"},
                        "vehicles_json":{"type": "string", "description": "JSON array of vehicle dicts"},
                    },
                    "required": ["fleet_name", "period_label", "vehicles_json"],
                },
            },
            self._tool_calculate_fleet,
        )

        # ── Construction machinery ────────────────────────────────────────────
        self._tool_registry.register(
            {
                "name": "calculate_construction_carbon",
                "description": "Calculate VMR0004 v2.0 GHG reductions for electric construction machinery.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "machine_category": {
                            "type": "string",
                            "enum": [c.value for c in CONSTRUCTION_PARAMS],
                        },
                        "operating_hours": {"type": "number"},
                    },
                    "required": ["machine_category", "operating_hours"],
                },
            },
            self._tool_calculate_construction,
        )

        # ── Rider ledger summary ──────────────────────────────────────────────
        self._tool_registry.register(
            {
                "name": "get_rider_carbon_summary",
                "description": "Retrieve a rider's accumulated carbon credits from the ledger.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string"},
                    },
                    "required": ["phone"],
                },
            },
            self._tool_rider_summary,
        )

        # ── Annual projection ─────────────────────────────────────────────────
        self._tool_registry.register(
            {
                "name": "project_annual_credits",
                "description": "Project annual VCU earnings for a fleet category.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vehicle_category": {"type": "string"},
                        "fleet_size":       {"type": "integer"},
                        "annual_km":        {"type": "number"},
                    },
                    "required": ["vehicle_category", "fleet_size"],
                },
            },
            self._tool_project,
        )

    # ── Tool implementations ──────────────────────────────────────────────────

    @staticmethod
    def _tool_calculate_trip(
        vehicle_category: str,
        distance_km:      float,
        charger_type:     str = "L2",
    ) -> dict:
        cat    = VehicleCategory(vehicle_category)
        result = GHGCalculator.calculate_trip(cat, distance_km, charger_type)
        return result.to_dict()

    @staticmethod
    def _tool_calculate_fleet(
        fleet_name:    str,
        period_label:  str,
        vehicles_json: str,
    ) -> dict:
        vehicles = json.loads(vehicles_json)
        for v in vehicles:
            v["category"] = VehicleCategory(v["category"])
        result = GHGCalculator.calculate_fleet(fleet_name, period_label, vehicles)
        return result.to_dict()

    @staticmethod
    def _tool_calculate_construction(
        machine_category: str,
        operating_hours:  float,
    ) -> dict:
        cat    = VehicleCategory(machine_category)
        result = GHGCalculator.calculate_construction(cat, operating_hours)
        return result.to_dict()

    def _tool_rider_summary(self, phone: str) -> dict:
        if self._ledger:
            return self._ledger.summary(phone)
        return {"error": "Ledger not initialised"}

    @staticmethod
    def _tool_project(
        vehicle_category: str,
        fleet_size:       int,
        annual_km:        float | None = None,
    ) -> dict:
        cat = VehicleCategory(vehicle_category)
        return GHGCalculator.project_annual_credits(cat, fleet_size, annual_km)

    # ── Public API ────────────────────────────────────────────────────────────

    def process_trip(
        self,
        phone:            str,
        trip_id:          str,
        vehicle_category: VehicleCategory,
        distance_km:      float,
        charger_type:     str = "L2",
    ) -> dict:
        """
        Called by the orchestrator after every completed EV trip.
        Calculates credits, records to ledger, returns summary dict.
        """
        result = GHGCalculator.calculate_trip(vehicle_category, distance_km, charger_type)

        if self._ledger:
            entry = CarbonLedgerEntry(
                trip_id          = trip_id,
                phone            = phone,
                vehicle_category = vehicle_category.value,
                distance_km      = distance_km,
                net_vcu          = result.net_vcu,
                vcu_value_kes    = result.vcu_value_kes,
                baseline_kg      = result.baseline_emissions_kg,
                net_reduction_kg = result.net_reduction_kg,
                charger_type     = charger_type,
            )
            self._ledger.record(phone, entry)

        return result.to_dict()

    def whatsapp_carbon_summary(self, phone: str, trip_result: dict) -> str:
        """Generate a WhatsApp-friendly carbon credit message after a trip."""
        vcu   = trip_result.get("net_vcu", 0)
        kg    = trip_result.get("net_reduction_kg", 0)
        trees = trip_result.get("trees_equivalent", 0)
        kes   = trip_result.get("vcu_value_kes", 0)
        dist  = trip_result.get("distance_km", 0)

        if self._ledger:
            total_vcu = self._ledger.total_vcu(phone)
            total_kg  = self._ledger.total_co2_saved_kg(phone)
            total_kes = self._ledger.total_value_kes(phone)
        else:
            total_vcu = vcu
            total_kg  = kg
            total_kes = kes

        return (
            f"🌿 *Carbon Credits Earned!*\n\n"
            f"🚗 Trip: {dist:.1f} km\n"
            f"🌱 CO₂ saved: *{kg:.0f}g* ({kg/1000:.4f} tCO₂e)\n"
            f"💎 VCU earned: *{vcu:.6f}* Verra credits\n"
            f"💰 Value: *KSh {kes:.2f}*\n"
            f"🌳 ≈ {trees:.2f} trees planted for 1 year\n\n"
            f"📊 *Your Total Credits*\n"
            f"   CO₂ saved: {total_kg:.0f}g ({total_kg/1000:.3f} tCO₂e)\n"
            f"   VCUs: {total_vcu:.5f}\n"
            f"   Value: KSh {total_kes:.2f}\n\n"
            f"_Certified under Verra VM0038 v1.0_\n"
            f"_VMD0049 Additionality: Kenya EV penetration <5%_ ✅"
        )

    def generate_monitoring_report(
        self,
        fleet_name:  str,
        period:      str,
        vehicles:    list[dict],
    ) -> str:
        """Generate a Verra VM0038-compliant monitoring report section."""
        fleet_result = GHGCalculator.calculate_fleet(fleet_name, period, vehicles)

        prompt = (
            f"Generate a formal Verra VM0038 v1.0 monitoring report section for:\n\n"
            f"Fleet: {fleet_name}\n"
            f"Period: {period}\n"
            f"Data: {json.dumps(fleet_result.to_dict(), indent=2)}\n\n"
            "Include: Executive Summary, Methodology Reference, Baseline Emissions calculation, "
            "Project Emissions, Net GHG Reductions, VCU Issuance recommendation, "
            "and Monitoring Plan compliance notes. Be precise and cite VM0038 equations."
        )
        return self.run(prompt, inject_history=False)

    def answer_carbon_query(self, question: str) -> str:
        """Answer a natural-language question about carbon credits / VM0038."""
        return self.run(question, inject_history=True)
