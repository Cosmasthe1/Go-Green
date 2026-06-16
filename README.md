# 🌿 Go Green — AI EV Ride Ordering Agent

> **Order EV-only rides via WhatsApp · Pay via M-Pesa · Earn Verra VM0038 Carbon Credits**

Go Green is a fully agentic, multi-model AI system that orchestrates EV ride bookings across 7 Kenyan and global providers, processes payments through Safaricom's Daraja API, and automatically calculates and accrues Verra VM0038 Verified Carbon Units (VCUs) for every completed ride.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Agent Roster](#agent-roster)
- [EV Provider Network](#ev-provider-network)
- [Carbon Credit Engine](#carbon-credit-engine)
- [WhatsApp Conversation Flow](#whatsapp-conversation-flow)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Carbon Credit Methodology](#carbon-credit-methodology)
- [Fleet Categories](#fleet-categories)
- [Charging Hardware Network](#charging-hardware-network)
- [Development Guide](#development-guide)
- [Production Deployment](#production-deployment)
- [Roadmap](#roadmap)

---

## Overview

Go Green connects riders in Nairobi to a network of EV-only taxis, buses, matatus, and bikes via the world's most ubiquitous interface — WhatsApp. Every completed trip:

1. **Books** an EV ride from 7 competing providers (best price wins)
2. **Pays** via M-Pesa STK Push to the rider's WhatsApp-registered number
3. **Earns** Verra-certified carbon credits calculated under methodology VM0038 v1.0
4. **Accrues** VCUs to the rider's personal carbon portfolio, redeemable as cash or green bonds

At scale — e-bikes, PSV passenger cars, matatus, transit buses, and construction machinery — Go Green transforms Kenya's transport fleet into a real-time carbon credit generation machine.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Go Green Platform                                │
│                                                                         │
│  WhatsApp (Twilio / Meta)  ←→  Flask Webhook  ←→  WhatsApp Agent       │
│                                                         │               │
│                                              GoGreenOrchestrator        │
│                                                         │               │
│              ┌──────────────┬──────────────┬────────────┴──────────┐   │
│              │ LocationAgent│  RideAgent   │  PaymentAgent │CarbonAgent│ │
│              │  geocode,    │  7 providers │  M-Pesa STK  │VM0038 VCU│  │
│              │  Nairobi map │  parallel    │  Daraja API  │  Verra   │  │
│              └──────────────┴──────────────┴──────────────┴──────────┘  │
│                                                                         │
│  BaseAgent (LLM core · ShortTermMemory · LongTermMemory · ToolRegistry) │
│                                                                         │
│  MCP Servers: [filesystem] [places] [history] [carbon-ledger]           │
│  HITL Gate: rider confirms booking before payment fires                 │
│                                                                         │
│  Gradio UI (port 7860)         Carbon Dashboard (port 7861)             │
│  Flask Webhook (port 5000)                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Design Principles

- **Single base agent** — every specialised agent inherits from `BaseAgent`, which manages the Anthropic API client, tool-call loop (up to 12 iterations), short-term sliding-window memory, and long-term key-value memory.
- **Stateful sessions** — `TripSession` tracks each rider's booking state machine (`IDLE → LOCATING → SHOWING_RIDES → AWAITING_CHOICE → CONFIRMING → PAYING → BOOKED`).
- **Carbon-first** — the GHG engine is not an afterthought. It fires as Step 4 of every confirmed trip and its result is persisted alongside the ride record.
- **Provider-agnostic payments** — the WhatsApp channel supports both Twilio and Meta Cloud API via a single environment variable switch.

---

## File Structure

```
gogreen/
│
├── app.py                        # Entry point: Gradio UI + Flask webhook (dual-port)
├── base_agent.py                 # Abstract AI model wrapper (shared by all agents)
├── orchestrator_agent.py         # GoGreenOrchestrator + 4 specialised agents
├── whatsapp_agent.py             # WhatsApp webhook handler (Twilio + Meta)
├── providers.py                  # 7 EV provider adapters + RideOffer model
├── mpesa.py                      # Safaricom Daraja API: OAuth, STK Push, STK Query
├── carbon_dashboard.py           # Standalone Gradio carbon credit dashboard
├── requirements.txt              # Python dependencies
│
└── carbon/                       # Verra VM0038 Carbon Credit Engine
    ├── __init__.py               # Module exports
    ├── verra_constants.py        # All emission factors, AFEC, VCU pricing (VM0038)
    ├── ghg_calculator.py         # BE / PE / ER / VCU calculation engine
    └── carbon_agent.py           # AI agent + CarbonLedger (per-rider VCU accrual)
```

---

## Agent Roster

### `BaseAgent` (`base_agent.py`)
Abstract base class shared by every agent. Provides:
- `ShortTermMemory` — sliding window of 30 turns, injected into every API call
- `LongTermMemory` — persistent key-value store (rider profile, trip history, saved places, carbon ledger)
- `ToolRegistry` — registers Python callables as Anthropic tool schemas; handles the full tool-use loop
- `_agentic_loop()` — retries up to 12 tool-call iterations until the model returns `end_turn`

### `LocationAgent`
Parses free-text rider messages to extract pickup and destination, then geocodes both against a 35-landmark Nairobi coordinate dictionary. Falls back to CBD coordinates with jitter for unknown addresses. In production: replace `_geocode()` with Google Maps Geocoding API.

**Tools:** `geocode(address) → {lat, lon}`

### `RideAgent`
Queries all 7 EV providers in parallel using `ThreadPoolExecutor`. Each provider adapter calculates haversine distance, applies its base fare + per-km rate, surge multiplier, and returns a `RideOffer` dataclass. Results are sorted by price ascending.

**Tools:** `fetch_rides(pickup_lat, pickup_lon, drop_lat, drop_lon) → offers[]`

### `PaymentAgent`
Normalises the rider's WhatsApp-registered phone number (any Kenyan format → `2547XXXXXXXX`) and initiates a Safaricom Daraja STK Push. Returns checkout request ID for polling. Falls back to simulated success in sandbox/demo mode.

**Tools:** `mpesa_push(phone, amount_kes, trip_id) → {success, checkout_request_id, customer_msg}`

### `CarbonAgent` (`carbon/carbon_agent.py`)
Implements Verra VM0038 v1.0. After every confirmed M-Pesa payment, calculates:
- Baseline Emissions (BE) — what the equivalent ICE trip would have emitted
- Project Emissions (PE) — actual grid electricity footprint via Kenya EF
- Net Emission Reductions → Verified Carbon Units (VCUs)

Accrues VCUs to the rider's `CarbonLedger` (backed by `LongTermMemory`) and returns a WhatsApp-formatted carbon summary.

**Tools:** `calculate_trip_carbon`, `calculate_fleet_carbon`, `calculate_construction_carbon`, `get_rider_carbon_summary`, `project_annual_credits`

### `GoGreenOrchestrator`
The stateful coordinator. One instance per active rider session (keyed by phone number). Manages the `TripSession` state machine, fires HITL checkpoint before payment, wires MCP servers, and sequences all 4 agents.

---

## EV Provider Network

| # | Provider | Region | Ride Type | EV Models | Base Fare | Rate/km |
|---|----------|--------|-----------|-----------|-----------|---------|
| 1 | **Uber** | Global | Uber Green | Tesla Model 3, Nissan Leaf | KSh 120 | KSh 55 |
| 2 | **Bolt** | Global | Bolt EV | BYD Atto 3, MG ZS EV | KSh 90 | KSh 42 |
| 3 | **Yego** | Africa | Yego EV | Hyundai IONIQ 5, BYD Dolphin | KSh 100 | KSh 48 |
| 4 | **Faras** | Africa | Faras Green | Volkswagen ID.4, MG4 EV | KSh 85 | KSh 40 |
| 5 | **Little Cabs** | Africa | Little EV | Nissan Leaf, BYD e6 | KSh 95 | KSh 45 |
| 6 | **Wasili** | Africa | Wasili EV | BYD Atto 3, Great Wall ORA | KSh 80 | KSh 38 |
| 7 | **Weego** | Africa | Weego EV | BYD Yuan Plus, Geely Geometry C | KSh 88 | KSh 44 |

All prices are subject to surge pricing. Promo codes (`GREEN10`, `EVRIDE5`) are applied automatically when active.

---

## Carbon Credit Engine

### VM0038 Core Formula

Every completed EV trip generates Verified Carbon Units via:

```
ER_y  =  BE_y  −  PE_y  −  LE_y

BE_y  =  distance_km × AFEC × EF_fuel × WTT_factor        (Baseline Emissions)
PE_y  =  (electricity_kWh ÷ η_charger) × EF_grid           (Project Emissions)
LE_y  =  ER_y × 0.03                                       (Leakage, 3%)
VCU_y =  ER_y × NET_VCU_FACTOR                             (after VCS buffer 10%)
```

**Kenya Parameters (IEA 2024):**

| Parameter | Value | Source |
|-----------|-------|--------|
| Grid EF | 0.061 kgCO₂e/kWh | IEA Emission Factors 2024 |
| Petrol EF | 2.296 kgCO₂e/L × WTT 1.19 | IPCC 2006 Vol.2 |
| Diesel EF | 2.703 kgCO₂e/L × WTT 1.21 | IPCC 2006 Vol.2 |
| Charger η (L1/L2/DCFC) | 85.5% / 90.0% / 92.3% | VM0038 §4.3 |
| NET_VCU_FACTOR | 0.873 | 3% leakage + 10% VCS buffer |
| VCU spot price | ~$12.50 / tCO₂e | Verra registry avg |
| Crediting period | 7 years (renewable ×2) | VM0038 §5 |
| Additionality | VMD0049 positive list | Kenya EV ~0.3% < 5% |

### Supporting Methodologies

- **VMD0049** — Additionality determination: Kenya's EV market penetration (~0.3%) is well below the 5% positive-list threshold, confirming all Go Green charging stations as **additional**.
- **VMR0004 v2.0** — Fleet vehicle efficiency improvement (Oct 2024): covers non-road mobile machinery including excavators, wheel loaders, cranes, and forklifts using operating-hours fuel displacement.
- **AMS-III.BC** — CDM small-scale methodology for emission reductions through improved efficiency of vehicle fleets.
- **IPCC AR6 GWP-100** — CH₄ = 27.9, N₂O = 273 (Table 7.SM.7).

---

## Fleet Categories

All categories are fully parameterised with AFEC, EV consumption, occupancy, and charger type:

### Transport Fleet

| Category | AFEC (L/km) | EV (kWh/km) | Annual km | CO₂ saved/km |
|----------|-------------|-------------|-----------|--------------|
| 🚲 E-Bike | 0.035 (petrol) | 0.010 | 8,000 | ~53g |
| 🚕 PSV Car / Taxi | 0.090 (petrol) | 0.180 | 50,000 | ~230g |
| 🚐 Minibus / Matatu | 0.130 (diesel) | 0.350 | 60,000 | ~350g |
| 🚌 Transit Bus / BRT | 0.350 (diesel) | 0.950 | 70,000 | ~1,009g |
| 🚚 Light Truck / Van | 0.120 (diesel) | 0.300 | 40,000 | ~320g |
| 🚛 Heavy Goods Truck | 0.400 (diesel) | 1.500 | 80,000 | ~1,065g |

### Construction Machinery (VMR0004 v2.0)

| Machine | Diesel (L/hr) | EV (kWh/hr) | CO₂ saved/hr |
|---------|---------------|-------------|--------------|
| ⛏️ Excavator (18–25 t) | 12.0 | 45.0 | ~31.7 kg |
| 🏗️ Wheel Loader (2–5 t) | 9.0 | 32.0 | ~23.8 kg |
| 🏗️ Mobile Crane (50–100 t) | 18.0 | 65.0 | ~47.5 kg |
| 🏗️ Forklift (2–5 t) | 3.5 | 8.5 | ~9.2 kg |

---

## Charging Hardware Network

Charger tiers registered in the system (VM0038 §7 monitoring plan):

| Level | Power | Efficiency | Max Sessions/Day | Est. Install Cost |
|-------|-------|------------|------------------|-------------------|
| L1 AC | 1.4 kW | 85.5% | 4 | $800 |
| L2 AC | 7.4 kW | 90.0% | 12 | $2,500 |
| L2 AC (fast) | 22 kW | 90.0% | 20 | $5,000 |
| DCFC 50 kW | 50 kW | 92.3% | 30 | $25,000 |
| DCFC 150 kW | 150 kW | 92.3% | 40 | $60,000 |

---

## WhatsApp Conversation Flow

```
Rider: "Hi"
Bot:   🌿 Welcome to Go Green! Tell me where you're going…

Rider: "Westlands to Karen"
Bot:   ✅ Geocoded both locations
       🔄 Querying 7 EV providers…
       🌿 Go Green EV Rides
       📍 From: Westlands  🏁 To: Karen  🛣️ ~9.4 km

       1. Wasili — Wasili EV
          💰 KSh 510  ⏱ 4m ETA  🚗 BYD Atto 3  ⭐ 4.7  🌱 2,209g CO₂
       2. Faras — Faras Green
          💰 KSh 580  ⏱ 6m ETA  🚗 MG4 EV  ⭐ 4.5  🌱 2,209g CO₂
       … (7 providers shown)

Rider: "1"
Bot:   ✅ Wasili — Wasili EV
       🚗 BYD Atto 3  👤 James K. ⭐ 4.7  🚘 KCA 342 B
       📍 ETA: 4 min  🛣️ 9.4 km  💰 KSh 510
       🌱 You'll save ~2,209g CO₂ vs a petrol cab
       Reply YES to confirm & pay, or NO to go back.

Rider: "YES"
Bot:   💳 M-Pesa payment request sent!
       📱 Check your phone +254712345678
       Enter your M-Pesa PIN to pay KSh 510
       Trip ID: GG-1748700123

       🌿 Carbon Credits Earned
       CO₂ saved: 2,209g (0.00221 tCO₂e)
       💎 VCUs: 0.0019289 (Verra VM0038)
       💰 Value: KSh 3.1344
       🌳 ≈ 0.087 trees/yr

[Rider enters PIN on phone]

Bot:   ✅ Payment confirmed! BYD Atto 3 is on the way…
```

---

## Installation

### Prerequisites

- Python 3.11+
- Anthropic API key (`claude-sonnet-4-20250514` or later)
- Safaricom Daraja API credentials (sandbox or production)
- Twilio or Meta WhatsApp Business account

### Quick Start

```bash
# 1. Clone / place all files in a directory
mkdir gogreen && cd gogreen
# (copy all files here)

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set required environment variables (see section below)
cp .env.example .env
nano .env

# 5. Run
python app.py
```

Open **http://localhost:7860** for the WhatsApp simulator UI.
Open **http://localhost:7861** for the Carbon Credit Dashboard (separate process).

---

## Environment Variables

Create a `.env` file (or export in your shell):

```env
# ── Anthropic (required) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── M-Pesa Daraja API ─────────────────────────────────────────────────────
MPESA_SANDBOX=true                          # set false for production
MPESA_CONSUMER_KEY=your_consumer_key
MPESA_CONSUMER_SECRET=your_consumer_secret
MPESA_SHORTCODE=174379                      # your paybill / till number
MPESA_PASSKEY=your_lipa_na_mpesa_passkey
MPESA_CALLBACK_URL=https://yourdomain.com/api/mpesa/callback

# ── WhatsApp provider (twilio or meta) ────────────────────────────────────
WA_PROVIDER=twilio

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886  # Twilio sandbox number

# Meta Cloud API (alternative to Twilio)
META_ACCESS_TOKEN=your_meta_access_token
META_PHONE_NUMBER_ID=your_phone_number_id
META_VERIFY_TOKEN=gogreen_verify_2025       # any string you choose

# ── Server ports ──────────────────────────────────────────────────────────
PORT=7860                                   # Gradio UI
CARBON_PORT=7861                            # Carbon dashboard

# ── Optional ─────────────────────────────────────────────────────────────
GOGREEN_BASE_URL=https://yourdomain.com     # for webhook registration
```

### Getting API Credentials

**Anthropic:** [console.anthropic.com](https://console.anthropic.com)

**Safaricom Daraja:**
1. Register at [developer.safaricom.co.ke](https://developer.safaricom.co.ke)
2. Create an app → copy Consumer Key + Consumer Secret
3. Go to *Lipa Na M-Pesa Online* → copy the Passkey
4. Use shortcode `174379` for sandbox

**Twilio WhatsApp Sandbox:**
1. [console.twilio.com](https://console.twilio.com) → Messaging → Try WhatsApp
2. Follow sandbox join instructions
3. Copy Account SID and Auth Token

**Meta Cloud API:**
1. [developers.facebook.com](https://developers.facebook.com) → Create App → WhatsApp
2. Add phone number → copy Phone Number ID and access token

---

## Running the Application

### Development (all-in-one)

```bash
python app.py
# Gradio UI  → http://localhost:7860
# Flask      → http://localhost:5000
```

### Carbon Dashboard (separate)

```bash
python carbon_dashboard.py
# Dashboard  → http://localhost:7861
```

### Production (recommended)

```bash
# Gradio UI via Gunicorn
gunicorn --bind 0.0.0.0:7860 --workers 2 "app:demo"

# Flask webhook via Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 "whatsapp_agent:flask_app"
```

Use **ngrok** for local webhook testing:

```bash
ngrok http 5000
# Copy the HTTPS URL → set as MPESA_CALLBACK_URL and Twilio/Meta webhook URL
```

---

## API Endpoints

All endpoints are served by the Flask server on port 5000.

### WhatsApp Webhook

```
GET  /api/whatsapp/webhook
     ?hub.mode=subscribe
     &hub.verify_token=<META_VERIFY_TOKEN>
     &hub.challenge=<challenge>
     → Returns challenge (Meta verification handshake)

POST /api/whatsapp/webhook
     Body: Twilio form-data OR Meta JSON payload
     → Processes inbound message, sends WhatsApp reply
     → Returns {"status": "ok"}
```

### Health Check

```
GET  /health
     → {"status": "ok", "service": "Go Green"}
```

### M-Pesa Callback (configure in Daraja)

```
POST /api/mpesa/callback
     Body: Daraja STK Push result JSON
     → Updates payment status, triggers booking confirmation
```

---

## Carbon Credit Methodology

### Verra VM0038 v1.0 — Step by Step

**Step 1 — Baseline Emissions (BE)**

The ICE equivalent trip emission using the fleet's Adjusted Fuel Economy Coefficient:

```
BE = VKT × AFEC × EF_fuel × WTT_factor   [kgCO₂e]

Example (PSV Car, 12.5 km):
BE = 12.5 × 0.090 L/km × 2.296 kgCO₂e/L × 1.19 = 3.066 kgCO₂e
```

**Step 2 — Project Emissions (PE)**

Grid electricity footprint, accounting for charger efficiency:

```
PE = (VKT × ev_kWh_per_km ÷ η_charger) × EF_grid   [kgCO₂e]

Example (PSV Car, L2 charger):
PE = (12.5 × 0.180 ÷ 0.900) × 0.061 = 0.153 kgCO₂e
```

**Step 3 — Gross Emission Reduction**

```
Gross ER = BE − PE = 3.066 − 0.153 = 2.913 kgCO₂e
```

**Step 4 — Leakage (3%)**

```
LE = 2.913 × 0.03 = 0.087 kgCO₂e
Net ER = 2.913 − 0.087 = 2.826 kgCO₂e
```

**Step 5 — VCS Buffer (10%) → Tradeable VCUs**

```
VCU = Net ER × (1 − 0.10) ÷ 1000 t
VCU = 2.826 × 0.90 ÷ 1000 = 0.002543 tCO₂e
Value = 0.002543 × $12.50 = $0.032 ≈ KSh 4.13
```

### Double-Counting Prevention

Per VM0038 §4.4, closed/private fleet networks cannot claim credits from both fleet adoption and charging station projects simultaneously. Go Green tracks VCU issuance per vehicle ID to prevent overlapping claims.

### Monitoring Plan

M-Pesa transaction records serve as **immutable proof of VKT** — every STK Push receipt is timestamped, geo-tagged (pickup/drop coordinates), and persisted to the rider's carbon ledger. This satisfies VM0038 §7 continuous monitoring requirements without additional telemetry hardware for ride-hail PSVs.

For construction machinery (VMR0004 v2.0), IoT operating-hour sensors feed into the same ledger.

---

## Development Guide

### Adding a New EV Provider

Create a new adapter in `providers.py` by subclassing `_Base`:

```python
class MyProviderAdapter(_Base):
    provider      = "MyProvider"
    provider_slug = "myprovider"
    color         = "#FF0000"
    ride_type     = "MyProvider EV"
    base_rate     = 45.0
    base_fare     = 95.0
    ev_models     = ["BYD Seal", "Tesla Model Y"]
    logo_url      = "https://..."

    # Override to make real API call instead of simulation:
    def search(self, query: str, max_results: int = 5) -> list[RideOffer]:
        response = requests.get(
            "https://api.myprovider.com/rides",
            params={"origin": ..., "destination": ...}
        )
        return [self._parse(r) for r in response.json()["rides"]]
```

Then add to `ALL_PROVIDERS` list at the bottom of `providers.py`.

### Adding a New Fleet Category

Add a `VehicleCategory` enum value and a `VehicleParams` entry in `carbon/verra_constants.py`:

```python
class VehicleCategory(str, Enum):
    ...
    MY_NEW_VEHICLE = "my_new_vehicle"

VEHICLE_PARAMS[VehicleCategory.MY_NEW_VEHICLE] = VehicleParams(
    afec_l_per_km       = 0.150,
    fuel_type           = "diesel",
    ev_kwh_per_km       = 0.400,
    co2_per_km_baseline = _baseline_co2(0.150, "diesel"),
    occupancy_factor    = 8.0,
    annual_km_default   = 45_000,
    charger_type        = "L2",
    vcu_per_km          = _vcu_per_km(_baseline_co2(0.150,"diesel"), 0.400, "L2"),
    category_label      = "My New Vehicle Type",
    sector              = "transport",
    icon                = "🚐",
)
```

### Replacing Simulated Geocoding

In `orchestrator_agent.py`, replace `LocationAgent._geocode()`:

```python
@staticmethod
def _geocode(address: str) -> dict:
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address + ", Nairobi, Kenya", "key": os.environ["GOOGLE_MAPS_KEY"]}
    )
    result = resp.json()["results"][0]["geometry"]["location"]
    return {"lat": result["lat"], "lon": result["lng"], "found": True}
```

### Replacing Simulated Ride Providers

Each adapter's `search()` method calls a simulated price model. Replace with the provider's real API:

- **Uber:** [Uber Rides API](https://developer.uber.com/docs/riders/ride-requests)
- **Bolt:** [Bolt Partner API](https://partners.bolt.eu)
- **Little Cabs / Faras / Wasili / Weego:** Contact providers for API access

---

## Production Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7860 5000
CMD ["python", "app.py"]
```

```bash
docker build -t gogreen .
docker run -p 7860:7860 -p 5000:5000 \
  -e ANTHROPIC_API_KEY=sk-... \
  -e MPESA_CONSUMER_KEY=... \
  gogreen
```

### Session Persistence

The current implementation uses in-process `LongTermMemory` (Python dict). For multi-worker production:

1. Replace `LongTermMemory.store` with Redis:
   ```python
   import redis
   r = redis.Redis(host=os.environ["REDIS_URL"])
   ```
2. Serialise `TripSession` to JSON and store by phone key
3. Set `SESSION_TTL=3600` for automatic expiry

### Scaling the Carbon Ledger

For high-volume fleets (>1,000 vehicles), persist VCU records to PostgreSQL:

```sql
CREATE TABLE carbon_ledger (
    entry_id      VARCHAR(8) PRIMARY KEY,
    phone         VARCHAR(20) NOT NULL,
    trip_id       VARCHAR(30),
    timestamp     BIGINT,
    vehicle_cat   VARCHAR(40),
    distance_km   FLOAT,
    net_vcu       FLOAT,
    vcu_value_kes FLOAT,
    baseline_kg   FLOAT,
    net_kg        FLOAT,
    charger_type  VARCHAR(10),
    methodology   VARCHAR(30) DEFAULT 'Verra VM0038 v1.0'
);
CREATE INDEX idx_carbon_phone ON carbon_ledger(phone);
```

---

## Roadmap

### Near Term
- [ ] Google Maps Geocoding API integration (replace landmark dict)
- [ ] Real provider API adapters (Bolt, Uber, Faras partners)
- [ ] Redis session persistence
- [ ] Push notification when driver arrives

### Medium Term
- [ ] Rider app (React Native) — WhatsApp remains primary, app as companion
- [ ] Fleet operator dashboard — real-time VCU accrual per vehicle
- [ ] Verra registry API integration — automatic VCU issuance
- [ ] Carbon credit marketplace — rider-to-rider VCU trading

### Long Term
- [ ] Full VMR0004 v2.0 IoT integration for construction machinery
- [ ] Expand to Uganda, Tanzania, Rwanda (KEDC / TANESCO grid EFs)
- [ ] Green bond issuance backed by accrued VCU portfolio
- [ ] ISO 14064-2 third-party verification pipeline

---

## Methodology References

| Document | Version | Description |
|----------|---------|-------------|
| [Verra VM0038](https://verra.org/methodologies/vm0038-methodology-for-electric-vehicle-charging-systems-v1-0/) | v1.0 | EV Charging Systems GHG methodology |
| [VMD0049](https://verra.org/wp-content/uploads/2022/06/VMD0049-v1.0.pdf) | v1.0 | Additionality for EV Charging Systems |
| [VMR0004](https://verra.org/wp-content/uploads/2024/10/VMR0004-v2.0.pdf) | v2.0 | Improved Efficiency of Fleet Vehicles |
| [AMS-III.BC](https://cdm.unfccc.int/methodologies/DB/R0CI5GIGKXHWQOCSTJB6AFQBGDQ2HT) | — | CDM Fleet Vehicle Efficiency |
| [IEA EF 2024](https://www.iea.org/data-and-statistics/data-product/emissions-factors-2024) | 2024 | Kenya Grid Emission Factor |
| [IPCC AR6](https://www.ipcc.ch/report/ar6/wg1/) | AR6 | GWP-100 values (CH₄=27.9, N₂O=273) |
| [UNFCCC Tool 03](https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-03-v3.pdf) | v3 | CO₂ emissions from fossil fuel combustion |

---

## License

MIT License — see `LICENSE` file.

---

## Contributing

Pull requests are welcome. For major changes please open an issue first to discuss what you'd like to change. All carbon credit calculation changes must include citation of the specific VM0038 clause being implemented or modified.

---

*Built with ❤️ for Kenya's green mobility transition.*
*Every ride. Every credit. Every tree.*  🌿
