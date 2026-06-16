"""
fleet/ — Go Green Expanded Fleet Module
═══════════════════════════════════════════════════════════════════════════
New fleet categories added:

  E-Bike Networks
  ───────────────
  • Ecobodaa    — Nairobi-designed/assembled e-motorbikes, PAYGO battery swap
                  (Kenyan engineers, lease-to-own, PREO-funded)
  • eBoda        — Generic e-boda-boda network (Spiro / M-KOPA / Mogo ecosystem)
  • BoltBoda     — Bolt's electric motorcycle fleet (40% of Nairobi motorcycle
                  fleet electric as of late 2025, per Ethical Business Africa)
  • RoamBoda     — Roam Electric (Kenyan-assembled) e-boda

  Matatu SACCOs (electric)
  ─────────────────────────
  • BasiGoMatatu  — BasiGo Pay-As-You-Drive electric matatus (16/19-seater)
                   Pilot: 4NTE SACCO (Nyahururu–Nyeri/Nakuru) +
                          Manchester SACCO (Thika–Nairobi) — launched Jul 2025
  • RoamMove      — Roam Move electric minibus (competing matatu segment)
  • OpibusMatatu  — Opibus electric matatu conversion

  BRT Routes (NAMATA electric bus network)
  ─────────────────────────────────────────
  • NamataBRT_Ndovu   — BRT Line 1: Kangemi ↔ Imara Daima via CBD/Westlands
  • NamataBRT_Line2   — BRT Line 2: Githurai ↔ CBD (EU-financed, e-bus scoping
                        completed Nov 2024–Jul 2025; BasiGo / Roam Rapid)
  • NamataBRT_Kifaru  — BRT Line 4: Jogoo Road corridor

All adapters implement get_offers() → list[RideOffer] and are
registered in the central fleet registry.
"""

from .ebike      import EcobodaaAdapter, EBodaAdapter, BoltBodaAdapter, RoamBodaAdapter
from .matatu     import BasiGoMatatuAdapter, RoamMoveAdapter, OpibusMatatuAdapter
from .brt        import NamataBRTNdovuAdapter, NamataBRTLine2Adapter, NamataBRTKifaruAdapter
from .registry   import FLEET_REGISTRY, get_fleet_offers, get_fleet_by_type, FleetType
from .vm0038_ext import FLEET_VM0038_PARAMS, get_carbon_params

__all__ = [
    # E-bikes
    "EcobodaaAdapter", "EBodaAdapter", "BoltBodaAdapter", "RoamBodaAdapter",
    # Matatus
    "BasiGoMatatuAdapter", "RoamMoveAdapter", "OpibusMatatuAdapter",
    # BRT
    "NamataBRTNdovuAdapter", "NamataBRTLine2Adapter", "NamataBRTKifaruAdapter",
    # Registry
    "FLEET_REGISTRY", "get_fleet_offers", "get_fleet_by_type", "FleetType",
    # VM0038
    "FLEET_VM0038_PARAMS", "get_carbon_params",
]
