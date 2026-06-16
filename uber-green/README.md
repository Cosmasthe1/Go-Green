# 🚗 Go Green × Uber Green — Live API Integration

Real Uber Green ride estimates and bookings via the **Uber Guest Rides API** (`guests.trips` scope, OAuth2 `client_credentials`).

---

## Architecture

```
GoGreenOrchestrator
    └── RideAgent.get_offers()
              │
              ▼
    UberGreenAdapter.get_offers()
              │
        ┌─────┴──────────────────┐
        │  Live path             │  Fallback path
        │  (credentials set)     │  (no creds or API error)
        ▼                        ▼
  POST /v1/guests/             Price model
  trips/estimates              + deep-link
        │
        ▼
  Filter: .is_green
  (display_name contains
  "green", "electric", "ev")
        │
        ▼
  USD → KES conversion
        │
        ▼
  RideOffer (DataSource.LIVE_API)
```

---

## Files

| File | Purpose |
|---|---|
| `uber_green/auth.py` | OAuth2 `client_credentials` token manager (thread-safe, auto-refresh) |
| `uber_green/models.py` | Typed request/response models mirroring Uber API schema exactly |
| `uber_green/client.py` | HTTP client — estimates, create trip, get status, cancel, poll |
| `uber_green/adapter.py` | Go Green ↔ Uber API adapter (live + price-model fallback) |
| `uber_green/orchestrator_patch.py` | Monkey-patches `GoGreenOrchestrator` with live Uber calls |
| `uber_green/sandbox_setup.py` | Sandbox run creation + interactive test script |
| `uber_green/fx.py` | USD → KES exchange rate (Open Exchange Rates or fallback) |

---

## Setup

### 1. Register on Uber Developer Platform

1. Go to [developer.uber.com](https://developer.uber.com) → **My Apps** → **Create New App**
2. Under **Authorization** → enable `client_credentials` grant type
3. Add scope: `guests.trips`
4. Copy your **Client ID** and **Client Secret**

> For **production** access (real rides), contact your Uber Business Development representative. Sandbox access is available immediately after app creation.

### 2. Configure environment variables

```bash
cp .env.uber.example .env.uber
# Edit .env.uber with your credentials
source .env.uber
```

### 3. Discover your Uber Green product ID (Nairobi)

```bash
# Create a sandbox run and discover product IDs for the Nairobi market
python -m uber_green.sandbox_setup

# Sample output:
# Products returned: 6
# [abc123...] UberX           fare=$8-11    eta=4m
# [def456...] Uber Green      fare=$9-13    eta=6m  🌿
# [ghi789...] Comfort         fare=$12-16   eta=5m
#
# ✅ Best Green product: Uber Green
#    fare_id: 6e642142-...
#
# 💡 Set in .env: UBER_GREEN_PRODUCT_ID=def456...
#    Set in .env: UBER_SANDBOX_RUN_UUID=run_abc123...
```

### 4. Wire into Go Green

In `app.py` or `orchestrator_agent.py`, add **before** `GoGreenOrchestrator` is instantiated:

```python
from uber_green.orchestrator_patch import patch_orchestrator
from orchestrator_agent import GoGreenOrchestrator

patch_orchestrator(GoGreenOrchestrator)
# All subsequent orchestrator instances use live Uber API
```

---

## API Endpoints Used

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/oauth/v2/token` | Get OAuth2 Bearer token |
| `POST` | `/v1/guests/trips/estimates` | Get fare + ETA for all products |
| `POST` | `/v1/guests/trips` | Create (book) a trip |
| `GET`  | `/v1/guests/trips/{id}` | Get trip status + driver details |
| `GET`  | `/v1/guests/trips/{id}/status` | Lightweight status poll |
| `DELETE` | `/v1/guests/trips/{id}` | Cancel a trip |
| `POST` | `/v1/guests/sandbox/run` | Create sandbox test run |

---

## Token Flow

```
UBER_CLIENT_ID + UBER_CLIENT_SECRET
            │
            ▼
POST https://auth.uber.com/oauth/v2/token
    grant_type=client_credentials
    scope=guests.trips
            │
            ▼
    { "access_token": "...", "expires_in": 2592000 }   (30 days)
            │
            ▼
    Authorization: Bearer <token>
    (all subsequent API calls)
```

Token is cached in-process and refreshed automatically 60 seconds before expiry.

---

## Estimates Response → RideOffer

```
POST /v1/guests/trips/estimates
    {
      "pickup":  { "latitude": -1.2636, "longitude": 36.8030 },
      "dropoff": { "latitude": -1.3180, "longitude": 36.7070 }
    }

Response:
    {
      "product_estimates": [
        {
          "product": {
            "product_id":    "def456...",
            "display_name":  "Uber Green",
            "short_description": "Electric vehicle"
          },
          "estimate_info": {
            "fare": {
              "currency_code": "USD",
              "value":         11.50,
              "display":       "$11.50",
              "fare_id":       "6e642142-...",
              "fare_breakdown": [...]
            },
            "pickup_estimate": 6,
            "trip": {
              "distance_estimate": 9.4,
              "duration_estimate": 1320,
              "distance_unit":     "km"
            }
          }
        }
      ]
    }

Mapped to RideOffer:
    price_kes     = 11.50 × 130 = KSh 1,495
    eta_min       = 6
    duration_min  = 1320 / 60 = 22
    fare_id       = "6e642142-..." (locked price on booking)
    data_source   = DataSource.LIVE_API
```

---

## Fallback Behaviour

The adapter **never raises** to the caller. If anything fails:

| Failure | Behaviour |
|---|---|
| No credentials set | Price model + Uber app deep-link |
| 401 Unauthorized | Invalidate token → retry once → price model |
| 429 Rate Limit | Price model |
| Timeout (12s) | Price model |
| No Green products found | Price model |
| Any other exception | Price model |

The deep-link (`uber://?action=setPickup&...`) opens the Uber app pre-filled with the rider's pickup and destination — so riders can still book even without live API credentials.

---

## Production Checklist

- [ ] Set `UBER_SANDBOX=false`
- [ ] Get production approval from Uber BD representative
- [ ] Set `UBER_ORG_UUID` (Uber for Business organisation UUID)
- [ ] Discover production `UBER_GREEN_PRODUCT_ID` for Nairobi market
- [ ] Set `OPENEXCHANGERATES_APP_ID` for live USD/KES rate
- [ ] Implement webhook receiver for trip status updates (optional but recommended)
- [ ] Add `UBER_CLIENT_SECRET` to a secrets manager (never in source code)

---

## References

- [Guest Rides API — Authentication](https://developer.uber.com/docs/guest-rides/guides/authentication)
- [Guest Rides API — Pulling Product Estimates](https://developer.uber.com/docs/guest-rides/guest-ride-api-build-guide/pulling-product-estimates)
- [Guest Rides API — Requesting a Trip](https://developer.uber.com/docs/guest-rides/guest-ride-api-build-guide/requesting-a-trip)
- [POST /v1/guests/trips/estimates](https://developer.uber.com/docs/guest-rides/references/api/v1/guest-trips-estimates-post)
- [POST /v1/guests/trips](https://developer.uber.com/docs/guest-rides/references/api/v1/guest-trips-post)
- [GET /v1/guests/trips/{request_id}](https://developer.uber.com/docs/guest-rides/references/api/v1/guest-trips-request_id-get)
