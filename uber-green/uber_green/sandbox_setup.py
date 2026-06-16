"""
uber_green/sandbox_setup.py — Go Green
────────────────────────────────────────────────────────────────────────────
Uber sandbox setup utilities.

The Uber Guest Rides sandbox requires a "run" to be created before making
estimate/trip calls.  This module handles that lifecycle:

  1. POST /v1/guests/sandbox/run   → create a sandbox run → run_id
  2. Use run_id as x-uber-sandbox-runuuid header on estimates + trip calls
  3. GET /v1/guests/sandbox/run/{run_id} → check run state

Docs:
  https://developer.uber.com/docs/guest-rides/guides/sandbox

Usage:
    python -m uber_green.sandbox_setup          # create run + test estimates
    python -m uber_green.sandbox_setup --trip   # also create a trip
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from .auth import token_manager
from .client import uber_client, UberClient
from .models import Location

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Nairobi test coordinates: Westlands → Karen
TEST_PICKUP  = Location(-1.2636, 36.8030, address="Westlands, Nairobi")
TEST_DROPOFF = Location(-1.3180, 36.7070, address="Karen, Nairobi")


def create_sandbox_run(client: UberClient) -> str:
    """
    POST /v1/guests/sandbox/run
    Returns the run_id to use as x-uber-sandbox-runuuid.
    """
    raw = client._request("POST", "/v1/guests/sandbox/run", json={})
    run_id = raw.get("run_id", "")
    if not run_id:
        raise RuntimeError(f"No run_id in sandbox response: {raw}")
    logger.info("Sandbox run created: %s", run_id)
    return run_id


def get_sandbox_run(client: UberClient, run_id: str) -> dict:
    """GET /v1/guests/sandbox/run/{run_id}"""
    return client._request("GET", f"/v1/guests/sandbox/run/{run_id}")


def test_estimates(run_id: str) -> None:
    """Test the estimates endpoint with Nairobi Westlands → Karen."""
    logger.info("Testing estimates: Westlands → Karen")
    resp = uber_client.get_estimates(
        pickup           = TEST_PICKUP,
        dropoff          = TEST_DROPOFF,
        sandbox_run_uuid = run_id,
    )
    print(f"\n{'─'*60}")
    print(f"Products returned: {len(resp.product_estimates)}")
    print(f"ETAs unavailable:  {resp.etas_unavailable}")
    print(f"Fares unavailable: {resp.fares_unavailable}")
    print(f"{'─'*60}")

    green = resp.green_products()
    print(f"Green/EV products: {len(green)}")
    for p in resp.product_estimates:
        marker = " 🌿" if p.is_green else ""
        fare   = p.fare.display if p.fare else "N/A"
        eta    = f"{p.pickup_estimate}m" if p.pickup_estimate is not None else "N/A"
        print(f"  [{p.product_id[:8]}...] {p.display_name:<25} fare={fare:<12} eta={eta}{marker}")

    if green:
        best = green[0]
        print(f"\n✅ Best Green product: {best.display_name}")
        print(f"   fare_id: {best.fare.fare_id if best.fare else 'N/A'}")
        print(f"\n💡 Set in .env:  UBER_GREEN_PRODUCT_ID={best.product_id}")

    print(f"{'─'*60}\n")


def test_trip(run_id: str, product_id: str, fare_id: str) -> None:
    """Create a sandbox trip and poll until driver is assigned."""
    from .adapter import UberGreenAdapter
    adapter = UberGreenAdapter()

    logger.info("Creating sandbox trip: product=%s", product_id)
    detail = adapter.book_ride(
        product_id      = product_id,
        fare_id         = fare_id,
        pickup_lat      = TEST_PICKUP.latitude,
        pickup_lon      = TEST_PICKUP.longitude,
        drop_lat        = TEST_DROPOFF.latitude,
        drop_lon        = TEST_DROPOFF.longitude,
        rider_name      = "Go Green Test Rider",
        rider_phone     = "+254700000000",
        rider_email     = "test@gogreen.co.ke",
        pickup_address  = TEST_PICKUP.address,
        dropoff_address = TEST_DROPOFF.address,
    )

    print(f"\n{'─'*60}")
    print(f"Trip created:  {detail.request_id}")
    print(f"Status:        {detail.status}")

    logger.info("Polling for driver assignment (max 60s)…")
    final = uber_client.poll_until_driver(detail.request_id, max_wait_s=60)
    print(f"Final status:  {final.status}")
    if final.driver:
        print(f"Driver:        {final.driver.name}  ⭐{final.driver.rating}")
    if final.vehicle:
        print(f"Vehicle:       {final.vehicle.make} {final.vehicle.model}  [{final.vehicle.license_plate}]")
    print(f"{'─'*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Uber Guest Rides sandbox tester")
    parser.add_argument("--trip", action="store_true", help="Also create a test trip")
    parser.add_argument("--run-id", help="Reuse an existing sandbox run ID")
    args = parser.parse_args()

    if not token_manager.is_configured:
        print("❌  Set UBER_CLIENT_ID and UBER_CLIENT_SECRET first.")
        print("    Register at https://developer.uber.com → Create Application")
        return

    print(f"✅  Credentials: {os.environ['UBER_CLIENT_ID'][:8]}***")
    print(f"    Mode: {'SANDBOX' if os.environ.get('UBER_SANDBOX','true').lower()=='true' else 'PRODUCTION'}")

    run_id = args.run_id or create_sandbox_run(uber_client)
    print(f"\n💡 Set in .env:  UBER_SANDBOX_RUN_UUID={run_id}\n")

    test_estimates(run_id)

    if args.trip:
        # Discover product_id from estimates first
        resp = uber_client.get_estimates(TEST_PICKUP, TEST_DROPOFF, sandbox_run_uuid=run_id)
        green = resp.green_products()
        if not green:
            print("⚠️  No Green products found — cannot test trip creation.")
            return
        p = green[0]
        test_trip(run_id, p.product_id, p.fare.fare_id if p.fare else "")


if __name__ == "__main__":
    main()
