"""
verra_registry/queue_.py — Go Green
────────────────────────────────────────────────────────────────────────────
IssuanceQueue — accumulates per-trip VCU calculations and batches them
into periodic monitoring-period packages ready for Verra submission.

VCS requirement: monitoring periods are typically quarterly or annual.
We accumulate trips until the batch threshold is met, then trigger the
full issuance request workflow.

Persistence: SQLite (lightweight, zero-config, suitable for single-server)
             Replace with PostgreSQL for multi-server deployments.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("GOGREEN_DB_PATH", "gogreen_carbon.db")


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class BatchStatus(str, Enum):
    OPEN       = "open"          # accumulating trips
    READY      = "ready"         # threshold met, ready to package
    SUBMITTED  = "submitted"     # monitoring report sent to Verra
    VERIFIED   = "verified"      # VVB has issued verification report
    ISSUED     = "issued"        # VCUs issued to registry account
    FAILED     = "failed"        # submission or verification failed


@dataclass
class TripRecord:
    """A single completed EV trip contributing to the VCU pool."""
    trip_id:          str
    phone:            str
    timestamp:        float          # Unix timestamp
    pickup:           str
    destination:      str
    provider:         str
    distance_km:      float
    charger_type:     str
    vehicle_category: str            # VehicleCategory enum value
    baseline_kg:      float          # BE from VM0038
    project_kg:       float          # PE from VM0038
    net_kg:           float          # net tCO2e reduction (before /1000)
    gross_vcu:        float          # gross VCUs (before buffer)
    net_vcu:          float          # tradeable VCUs (after buffer)
    vcu_value_kes:    float
    batch_id:         Optional[str]  = None
    record_id:        str            = field(default_factory=lambda: str(uuid.uuid4())[:12])

    @property
    def net_tco2e(self) -> float:
        return self.net_kg / 1000.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IssuanceBatch:
    """A group of trips forming one Verra monitoring period."""
    batch_id:           str
    period_start:       str          # ISO date
    period_end:         str          # ISO date
    trip_count:         int
    total_distance_km:  float
    total_baseline_tco2: float
    total_project_tco2:  float
    total_net_tco2:      float
    total_gross_vcu:     float
    total_net_vcu:       float
    total_value_kes:     float
    status:             BatchStatus  = BatchStatus.OPEN
    submission_ref:     str          = ""    # Verra email thread / ticket ref
    vvb_report_url:     str          = ""
    vcu_serial_start:   str          = ""    # filled after issuance
    vcu_serial_end:     str          = ""
    created_at:         str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at:         str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ─────────────────────────────────────────────────────────────────────────────
# SQLite persistence
# ─────────────────────────────────────────────────────────────────────────────

class _DB:
    def __init__(self, path: str = DB_PATH) -> None:
        self._path = path
        self._init()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self._path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def _init(self) -> None:
        with self.conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS trips (
                record_id         TEXT PRIMARY KEY,
                trip_id           TEXT NOT NULL,
                phone             TEXT NOT NULL,
                timestamp         REAL NOT NULL,
                pickup            TEXT,
                destination       TEXT,
                provider          TEXT,
                distance_km       REAL,
                charger_type      TEXT,
                vehicle_category  TEXT,
                baseline_kg       REAL,
                project_kg        REAL,
                net_kg            REAL,
                gross_vcu         REAL,
                net_vcu           REAL,
                vcu_value_kes     REAL,
                batch_id          TEXT,
                created_at        TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS batches (
                batch_id              TEXT PRIMARY KEY,
                period_start          TEXT,
                period_end            TEXT,
                trip_count            INTEGER,
                total_distance_km     REAL,
                total_baseline_tco2   REAL,
                total_project_tco2    REAL,
                total_net_tco2        REAL,
                total_gross_vcu       REAL,
                total_net_vcu         REAL,
                total_value_kes       REAL,
                status                TEXT DEFAULT 'open',
                submission_ref        TEXT DEFAULT '',
                vvb_report_url        TEXT DEFAULT '',
                vcu_serial_start      TEXT DEFAULT '',
                vcu_serial_end        TEXT DEFAULT '',
                created_at            TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at            TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)


# ─────────────────────────────────────────────────────────────────────────────
# IssuanceQueue
# ─────────────────────────────────────────────────────────────────────────────

class IssuanceQueue:
    """
    Accumulates per-trip VCU records and batches them into monitoring periods.

    Batch triggers (configurable):
      • MIN_VCU_THRESHOLD  : minimum tCO2e to justify a submission (~50 tCO2e)
      • MAX_PERIOD_DAYS    : maximum days before forcing a batch (90 = quarterly)
      • MIN_TRIPS          : minimum trips in a batch (avoid micro-submissions)

    Typical Go Green workflow:
      1. After each confirmed trip → queue.add_trip(trip_record)
      2. Periodically             → queue.check_and_promote()
      3. When batch is READY      → workflow.submit_batch(batch)
      4. After VVB verification   → queue.mark_verified(batch_id, report_url)
      5. After Verra issues VCUs  → queue.mark_issued(batch_id, serials)
    """

    MIN_VCU_THRESHOLD  = float(os.environ.get("MIN_VCU_THRESHOLD",  "50.0"))   # tCO2e
    MAX_PERIOD_DAYS    = int(os.environ.get("MAX_PERIOD_DAYS",       "90"))     # ~quarterly
    MIN_TRIPS          = int(os.environ.get("MIN_TRIPS",             "100"))

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db = _DB(db_path)
        logger.info(
            "IssuanceQueue: min_vcu=%.1f tCO2e, max_period=%dd, min_trips=%d",
            self.MIN_VCU_THRESHOLD, self.MAX_PERIOD_DAYS, self.MIN_TRIPS,
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_trip(self, trip: TripRecord) -> None:
        """Add a completed trip to the open batch."""
        open_batch = self._get_or_create_open_batch()
        trip.batch_id = open_batch.batch_id

        with self._db.conn() as c:
            c.execute("""
                INSERT OR IGNORE INTO trips
                (record_id, trip_id, phone, timestamp, pickup, destination,
                 provider, distance_km, charger_type, vehicle_category,
                 baseline_kg, project_kg, net_kg, gross_vcu, net_vcu,
                 vcu_value_kes, batch_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trip.record_id, trip.trip_id, trip.phone, trip.timestamp,
                trip.pickup, trip.destination, trip.provider, trip.distance_km,
                trip.charger_type, trip.vehicle_category,
                trip.baseline_kg, trip.project_kg, trip.net_kg,
                trip.gross_vcu, trip.net_vcu, trip.vcu_value_kes, trip.batch_id,
            ))
            # Update batch aggregate
            c.execute("""
                UPDATE batches SET
                  trip_count          = trip_count + 1,
                  total_distance_km   = total_distance_km   + ?,
                  total_baseline_tco2 = total_baseline_tco2 + ?,
                  total_project_tco2  = total_project_tco2  + ?,
                  total_net_tco2      = total_net_tco2      + ?,
                  total_gross_vcu     = total_gross_vcu     + ?,
                  total_net_vcu       = total_net_vcu       + ?,
                  total_value_kes     = total_value_kes     + ?,
                  period_end          = ?,
                  updated_at          = ?
                WHERE batch_id = ?
            """, (
                trip.distance_km,
                trip.baseline_kg / 1000,
                trip.project_kg  / 1000,
                trip.net_kg      / 1000,
                trip.gross_vcu,
                trip.net_vcu,
                trip.vcu_value_kes,
                datetime.fromtimestamp(trip.timestamp, tz=timezone.utc).date().isoformat(),
                datetime.now(timezone.utc).isoformat(),
                open_batch.batch_id,
            ))

        logger.debug("Trip %s added to batch %s", trip.trip_id, open_batch.batch_id)

    # ── Batch promotion ───────────────────────────────────────────────────────

    def check_and_promote(self) -> Optional[IssuanceBatch]:
        """
        Check if the open batch meets submission thresholds.
        If yes, promote it to READY status and return it.
        Returns None if not yet ready.
        """
        batch = self.get_open_batch()
        if not batch:
            return None

        days_open = (
            datetime.now(timezone.utc).date()
            - datetime.fromisoformat(batch.created_at).date()
        ).days

        vcu_ready   = batch.total_net_vcu  >= self.MIN_VCU_THRESHOLD
        trips_ready = batch.trip_count     >= self.MIN_TRIPS
        age_ready   = days_open            >= self.MAX_PERIOD_DAYS

        if vcu_ready and trips_ready:
            logger.info(
                "Batch %s READY: %.4f tCO2e, %d trips, %d days",
                batch.batch_id, batch.total_net_vcu, batch.trip_count, days_open,
            )
            self._set_batch_status(batch.batch_id, BatchStatus.READY)
            batch.status = BatchStatus.READY
            return batch
        elif age_ready and batch.trip_count > 0:
            logger.info(
                "Batch %s READY (age threshold): %.4f tCO2e, %d trips",
                batch.batch_id, batch.total_net_vcu, batch.trip_count,
            )
            self._set_batch_status(batch.batch_id, BatchStatus.READY)
            batch.status = BatchStatus.READY
            return batch

        logger.debug(
            "Batch %s not ready: %.4f/%.1f tCO2e, %d/%d trips, %d/%d days",
            batch.batch_id,
            batch.total_net_vcu, self.MIN_VCU_THRESHOLD,
            batch.trip_count, self.MIN_TRIPS,
            days_open, self.MAX_PERIOD_DAYS,
        )
        return None

    # ── Status updates ─────────────────────────────────────────────────────────

    def mark_submitted(self, batch_id: str, submission_ref: str) -> None:
        with self._db.conn() as c:
            c.execute(
                "UPDATE batches SET status=?, submission_ref=?, updated_at=? WHERE batch_id=?",
                (BatchStatus.SUBMITTED.value, submission_ref,
                 datetime.now(timezone.utc).isoformat(), batch_id),
            )
        logger.info("Batch %s SUBMITTED (ref: %s)", batch_id, submission_ref)

    def mark_verified(self, batch_id: str, vvb_report_url: str) -> None:
        with self._db.conn() as c:
            c.execute(
                "UPDATE batches SET status=?, vvb_report_url=?, updated_at=? WHERE batch_id=?",
                (BatchStatus.VERIFIED.value, vvb_report_url,
                 datetime.now(timezone.utc).isoformat(), batch_id),
            )
        logger.info("Batch %s VERIFIED (VVB: %s)", batch_id, vvb_report_url)

    def mark_issued(
        self, batch_id: str,
        serial_start: str, serial_end: str,
    ) -> None:
        with self._db.conn() as c:
            c.execute(
                """UPDATE batches SET status=?, vcu_serial_start=?,
                   vcu_serial_end=?, updated_at=? WHERE batch_id=?""",
                (BatchStatus.ISSUED.value, serial_start, serial_end,
                 datetime.now(timezone.utc).isoformat(), batch_id),
            )
        logger.info(
            "Batch %s ISSUED — serials %s → %s", batch_id, serial_start, serial_end
        )

    def mark_failed(self, batch_id: str, reason: str = "") -> None:
        with self._db.conn() as c:
            c.execute(
                "UPDATE batches SET status=?, submission_ref=?, updated_at=? WHERE batch_id=?",
                (BatchStatus.FAILED.value, reason,
                 datetime.now(timezone.utc).isoformat(), batch_id),
            )
        logger.warning("Batch %s FAILED: %s", batch_id, reason)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_open_batch(self) -> Optional[IssuanceBatch]:
        with self._db.conn() as c:
            row = c.execute(
                "SELECT * FROM batches WHERE status=? ORDER BY created_at LIMIT 1",
                (BatchStatus.OPEN.value,),
            ).fetchone()
        return self._row_to_batch(row) if row else None

    def get_batch(self, batch_id: str) -> Optional[IssuanceBatch]:
        with self._db.conn() as c:
            row = c.execute(
                "SELECT * FROM batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
        return self._row_to_batch(row) if row else None

    def get_batch_trips(self, batch_id: str) -> list[TripRecord]:
        with self._db.conn() as c:
            rows = c.execute(
                "SELECT * FROM trips WHERE batch_id=? ORDER BY timestamp",
                (batch_id,),
            ).fetchall()
        return [self._row_to_trip(r) for r in rows]

    def get_all_batches(self) -> list[IssuanceBatch]:
        with self._db.conn() as c:
            rows = c.execute(
                "SELECT * FROM batches ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_batch(r) for r in rows]

    def get_portfolio_summary(self, phone: Optional[str] = None) -> dict:
        """Aggregated VCU stats across all ISSUED batches."""
        with self._db.conn() as c:
            if phone:
                row = c.execute(
                    """SELECT COUNT(*) as trips,
                              SUM(net_vcu) as total_vcu,
                              SUM(net_kg/1000) as total_tco2,
                              SUM(vcu_value_kes) as total_kes
                       FROM trips WHERE phone=?""",
                    (phone,),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT COUNT(*) as trips,
                              SUM(net_vcu) as total_vcu,
                              SUM(net_kg/1000) as total_tco2,
                              SUM(vcu_value_kes) as total_kes
                       FROM trips"""
                ).fetchone()
        return {
            "trips":      row["trips"]       or 0,
            "total_vcu":  round(row["total_vcu"]   or 0, 6),
            "total_tco2": round(row["total_tco2"]  or 0, 4),
            "total_kes":  round(row["total_kes"]   or 0, 2),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_or_create_open_batch(self) -> IssuanceBatch:
        existing = self.get_open_batch()
        if existing:
            return existing

        batch_id = f"GG-BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
        now      = datetime.now(timezone.utc)
        today    = now.date().isoformat()

        with self._db.conn() as c:
            c.execute("""
                INSERT INTO batches
                (batch_id, period_start, period_end, trip_count,
                 total_distance_km, total_baseline_tco2, total_project_tco2,
                 total_net_tco2, total_gross_vcu, total_net_vcu, total_value_kes,
                 status, created_at, updated_at)
                VALUES (?,?,?,0, 0,0,0,0,0,0,0, ?,?,?)
            """, (batch_id, today, today,
                  BatchStatus.OPEN.value, now.isoformat(), now.isoformat()))

        logger.info("New issuance batch created: %s", batch_id)
        return self._get_or_create_open_batch()

    def _set_batch_status(self, batch_id: str, status: BatchStatus) -> None:
        with self._db.conn() as c:
            c.execute(
                "UPDATE batches SET status=?, updated_at=? WHERE batch_id=?",
                (status.value, datetime.now(timezone.utc).isoformat(), batch_id),
            )

    @staticmethod
    def _row_to_batch(row: sqlite3.Row) -> IssuanceBatch:
        return IssuanceBatch(
            batch_id             = row["batch_id"],
            period_start         = row["period_start"],
            period_end           = row["period_end"],
            trip_count           = row["trip_count"],
            total_distance_km    = row["total_distance_km"],
            total_baseline_tco2  = row["total_baseline_tco2"],
            total_project_tco2   = row["total_project_tco2"],
            total_net_tco2       = row["total_net_tco2"],
            total_gross_vcu      = row["total_gross_vcu"],
            total_net_vcu        = row["total_net_vcu"],
            total_value_kes      = row["total_value_kes"],
            status               = BatchStatus(row["status"]),
            submission_ref       = row["submission_ref"] or "",
            vvb_report_url       = row["vvb_report_url"] or "",
            vcu_serial_start     = row["vcu_serial_start"] or "",
            vcu_serial_end       = row["vcu_serial_end"] or "",
            created_at           = row["created_at"],
            updated_at           = row["updated_at"],
        )

    @staticmethod
    def _row_to_trip(row: sqlite3.Row) -> TripRecord:
        return TripRecord(
            record_id        = row["record_id"],
            trip_id          = row["trip_id"],
            phone            = row["phone"],
            timestamp        = row["timestamp"],
            pickup           = row["pickup"]           or "",
            destination      = row["destination"]      or "",
            provider         = row["provider"]         or "",
            distance_km      = row["distance_km"]      or 0,
            charger_type     = row["charger_type"]     or "L2",
            vehicle_category = row["vehicle_category"] or "psv_passenger_car",
            baseline_kg      = row["baseline_kg"]      or 0,
            project_kg       = row["project_kg"]       or 0,
            net_kg           = row["net_kg"]           or 0,
            gross_vcu        = row["gross_vcu"]        or 0,
            net_vcu          = row["net_vcu"]          or 0,
            vcu_value_kes    = row["vcu_value_kes"]    or 0,
            batch_id         = row["batch_id"],
        )
