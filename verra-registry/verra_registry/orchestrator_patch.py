"""
verra_registry/orchestrator_patch.py — Go Green
────────────────────────────────────────────────────────────────────────────
Wires IssuanceWorkflow into GoGreenOrchestrator.

After every confirmed M-Pesa payment → carbon result is calculated →
a TripRecord is built and fed into the workflow → VCU accumulates in
the issuance queue.

Usage in app.py:
    from verra_registry.orchestrator_patch import patch_orchestrator
    from orchestrator_agent import GoGreenOrchestrator
    patch_orchestrator(GoGreenOrchestrator)
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .queue_    import TripRecord
from .workflow  import IssuanceWorkflow

logger = logging.getLogger(__name__)

# Module-level workflow singleton
workflow = IssuanceWorkflow()


def patch_orchestrator(orchestrator_class) -> None:
    """
    Monkey-patches GoGreenOrchestrator._handle_confirmation to call
    workflow.on_trip_complete() after every successful M-Pesa payment.
    """
    original_confirmation = orchestrator_class._handle_confirmation

    def patched_confirmation(self, phone: str, text: str):
        response = original_confirmation(self, phone, text)

        # Only process if payment succeeded and carbon was calculated
        if (
            self.session.paid
            and self.session.carbon_result
            and self.session.chosen_offer
        ):
            carbon = self.session.carbon_result
            offer  = self.session.chosen_offer
            trip   = TripRecord(
                trip_id          = self.session.trip_id or f"GG-{int(time.time())}",
                phone            = phone,
                timestamp        = time.time(),
                pickup           = self.session.pickup,
                destination      = self.session.destination,
                provider         = offer.get("provider", "Uber"),
                distance_km      = carbon.get("distance_km", offer.get("distance_km", 0)),
                charger_type     = carbon.get("charger_type", "L2"),
                vehicle_category = carbon.get("vehicle_category", "psv_passenger_car"),
                baseline_kg      = carbon.get("baseline_emissions_kg", 0),
                project_kg       = carbon.get("project_emissions_kg",  0),
                net_kg           = carbon.get("net_reduction_kg",       0),
                gross_vcu        = carbon.get("gross_vcu",              0),
                net_vcu          = carbon.get("net_vcu",                0),
                vcu_value_kes    = carbon.get("vcu_value_kes",          0),
            )
            try:
                workflow.on_trip_complete(trip)
                logger.info(
                    "Trip %s → IssuanceQueue (batch %s, %.8f VCU)",
                    trip.trip_id, trip.batch_id, trip.net_vcu,
                )
            except Exception as exc:
                logger.warning("IssuanceWorkflow.on_trip_complete failed: %s", exc)

        return response

    orchestrator_class._handle_confirmation = patched_confirmation
    logger.info("GoGreenOrchestrator patched with Verra IssuanceWorkflow")
