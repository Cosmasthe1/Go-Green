"""
verra_registry/builder.py — Go Green
────────────────────────────────────────────────────────────────────────────
IssuanceRequestBuilder — generates the complete Verra submission package
for a monitoring period batch.

Outputs (all written to a temp directory, then zipped):
  1. monitoring_report_{batch_id}.md   — human-readable VCS monitoring report
                                         following the VM0038 template structure
  2. ghg_calculations_{batch_id}.csv   — per-trip VM0038 calculation table
                                         (the "Calculation Spreadsheet" required
                                          by VM0038 §7 monitoring plan)
  3. cover_letter_{batch_id}.txt       — formal submission cover letter
                                         addressed to registry@verra.org
  4. summary_{batch_id}.json           — machine-readable batch summary

VCS required monitoring report sections (VM0038 §7):
  1. Project Summary
  2. Monitoring Period
  3. Quantification of GHG Emission Reductions
     3.1 Baseline Emissions (BE)
     3.2 Project Emissions (PE)
     3.3 Leakage (LE)
     3.4 Net Emission Reductions (ER)
  4. Data and Parameters
  5. Additionality
  6. Double Counting Avoidance
  7. VCU Calculation Summary
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .queue_ import IssuanceBatch, TripRecord

logger = logging.getLogger(__name__)

# ── Project constants (set in .env after Verra project registration) ──────────
VCS_PROJECT_ID      = os.environ.get("VCS_PROJECT_ID",       "")        # e.g. "3456"
VCS_PROJECT_NAME    = os.environ.get("VCS_PROJECT_NAME",     "Go Green EV Fleet Kenya")
VCS_PROJECT_COUNTRY = os.environ.get("VCS_PROJECT_COUNTRY",  "Kenya")
VCS_PROPONENT_NAME  = os.environ.get("VCS_PROPONENT_NAME",   "Go Green Limited")
VCS_PROPONENT_EMAIL = os.environ.get("VCS_PROPONENT_EMAIL",  "registry@gogreen.co.ke")
VCS_ACCOUNT_NUMBER  = os.environ.get("VCS_ACCOUNT_NUMBER",   "")        # Verra account #
VVB_NAME            = os.environ.get("VVB_NAME",             "")        # e.g. "SustainCERT"
VVB_ACCREDITATION   = os.environ.get("VVB_ACCREDITATION",    "")        # ISO 14065

# VM0038 fixed parameters
METHODOLOGY         = "VM0038 v1.0 — Methodology for Electric Vehicle Charging Systems"
ADDITIONALITY       = "VMD0049 v1.0 — Activity Method (positive list). Kenya EV penetration ~0.3% < 5% threshold."
EF_GRID             = 0.061      # kgCO2e/kWh  IEA 2024
EF_PETROL           = 2.296      # kgCO2e/L
WTT_PETROL          = 1.19
AFEC_PSV            = 0.090      # L/km  PSV passenger car baseline
EV_KWH_KM           = 0.180      # kWh/km  EV project vehicle
ETA_L2              = 0.900      # L2 charger efficiency
LEAKAGE_PCT         = 0.03
VCS_BUFFER_PCT      = 0.10
NET_FACTOR          = (1 - LEAKAGE_PCT) * (1 - VCS_BUFFER_PCT)


@dataclass
class MonitoringReport:
    batch_id:    str
    report_path: Path        # path to generated .md file
    csv_path:    Path        # path to generated calculations .csv
    letter_path: Path        # path to cover letter .txt
    summary_path:Path        # path to summary .json
    zip_path:    Path        # path to final .zip archive
    total_net_vcu: float
    total_net_tco2: float
    period_start: str
    period_end:   str


class IssuanceRequestBuilder:
    """
    Generates a complete Verra VCS issuance request package for a batch.

    Usage:
        builder  = IssuanceRequestBuilder()
        trips    = queue.get_batch_trips(batch.batch_id)
        report   = builder.build(batch, trips, output_dir="/tmp/verra")
        # report.zip_path contains everything to attach to the email
    """

    def build(
        self,
        batch:      IssuanceBatch,
        trips:      list[TripRecord],
        output_dir: Optional[str] = None,
    ) -> MonitoringReport:
        """
        Generate all submission documents and zip them.
        Returns a MonitoringReport with paths to all generated files.
        """
        out = Path(output_dir or tempfile.mkdtemp(prefix="gogreen_verra_"))
        out.mkdir(parents=True, exist_ok=True)
        bid = batch.batch_id

        logger.info("Building issuance package for batch %s (%d trips)", bid, len(trips))

        report_path  = out / f"monitoring_report_{bid}.md"
        csv_path     = out / f"ghg_calculations_{bid}.csv"
        letter_path  = out / f"cover_letter_{bid}.txt"
        summary_path = out / f"summary_{bid}.json"
        zip_path     = out / f"gogreen_vcs_issuance_{bid}.zip"

        self._write_monitoring_report(report_path, batch, trips)
        self._write_calculations_csv(csv_path, trips)
        self._write_cover_letter(letter_path, batch)
        self._write_summary_json(summary_path, batch)
        self._zip_package(zip_path, [report_path, csv_path, letter_path, summary_path])

        logger.info("Issuance package ready: %s (%.1f KB)", zip_path, zip_path.stat().st_size / 1024)

        return MonitoringReport(
            batch_id       = bid,
            report_path    = report_path,
            csv_path       = csv_path,
            letter_path    = letter_path,
            summary_path   = summary_path,
            zip_path       = zip_path,
            total_net_vcu  = batch.total_net_vcu,
            total_net_tco2 = batch.total_net_tco2,
            period_start   = batch.period_start,
            period_end     = batch.period_end,
        )

    # ── Document generators ───────────────────────────────────────────────────

    def _write_monitoring_report(
        self, path: Path, batch: IssuanceBatch, trips: list[TripRecord]
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%d %B %Y")
        content = f"""# VCS Monitoring Report
## {VCS_PROJECT_NAME}

---

| Field | Value |
|-------|-------|
| **VCS Project ID** | {VCS_PROJECT_ID or "PENDING REGISTRATION"} |
| **Project Name** | {VCS_PROJECT_NAME} |
| **Country** | {VCS_PROJECT_COUNTRY} |
| **Methodology** | {METHODOLOGY} |
| **Batch ID** | {batch.batch_id} |
| **Monitoring Period** | {batch.period_start} — {batch.period_end} |
| **Report Date** | {now} |
| **Project Proponent** | {VCS_PROPONENT_NAME} |
| **VCS Account** | {VCS_ACCOUNT_NUMBER or "PENDING"} |
| **VVB** | {VVB_NAME or "TBD"} |

---

## 1. Project Summary

Go Green operates a fleet of electric vehicles (EVs) for ride-hailing services
in Nairobi, Kenya. This project displaces fossil-fuel-powered vehicle trips with
clean electricity from Kenya's predominantly renewable grid (>90% geothermal
and hydro), generating verified GHG emission reductions certified under the
Verified Carbon Standard (VCS).

**Fleet categories covered this period:**
- PSV Passenger Cars (ride-hailing / taxi): primary fleet
- All rides exclusively with Uber Green EV service

**Charging network:** Level 2 AC chargers (7.4 kW, η = {ETA_L2})

---

## 2. Monitoring Period

| Parameter | Value |
|-----------|-------|
| Period Start | {batch.period_start} |
| Period End | {batch.period_end} |
| Total Trips Monitored | {batch.trip_count:,} |
| Total VKT (Vehicle km Travelled) | {batch.total_distance_km:,.1f} km |
| Data Source | M-Pesa transaction records + GPS trip logs |

**Monitoring methodology:** Per VM0038 §7, VKT data is derived from
GPS-verified trip records linked to confirmed M-Pesa payment receipts.
Each trip record includes: rider ID (hashed phone), pickup/drop coordinates,
odometer distance, provider confirmation, and timestamp.

---

## 3. Quantification of GHG Emission Reductions

### 3.1 Baseline Emissions (BE)

The baseline scenario is continued use of petrol-powered PSV passenger cars.

**BE formula (VM0038 §4.1):**
```
BE = VKT × AFEC × EF_fuel × WTT_factor
```

| Parameter | Value | Source |
|-----------|-------|--------|
| AFEC (Adjusted Fuel Economy Coeff.) | {AFEC_PSV} L/km | VM0038 Appendix 1, AMS-III.BC |
| EF_petrol | {EF_PETROL} kgCO₂e/L | IPCC 2006 Guidelines Vol.2 |
| WTT factor | {WTT_PETROL} | DEFRA / VM0038 guidance |
| VKT (this period) | {batch.total_distance_km:,.1f} km | GPS trip records |

**Baseline Emissions = {batch.total_baseline_tco2:,.4f} tCO₂e**

### 3.2 Project Emissions (PE)

**PE formula (VM0038 §4.2):**
```
PE = (VKT × EV_kWh/km ÷ η_charger) × EF_grid
```

| Parameter | Value | Source |
|-----------|-------|--------|
| EV energy consumption | {EV_KWH_KM} kWh/km | WLTP, manufacturer data |
| Charger efficiency (L2) | {ETA_L2} | VM0038 §4.3 default |
| EF_grid (Kenya) | {EF_GRID} kgCO₂e/kWh | IEA Emission Factors 2024 |

**Project Emissions = {batch.total_project_tco2:,.4f} tCO₂e**

### 3.3 Leakage (LE)

Leakage discount applied per VM0038 §6: **{LEAKAGE_PCT*100:.0f}%** of gross reduction.

Leakage sources considered:
- Upstream emissions from EV manufacturing (deemed negligible per VM0038 guidance)
- Grid transmission losses (captured in η_charger)
- No modal shift leakage (EV replaces the same PSV trip)

**Leakage = {(batch.total_gross_vcu - batch.total_net_vcu/(1-VCS_BUFFER_PCT)):,.4f} tCO₂e**

### 3.4 Net Emission Reductions (ER)

```
Gross ER = BE - PE             = {batch.total_baseline_tco2 - batch.total_project_tco2:,.4f} tCO₂e
Leakage  = Gross ER × {LEAKAGE_PCT}   = {(batch.total_baseline_tco2 - batch.total_project_tco2)*LEAKAGE_PCT:,.4f} tCO₂e
Net ER   = Gross ER - Leakage  = {batch.total_net_tco2:,.4f} tCO₂e
```

---

## 4. VCU Calculation Summary

| Component | tCO₂e |
|-----------|-------|
| Baseline Emissions (BE) | {batch.total_baseline_tco2:,.4f} |
| Project Emissions (PE) | {batch.total_project_tco2:,.4f} |
| Gross Emission Reduction | {batch.total_gross_vcu / NET_FACTOR:,.4f} |
| Leakage (3%) | {batch.total_gross_vcu / NET_FACTOR * LEAKAGE_PCT:,.4f} |
| Net Emission Reduction | {batch.total_net_tco2:,.4f} |
| VCS Buffer Pool Deduction (10%) | {batch.total_gross_vcu * VCS_BUFFER_PCT:,.4f} |
| **Gross VCUs** | **{batch.total_gross_vcu:,.4f}** |
| **Net VCUs (requested for issuance)** | **{batch.total_net_vcu:,.6f}** |

**VCU Vintage:** {batch.period_start} — {batch.period_end}

---

## 5. Data and Parameters

| Parameter | Value | Monitoring Frequency | Data Source |
|-----------|-------|---------------------|-------------|
| VKT | {batch.total_distance_km:,.1f} km | Per trip | GPS + M-Pesa |
| Fuel type displaced | Petrol | Static | VM0038 default |
| EF_grid | {EF_GRID} kgCO₂e/kWh | Annual update | IEA Emission Factors |
| Charger type | L2 AC | Per installation | Hardware records |
| η_charger | {ETA_L2} | Per charger model | VM0038 default |
| Surge multiplier | Actual | Per trip | Provider API |

---

## 6. Additionality

**Method:** VMD0049 v1.0 — Activity Method (Positive List)

Kenya EV market penetration as of monitoring period: **~0.3%**
VMD0049 positive-list threshold: **5%**
**Status: ADDITIONAL ✓**

The project is not required to demonstrate financial additionality as it
qualifies under the positive list (EV market penetration < 5%).

**Double counting:** Each trip's M-Pesa receipt is a unique, tamper-evident
identifier. No trip is counted under any other GHG program. Credits from the
same charging hardware are not claimed under both fleet adoption and charging
station methodologies per VM0038 §4.4.

---

## 7. Supporting Documents

The following are attached to this submission:

1. `ghg_calculations_{batch.batch_id}.csv` — Per-trip VM0038 calculation table
2. `summary_{batch.batch_id}.json` — Machine-readable batch summary
3. M-Pesa transaction log (separate secure link to registry@verra.org)
4. GPS trip log export (separate secure link)
5. Charger installation certificates (on file, provided on request)

---

*Prepared by {VCS_PROPONENT_NAME} · {VCS_PROPONENT_EMAIL}*
*{now}*
"""
        path.write_text(content, encoding="utf-8")
        logger.debug("Monitoring report written: %s", path)

    def _write_calculations_csv(self, path: Path, trips: list[TripRecord]) -> None:
        fieldnames = [
            "record_id", "trip_id", "date", "phone_hash",
            "provider", "pickup", "destination",
            "distance_km", "vehicle_category", "charger_type",
            "baseline_kg_co2e", "project_kg_co2e",
            "gross_reduction_kg", "leakage_kg", "net_reduction_kg",
            "gross_vcu_tco2e", "net_vcu_tco2e",
            "vcu_value_kes",
            "methodology",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trips:
                gross_kg   = t.baseline_kg - t.project_kg
                leakage_kg = gross_kg * LEAKAGE_PCT
                writer.writerow({
                    "record_id":           t.record_id,
                    "trip_id":             t.trip_id,
                    "date":                datetime.fromtimestamp(t.timestamp, tz=timezone.utc).date().isoformat(),
                    "phone_hash":          hash(t.phone) & 0xFFFFFFFF,
                    "provider":            t.provider,
                    "pickup":              t.pickup,
                    "destination":         t.destination,
                    "distance_km":         round(t.distance_km, 3),
                    "vehicle_category":    t.vehicle_category,
                    "charger_type":        t.charger_type,
                    "baseline_kg_co2e":    round(t.baseline_kg, 4),
                    "project_kg_co2e":     round(t.project_kg,  4),
                    "gross_reduction_kg":  round(gross_kg,       4),
                    "leakage_kg":          round(leakage_kg,     4),
                    "net_reduction_kg":    round(t.net_kg,       4),
                    "gross_vcu_tco2e":     round(t.gross_vcu,    8),
                    "net_vcu_tco2e":       round(t.net_vcu,      8),
                    "vcu_value_kes":       round(t.vcu_value_kes, 4),
                    "methodology":         "Verra VM0038 v1.0",
                })
        logger.debug("Calculations CSV written: %s (%d rows)", path, len(trips))

    def _write_cover_letter(self, path: Path, batch: IssuanceBatch) -> None:
        now     = datetime.now(timezone.utc).strftime("%d %B %Y")
        content = f"""{now}

The Registry Administrator
Verra Registry
2101 L Street NW, Suite 800
Washington, DC 20037
United States

Email: registry@verra.org

Re: VCU Issuance Request — {VCS_PROJECT_NAME}
    VCS Project ID: {VCS_PROJECT_ID or "[PENDING]"}
    Account Number: {VCS_ACCOUNT_NUMBER or "[PENDING]"}
    Batch Reference: {batch.batch_id}
    Monitoring Period: {batch.period_start} to {batch.period_end}

Dear Registry Administrator,

{VCS_PROPONENT_NAME} ("the Project Proponent") hereby submits a request for
issuance of Verified Carbon Units (VCUs) under the Verified Carbon Standard (VCS)
for the above-referenced project.

PROJECT DETAILS

  Project Name:        {VCS_PROJECT_NAME}
  VCS Project ID:      {VCS_PROJECT_ID or "[PENDING REGISTRATION]"}
  Country:             {VCS_PROJECT_COUNTRY}
  Methodology:         {METHODOLOGY}
  Project Type:        Electric Vehicle Charging Systems — EV Fleet Adoption
  Crediting Period:    7 years (renewable)

MONITORING PERIOD AND QUANTIFICATION

  Period Start:            {batch.period_start}
  Period End:              {batch.period_end}
  Total Trips Monitored:   {batch.trip_count:,}
  Total VKT:               {batch.total_distance_km:,.1f} km
  Total Baseline Emissions:{batch.total_baseline_tco2:,.4f} tCO₂e
  Total Project Emissions: {batch.total_project_tco2:,.4f} tCO₂e
  Net Emission Reductions: {batch.total_net_tco2:,.4f} tCO₂e

VCU ISSUANCE REQUESTED

  Gross VCUs:            {batch.total_gross_vcu:,.4f} tCO₂e
  VCS Buffer (10%):      {batch.total_gross_vcu * VCS_BUFFER_PCT:,.4f} tCO₂e
  Net VCUs Requested:    {batch.total_net_vcu:,.6f} tCO₂e
  Vintage Year(s):       {batch.period_start[:4]}{"–" + batch.period_end[:4] if batch.period_start[:4] != batch.period_end[:4] else ""}

ADDITIONALITY

This project qualifies under the VMD0049 v1.0 positive list activity method.
Kenya's EV market penetration (approximately 0.3%) is below the 5% threshold,
confirming the project's additionality without further barrier analysis.

VERIFICATION

{"Verification by " + VVB_NAME + " (" + VVB_ACCREDITATION + ") is in progress." if VVB_NAME else "We will engage an accredited VVB and submit the verification report separately."}

ATTACHED DOCUMENTS

  1. VCS Monitoring Report (monitoring_report_{batch.batch_id}.md)
  2. GHG Calculations Spreadsheet (ghg_calculations_{batch.batch_id}.csv)
  3. Batch Summary (summary_{batch.batch_id}.json)

We confirm that:
(a) The data presented in this monitoring report is accurate and complete.
(b) The GHG emission reductions have not been and will not be claimed under
    any other GHG program or mechanism.
(c) All monitoring data is available for inspection by the Registry Administrator
    or an authorised VVB upon request.

Please do not hesitate to contact us at {VCS_PROPONENT_EMAIL} if you require
any additional information.

Yours sincerely,

{VCS_PROPONENT_NAME}
{VCS_PROPONENT_EMAIL}
VCS Account: {VCS_ACCOUNT_NUMBER or "[PENDING]"}
Batch Reference: {batch.batch_id}
"""
        path.write_text(content, encoding="utf-8")
        logger.debug("Cover letter written: %s", path)

    def _write_summary_json(self, path: Path, batch: IssuanceBatch) -> None:
        summary = {
            "schema_version":         "1.0",
            "generated_at":           datetime.now(timezone.utc).isoformat(),
            "batch_id":               batch.batch_id,
            "vcs_project_id":         VCS_PROJECT_ID,
            "project_name":           VCS_PROJECT_NAME,
            "proponent":              VCS_PROPONENT_NAME,
            "methodology":            METHODOLOGY,
            "additionality_method":   "VMD0049 v1.0",
            "monitoring_period": {
                "start":              batch.period_start,
                "end":                batch.period_end,
            },
            "monitoring_data": {
                "total_trips":        batch.trip_count,
                "total_vkt_km":       round(batch.total_distance_km, 2),
            },
            "ghg_quantification": {
                "baseline_tco2e":     round(batch.total_baseline_tco2,  4),
                "project_tco2e":      round(batch.total_project_tco2,   4),
                "net_reduction_tco2e":round(batch.total_net_tco2,       4),
                "gross_vcu":          round(batch.total_gross_vcu,      6),
                "vcs_buffer_10pct":   round(batch.total_gross_vcu * VCS_BUFFER_PCT, 6),
                "net_vcu_requested":  round(batch.total_net_vcu,        6),
            },
            "key_parameters": {
                "ef_grid_kg_kwh":     EF_GRID,
                "ef_petrol_kg_l":     EF_PETROL,
                "wtt_petrol":         WTT_PETROL,
                "afec_l_km":          AFEC_PSV,
                "ev_kwh_km":          EV_KWH_KM,
                "eta_l2_charger":     ETA_L2,
                "leakage_pct":        LEAKAGE_PCT,
                "vcs_buffer_pct":     VCS_BUFFER_PCT,
                "net_factor":         NET_FACTOR,
            },
            "submission_status":      batch.status.value,
        }
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.debug("Summary JSON written: %s", path)

    @staticmethod
    def _zip_package(zip_path: Path, files: list[Path]) -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.exists():
                    zf.write(f, f.name)
        logger.info(
            "Zipped %d files → %s (%.1f KB)",
            len(files), zip_path, zip_path.stat().st_size / 1024,
        )
