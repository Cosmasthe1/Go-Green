"""
verra_registry/workflow.py — Go Green
────────────────────────────────────────────────────────────────────────────
IssuanceWorkflow — orchestrates the full VCU pipeline end-to-end.

Pipeline stages:
  ┌─────────────────────────────────────────────────────────────────────┐
  │                    IssuanceWorkflow                                  │
  │                                                                     │
  │  Per trip (real-time):                                              │
  │    on_trip_complete() → queue.add_trip() → check_and_promote()     │
  │                                                                     │
  │  When batch threshold met → READY:                                  │
  │    submit_batch()                                                   │
  │      ├─ builder.build()        → monitoring report + CSV + letter  │
  │      ├─ submitter.submit()     → email to registry@verra.org       │
  │      └─ queue.mark_submitted() → track submission ref              │
  │                                                                     │
  │  When VVB verifies (manual trigger or webhook):                     │
  │    mark_verified(batch_id, vvb_report_url)                         │
  │                                                                     │
  │  When Verra issues credits (registry scrape or manual trigger):     │
  │    mark_issued(batch_id, serial_start, serial_end)                  │
  │    → verify against public registry                                 │
  │    → notify riders via WhatsApp                                     │
  │                                                                     │
  │  Background scheduler (APScheduler or threading.Timer):             │
  │    • Daily:   check_and_promote() — see if any batch is ready       │
  │    • Weekly:  scrape_registry()   — check for new issuances         │
  │    • Monthly: send_portfolio_report() — notify all riders           │
  └─────────────────────────────────────────────────────────────────────┘
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from .builder   import IssuanceRequestBuilder
from .client    import verra_client
from .queue_    import BatchStatus, IssuanceBatch, IssuanceQueue, TripRecord
from .submitter import EmailSubmitter

logger = logging.getLogger(__name__)

# Notification callback type: fn(phone, message_text)
NotifyFn = Callable[[str, str], None]


@dataclass
class WorkflowEvent:
    event_type:  str          # "trip_added" | "batch_ready" | "submitted" | "issued"
    batch_id:    str
    detail:      str
    timestamp:   float = field(default_factory=time.time)


class IssuanceWorkflow:
    """
    Full VCU issuance pipeline for Go Green.

    Designed to be a singleton, instantiated once at app startup and shared
    across the orchestrator, WhatsApp agent, and background scheduler.

    Usage in orchestrator_agent.py:
        from verra_registry import IssuanceWorkflow
        workflow = IssuanceWorkflow()

        # After each confirmed + paid trip:
        workflow.on_trip_complete(trip_record)

        # Manual batch submission (for testing):
        workflow.force_submit()
    """

    def __init__(
        self,
        db_path:  str = os.environ.get("GOGREEN_DB_PATH", "gogreen_carbon.db"),
        notify_fn: Optional[NotifyFn] = None,
        auto_schedule: bool = True,
    ) -> None:
        self.queue     = IssuanceQueue(db_path)
        self.builder   = IssuanceRequestBuilder()
        self.submitter = EmailSubmitter()
        self._notify   = notify_fn or self._log_notify
        self._events:  list[WorkflowEvent] = []
        self._lock     = threading.Lock()

        if auto_schedule:
            self._start_scheduler()
            logger.info("IssuanceWorkflow started with background scheduler")
        else:
            logger.info("IssuanceWorkflow started (no scheduler)")

    # ── Primary entry point ───────────────────────────────────────────────────

    def on_trip_complete(
        self,
        trip: TripRecord,
        output_dir: Optional[str] = None,
    ) -> Optional[IssuanceBatch]:
        """
        Called by the orchestrator after every confirmed M-Pesa payment.

        1. Adds trip to the open batch
        2. Checks if batch threshold is met
        3. If READY → submits automatically

        Returns the batch if it was promoted to READY/SUBMITTED, else None.
        """
        with self._lock:
            self.queue.add_trip(trip)
            self._record(WorkflowEvent("trip_added", trip.batch_id or "", f"trip={trip.trip_id} vcu={trip.net_vcu:.8f}"))

            ready_batch = self.queue.check_and_promote()
            if ready_batch:
                logger.info("Batch %s promoted to READY — submitting", ready_batch.batch_id)
                return self.submit_batch(ready_batch, output_dir=output_dir)

        return None

    def submit_batch(
        self,
        batch:      IssuanceBatch,
        output_dir: Optional[str] = None,
    ) -> IssuanceBatch:
        """
        Build + submit a READY batch to Verra.
        Returns the updated batch (status = SUBMITTED or FAILED).
        """
        logger.info(
            "Submitting batch %s: %.4f tCO₂e, %d trips, period %s—%s",
            batch.batch_id, batch.total_net_vcu,
            batch.trip_count, batch.period_start, batch.period_end,
        )

        trips = self.queue.get_batch_trips(batch.batch_id)
        if not trips:
            logger.warning("Batch %s has no trips — skipping", batch.batch_id)
            return batch

        try:
            # 1. Build the monitoring report package
            report = self.builder.build(batch, trips, output_dir=output_dir)

            # 2. Submit to registry@verra.org
            result = self.submitter.submit(report)

            if result.success:
                self.queue.mark_submitted(batch.batch_id, result.reference)
                batch.status        = BatchStatus.SUBMITTED
                batch.submission_ref= result.reference

                self._record(WorkflowEvent(
                    "submitted", batch.batch_id,
                    f"ref={result.reference} vcu={batch.total_net_vcu:.4f}",
                ))
                self._notify(
                    "admin",
                    f"🌿 *VCU Issuance Submitted*\n\n"
                    f"Batch: {batch.batch_id}\n"
                    f"Net VCUs: {batch.total_net_vcu:.4f} tCO₂e\n"
                    f"Trips: {batch.trip_count:,}\n"
                    f"Period: {batch.period_start} — {batch.period_end}\n"
                    f"Submitted to: registry@verra.org\n"
                    f"Reference: {result.reference}\n\n"
                    f"_Next: VVB verification, then Verra review and credit issuance._",
                )
                logger.info("Batch %s submitted — ref: %s", batch.batch_id, result.reference)
            else:
                self.queue.mark_failed(batch.batch_id, result.error)
                batch.status = BatchStatus.FAILED
                logger.error("Batch %s submission failed: %s", batch.batch_id, result.error)

        except Exception as exc:
            self.queue.mark_failed(batch.batch_id, str(exc))
            batch.status = BatchStatus.FAILED
            logger.exception("Batch %s submission exception", batch.batch_id)

        return batch

    def force_submit(self, output_dir: Optional[str] = None) -> Optional[IssuanceBatch]:
        """
        Force-promote and submit the current open batch regardless of threshold.
        Useful for end-of-period submissions and testing.
        """
        with self._lock:
            batch = self.queue.get_open_batch()
            if not batch:
                logger.info("No open batch to submit")
                return None
            if batch.trip_count == 0:
                logger.info("Open batch is empty — nothing to submit")
                return None

            logger.info("Force-submitting batch %s", batch.batch_id)
            self.queue._set_batch_status(batch.batch_id, BatchStatus.READY)
            batch.status = BatchStatus.READY
            return self.submit_batch(batch, output_dir=output_dir)

    # ── Status update hooks (called manually or via webhook) ──────────────────

    def mark_verified(self, batch_id: str, vvb_report_url: str) -> None:
        """
        Call when the VVB has issued its verification report.
        This enables the proponent to request VCU issuance from Verra.
        """
        self.queue.mark_verified(batch_id, vvb_report_url)
        self._record(WorkflowEvent("verified", batch_id, vvb_report_url))
        self._notify(
            "admin",
            f"✅ *VVB Verification Complete*\n\n"
            f"Batch: {batch_id}\n"
            f"Report: {vvb_report_url}\n\n"
            f"_Next: Log into registry.verra.org → request VCU issuance._",
        )

    def mark_issued(
        self,
        batch_id:     str,
        serial_start: str,
        serial_end:   str,
    ) -> None:
        """
        Call when Verra has issued VCUs and they appear in the registry.
        Verifies the serials against the public registry, then notifies.
        """
        self.queue.mark_issued(batch_id, serial_start, serial_end)
        self._record(WorkflowEvent("issued", batch_id, f"{serial_start}—{serial_end}"))

        # Verify against public registry
        verify = verra_client.verify_serial(serial_start)
        logger.info("Serial verification: %s → %s", serial_start, verify)

        batch = self.queue.get_batch(batch_id)
        vcu   = batch.total_net_vcu if batch else 0

        self._notify(
            "admin",
            f"💎 *VCUs Issued!*\n\n"
            f"Batch: {batch_id}\n"
            f"VCUs: {vcu:.4f} tCO₂e\n"
            f"Serials: {serial_start} — {serial_end}\n"
            f"Registry: https://registry.verra.org\n\n"
            f"_Credits are now tradeable on the voluntary carbon market._",
        )

    # ── Registry polling ──────────────────────────────────────────────────────

    def check_registry_for_new_issuances(self) -> Optional[dict]:
        """
        Scrape the public Verra registry for new issuances on our project.
        Run weekly via the background scheduler.
        Returns the latest issuance record if found, else None.
        """
        from .builder import VCS_PROJECT_ID as pid
        if not pid:
            logger.debug("VCS_PROJECT_ID not set — skipping registry check")
            return None

        try:
            latest_date = verra_client.get_latest_issuance_date(pid)
            total       = verra_client.get_total_issued(pid)
            logger.info(
                "Registry check: VCS%s — latest issuance %s, total %.2f tCO2e",
                pid, latest_date, total,
            )
            return {"latest_date": latest_date, "total_issued": total}
        except Exception as exc:
            logger.warning("Registry check failed: %s", exc)
            return None

    # ── Portfolio reporting ───────────────────────────────────────────────────

    def get_portfolio_summary(self, phone: Optional[str] = None) -> dict:
        """Aggregated VCU stats for a rider or the whole fleet."""
        return self.queue.get_portfolio_summary(phone)

    def get_all_batches(self) -> list[IssuanceBatch]:
        return self.queue.get_all_batches()

    def get_events(self) -> list[WorkflowEvent]:
        return list(self._events[-50:])   # last 50 events

    # ── Background scheduler ──────────────────────────────────────────────────

    def _start_scheduler(self) -> None:
        """Start lightweight background threads for periodic tasks."""

        def daily_check():
            while True:
                time.sleep(86_400)   # 24 hours
                logger.info("Scheduler: daily batch promotion check")
                try:
                    with self._lock:
                        ready = self.queue.check_and_promote()
                        if ready:
                            self.submit_batch(ready)
                except Exception as exc:
                    logger.warning("Scheduler daily check error: %s", exc)

        def weekly_registry_check():
            while True:
                time.sleep(7 * 86_400)   # 7 days
                logger.info("Scheduler: weekly registry scrape")
                try:
                    self.check_registry_for_new_issuances()
                except Exception as exc:
                    logger.warning("Scheduler registry check error: %s", exc)

        for fn in (daily_check, weekly_registry_check):
            t = threading.Thread(target=fn, daemon=True, name=fn.__name__)
            t.start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _record(self, event: WorkflowEvent) -> None:
        self._events.append(event)
        if len(self._events) > 500:
            self._events = self._events[-500:]

    @staticmethod
    def _log_notify(phone: str, message: str) -> None:
        logger.info("[NOTIFY → %s] %s", phone, message[:100])
