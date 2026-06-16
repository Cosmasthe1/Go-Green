"""
verra_registry — Go Green × Verra Registry Integration
=======================================================

What the Verra Registry actually provides (as of 2025):
  • A web portal at registry.verra.org (human-operated, not a REST API)
  • The VCS Program process: register project → VVB verification → issuance request → invoice → credits issued
  • Public data scraping via registry.verra.org/app/search (HTML / undocumented JSON)
  • No public REST API for issuance requests or credit transfers

What this module implements:
  1.  VerraRegistryClient       — public registry scraper (project search, VCU serial lookup)
  2.  IssuanceRequestBuilder    — generates the complete Verra issuance package (monitoring
                                  report, calculations spreadsheet, cover letter) that a
                                  Project Proponent submits to registry@verra.org
  3.  IssuanceQueue             — accumulates per-trip VCU calculations, batches them into
                                  periodic (monthly / quarterly) issuance requests per the
                                  VCS annual monitoring period requirement
  4.  IssuanceWorkflow          — orchestrates the full pipeline:
                                  accumulate → batch → build package → notify → track status

The "auto-submit" path:
  Go Green cannot fully automate VCU issuance because Verra requires:
    (a) A registered VCS project with an approved Project Description
    (b) An accredited VVB to verify the Monitoring Report
    (c) Verra staff review + invoice payment before credits are issued
  
  What CAN be automated end-to-end:
    ✓ Continuous monitoring data collection (per trip, per day, per period)
    ✓ VM0038 calculations (already in carbon/ghg_calculator.py)
    ✓ Monitoring Report generation (Word/Excel + PDF, following VCS template)
    ✓ Submission email to registry@verra.org with all required attachments
    ✓ Status tracking and notification when credits land in the registry account
    ✓ Public registry scraping to verify issued serial numbers
"""

from .client   import VerraRegistryClient
from .queue_   import IssuanceQueue, TripRecord
from .builder  import IssuanceRequestBuilder, MonitoringReport
from .workflow import IssuanceWorkflow

__all__ = [
    "VerraRegistryClient",
    "IssuanceQueue",
    "TripRecord",
    "IssuanceRequestBuilder",
    "MonitoringReport",
    "IssuanceWorkflow",
]
