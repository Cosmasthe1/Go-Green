# 🌿 Go Green × Verra Registry Integration

> Auto-generates Verra VM0038 monitoring reports and submits VCU issuance requests to `registry@verra.org`.

---

## The Honest Truth About "Automating" Verra

Before anything else — here is exactly what can and cannot be automated with the Verra Registry:

| Step | Automated? | How |
|------|-----------|-----|
| Monitoring data collection (per trip) | ✅ Fully | M-Pesa receipts + GPS logs → `IssuanceQueue` |
| VM0038 GHG calculations | ✅ Fully | `carbon/ghg_calculator.py` |
| Monitoring report generation | ✅ Fully | `IssuanceRequestBuilder` → Markdown + CSV + JSON |
| Submission email to Verra | ✅ Fully | `EmailSubmitter` → SMTP to `registry@verra.org` |
| Batch threshold monitoring | ✅ Fully | `IssuanceQueue.check_and_promote()` daily |
| VVB verification | ❌ Manual | Must hire an ISO 14065-accredited VVB |
| Verra staff review | ❌ Manual | Verra reviews the monitoring report + VVB report |
| Invoice payment | ❌ Manual | Verra issues an invoice; you pay before credits are issued |
| VCU serial number assignment | ❌ Manual | Verra assigns serials after invoice is paid |
| Public registry confirmation | ✅ Fully | `VerraRegistryClient` scrapes `registry.verra.org` |

**Why can't we call a Verra REST API?** The Verra Registry (`registry.verra.org`) does not publish a documented API for issuance requests. All submissions are made by emailing `registry@verra.org` with required documents attached. The web portal is human-operated. This is by design — carbon credits require human oversight at the verification and issuance steps.

---

## File Structure

```
verra_registry/
├── __init__.py              Module exports
├── client.py                Read-only Verra registry scraper (project search, VCU lookup)
├── queue_.py                SQLite-backed issuance queue (accumulates trips → batches)
├── builder.py               Monitoring report + CSV + cover letter generator
├── submitter.py             SMTP email submitter to registry@verra.org
├── workflow.py              Full pipeline orchestrator + background scheduler
└── orchestrator_patch.py   One-line patch for GoGreenOrchestrator
```

---

## Architecture

```
Per trip (real-time):

  GoGreenOrchestrator._handle_confirmation()
          │ (after M-Pesa confirmed + VM0038 calculated)
          ▼
  workflow.on_trip_complete(TripRecord)
          │
          ├─ queue.add_trip()          → written to SQLite
          └─ queue.check_and_promote() → is threshold met?
                    │ YES
                    ▼
          workflow.submit_batch()
                    │
                    ├─ builder.build()       → .md + .csv + .txt + .json → .zip
                    ├─ submitter.submit()    → SMTP → registry@verra.org
                    └─ queue.mark_submitted() → ref stored for tracking

Background (daily/weekly):

  Scheduler thread
    ├─ Daily:   check_and_promote()               → catch any missed thresholds
    └─ Weekly:  check_registry_for_new_issuances() → scrape registry.verra.org

Manual triggers (after human steps):

  workflow.mark_verified(batch_id, vvb_report_url)  → after VVB issues report
  workflow.mark_issued(batch_id, serial_start, end)  → after Verra issues credits
```

---

## Batch Thresholds

A batch is promoted from `OPEN → READY → SUBMITTED` when **any** of these is met:

| Threshold | Default | Env Var |
|-----------|---------|---------|
| Minimum VCUs | 50 tCO₂e | `MIN_VCU_THRESHOLD` |
| Minimum trips | 100 | `MIN_TRIPS` |
| Maximum period age | 90 days | `MAX_PERIOD_DAYS` |

**Why 50 tCO₂e minimum?** Verra charges an issuance fee (~$0.10–0.20/VCU + fixed admin fee). Batches smaller than ~50 tCO₂e may not be economically viable after fees. Adjust to match your project's economics.

---

## Setup

### 1. Register your VCS project

1. Create an account at [registry.verra.org](https://registry.verra.org)
2. Submit a Project Description (PD) following the VM0038 template
3. Hire an accredited VVB to validate the PD
4. After validation approval → project is listed → you receive a **VCS Project ID**
5. Set `VCS_PROJECT_ID` in your `.env`

This process typically takes **3–6 months** and costs **$5,000–$30,000** in VVB fees.

### 2. Configure environment variables

```bash
cp .env.verra.example .env.verra
nano .env.verra      # fill in VCS_PROJECT_ID, SMTP credentials, etc.
source .env.verra
```

### 3. Wire into Go Green

In `app.py`, add **two lines** before launching:

```python
from verra_registry.orchestrator_patch import patch_orchestrator
from orchestrator_agent import GoGreenOrchestrator

patch_orchestrator(GoGreenOrchestrator)
```

That's it. Every confirmed trip now flows into the issuance queue automatically.

### 4. Test with a dry run

```python
from verra_registry import IssuanceWorkflow
from verra_registry.queue_ import TripRecord
import time

workflow = IssuanceWorkflow(auto_schedule=False)

# Add a test trip
trip = TripRecord(
    trip_id="TEST-001", phone="+254712345678",
    timestamp=time.time(), pickup="Westlands", destination="Karen",
    provider="Uber", distance_km=9.4, charger_type="L2",
    vehicle_category="psv_passenger_car",
    baseline_kg=2.912, project_kg=0.115,
    net_kg=2.718, gross_vcu=0.002718, net_vcu=0.002446,
    vcu_value_kes=3.97,
)
workflow.queue.add_trip(trip)

# Force submit (ignores thresholds)
batch = workflow.force_submit(output_dir="/tmp/verra_test")
print(f"Status: {batch.status}")
# → Check /tmp/verra_test/ for generated documents
```

---

## Generated Documents

After `submit_batch()`, the following files are created and zipped:

### `monitoring_report_{batch_id}.md`
Full VCS monitoring report following the VM0038 §7 template:
- Project summary, monitoring period
- Baseline emissions (BE) with formula and parameters
- Project emissions (PE)
- Leakage calculation
- Net emission reductions
- Additionality statement (VMD0049)
- Double counting avoidance
- VCU calculation summary table

### `ghg_calculations_{batch_id}.csv`
Per-trip calculation table (required as the "Calculation Spreadsheet"):

| Column | Description |
|--------|-------------|
| `record_id` | Unique record identifier |
| `trip_id` | M-Pesa transaction reference |
| `date` | Trip date |
| `phone_hash` | Hashed rider phone (privacy) |
| `distance_km` | GPS-verified VKT |
| `baseline_kg_co2e` | BE for this trip |
| `project_kg_co2e` | PE for this trip |
| `net_reduction_kg` | Net ER for this trip |
| `net_vcu_tco2e` | VCUs earned this trip |

### `cover_letter_{batch_id}.txt`
Formal submission letter addressed to The Registry Administrator, Verra.

### `summary_{batch_id}.json`
Machine-readable batch summary with all key parameters.

---

## Batch Status Lifecycle

```
OPEN  →  READY  →  SUBMITTED  →  VERIFIED  →  ISSUED
                                     ↑              ↑
                               (VVB report)   (Verra issues)
                                (manual)        (manual)

Any stage → FAILED (on error)
```

Track status via:
```python
batches = workflow.get_all_batches()
for b in batches:
    print(f"{b.batch_id}: {b.status.value} | {b.total_net_vcu:.4f} VCU | {b.trip_count} trips")
```

---

## Production Checklist

- [ ] VCS Project registered and ID obtained
- [ ] VVB engaged and contracted
- [ ] `VCS_PROJECT_ID` set in environment
- [ ] `VCS_ACCOUNT_NUMBER` set
- [ ] SMTP credentials configured and tested
- [ ] `registry@gogreen.co.ke` email address set up
- [ ] Batch thresholds tuned to your fleet size
- [ ] `MIN_VCU_THRESHOLD` adjusted based on Verra fee economics
- [ ] `orchestrator_patch.patch_orchestrator(GoGreenOrchestrator)` added to `app.py`
- [ ] M-Pesa transaction log archival in place (required for VVB audit)
- [ ] GPS trip log export pipeline confirmed

---

## VCS Process Timeline (realistic)

| Stage | Typical Duration | Who |
|-------|-----------------|-----|
| Project Description preparation | 4–8 weeks | Go Green + consultant |
| VVB validation of PD | 8–16 weeks | VVB |
| Verra PD approval | 4–8 weeks | Verra staff |
| Accumulate first batch (50 tCO₂e) | 1–6 months | Go Green fleet |
| VVB monitoring report verification | 4–8 weeks | VVB |
| Verra issuance review + invoice | 2–4 weeks | Verra staff |
| **First VCUs in registry** | **~12–18 months from start** | |
| Subsequent annual issuances | 8–12 weeks per cycle | |

---

## References

- [VCS Program Guide](https://verra.org/programs/verified-carbon-standard/)
- [VM0038 v1.0 Methodology](https://verra.org/methodologies/vm0038-methodology-for-electric-vehicle-charging-systems-v1-0/)
- [VMD0049 Additionality](https://verra.org/wp-content/uploads/2022/06/VMD0049-v1.0.pdf)
- [VCS Project Registration](https://registry.verra.org)
- [Accredited VVBs List](https://verra.org/programs/verified-carbon-standard/vvbs/)
- [IEA Emission Factors 2024](https://www.iea.org/data-and-statistics/data-product/emissions-factors-2024)
