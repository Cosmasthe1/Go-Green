"""
orchestrator_agent.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
Multi-agent orchestrator for the Go Green EV ride ordering system.

Agent roster
  ┌──────────────────────────────────────────────────────────────────────┐
  │                       GoGreenOrchestrator                            │
  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
  │  │ LocationAgent│  │  RideAgent   │  │  Payment   │  │  Carbon  │  │
  │  │ geocode,maps │  │ fetch,rank   │  │   Agent    │  │  Agent   │  │
  │  └──────────────┘  └──────────────┘  └────────────┘  └──────────┘  │
  │           Memory  ·  MCP layer  ·  HITL gate  ·  Verra VM0038      │
  └──────────────────────────────────────────────────────────────────────┘

WhatsApp conversation flow:
  1. Rider sends pickup + destination (free text or "pin")
  2. LocationAgent  → geocode both addresses → lat/lon pairs
  3. RideAgent      → query all 7 EV providers in parallel → ranked offers
  4. WhatsApp bot   → display ride cards with logo, distance, price
  5. Rider picks a provider (replies "1" / "Bolt" / etc.)
  6. HITL gate      → confirm booking details with rider
  7. PaymentAgent   → M-Pesa STK push to WhatsApp-registered number
  8. CarbonAgent    → calculate Verra VM0038 GHG reductions → accrue VCUs
  9. Orchestrator   → confirm booking + send carbon credit summary
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from base_agent import BaseAgent, LongTermMemory
from mpesa import STKPushRequest, mpesa
from providers import RideOffer, get_all_offers
from carbon import CarbonAgent, CarbonLedger, VehicleCategory

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Execution log
# ─────────────────────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    AWAITING = "awaiting_human"
    DONE     = "done"
    ERROR    = "error"


@dataclass
class ExecutionStep:
    agent_name: str
    task:       str
    status:     StepStatus = StepStatus.PENDING
    result:     str        = ""
    timestamp:  float      = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "agent":     self.agent_name,
            "task":      self.task,
            "status":    self.status.value,
            "result":    self.result[:200] + ("…" if len(self.result) > 200 else ""),
            "ts":        self.timestamp,
        }


class ExecutionLog:
    def __init__(self) -> None:
        self._steps: list[ExecutionStep] = []

    def add(self, step: ExecutionStep) -> ExecutionStep:
        self._steps.append(step)
        return step

    def as_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self._steps]

    def clear(self) -> None:
        self._steps.clear()


# ─────────────────────────────────────────────────────────────────────────────
# HITL gate
# ─────────────────────────────────────────────────────────────────────────────

class HITLGate:
    """
    Synchronous human-approval gate.
    For Go Green the "human" is the rider confirming their booking via WhatsApp.
    The UI / WhatsApp agent registers an approve_fn that blocks until the
    rider responds.
    """

    def __init__(self) -> None:
        self._fn: Callable[[str], tuple[bool, str]] | None = None

    def register(self, fn: Callable[[str], tuple[bool, str]]) -> None:
        self._fn = fn

    def checkpoint(self, prompt: str) -> tuple[bool, str]:
        if self._fn is None:
            logger.warning("HITL: no handler → auto-approving")
            return True, ""
        return self._fn(prompt)


# ─────────────────────────────────────────────────────────────────────────────
# MCP client
# ─────────────────────────────────────────────────────────────────────────────

class MCPClient:
    def __init__(self) -> None:
        self._servers: dict[str, dict] = {}

    def connect_server(self, name: str, desc: str, tools: dict) -> None:
        self._servers[name] = {"desc": desc, "tools": tools}
        logger.info("MCP server: %s", name)

    def call(self, server: str, tool: str, **kwargs) -> Any:
        return self._servers[server]["tools"][tool](**kwargs)

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Specialised agents
# ─────────────────────────────────────────────────────────────────────────────

# ── Nairobi landmark coordinates for demo geocoding ──────────────────────────
NAIROBI_LANDMARKS: dict[str, tuple[float, float]] = {
    "cbd":                  (-1.2833, 36.8172),
    "nairobi cbd":          (-1.2833, 36.8172),
    "westlands":            (-1.2636, 36.8030),
    "karen":                (-1.3180, 36.7070),
    "kileleshwa":           (-1.2833, 36.7747),
    "kilimani":             (-1.2897, 36.7836),
    "lavington":            (-1.2789, 36.7730),
    "parklands":            (-1.2600, 36.8140),
    "upperhill":            (-1.2998, 36.8197),
    "gigiri":               (-1.2300, 36.8100),
    "runda":                (-1.2050, 36.8300),
    "muthaiga":             (-1.2480, 36.8380),
    "langata":              (-1.3600, 36.7340),
    "south b":              (-1.3200, 36.8340),
    "south c":              (-1.3080, 36.8360),
    "embakasi":             (-1.3260, 36.8960),
    "kasarani":             (-1.2180, 36.8970),
    "ruaka":                (-1.2030, 36.7680),
    "thika road":           (-1.2200, 36.8600),
    "jkia":                 (-1.3192, 36.9275),
    "jomo kenyatta":        (-1.3192, 36.9275),
    "airport":              (-1.3192, 36.9275),
    "uchumi":               (-1.2833, 36.8172),
    "galleria":             (-1.3400, 36.7600),
    "junction":             (-1.3050, 36.7820),
    "village market":       (-1.2280, 36.8030),
    "two rivers":           (-1.1940, 36.7970),
    "garden city":          (-1.2180, 36.8850),
    "sarit":                (-1.2620, 36.8060),
    "yaya":                 (-1.2950, 36.7880),
    "prestige":             (-1.3020, 36.7720),
    "university of nairobi":(-1.2792, 36.8165),
    "strathmore":           (-1.3094, 36.8120),
    "kenyatta hospital":    (-1.3010, 36.8070),
    "aga khan":             (-1.2640, 36.8200),
    "nairobi hospital":     (-1.2946, 36.8177),
}


class LocationAgent(BaseAgent):
    """
    Geocodes pickup and destination addresses to lat/lon pairs.
    Falls back to Nairobi CBD if the address is unrecognised.
    In production wire to Google Maps Geocoding API or OpenStreetMap Nominatim.
    """

    name   = "LocationAgent"
    system = textwrap.dedent("""\
        You are a location parsing specialist for Nairobi, Kenya.
        Extract structured pickup and destination from the rider's message.
        Respond ONLY with JSON:
        {
          "pickup":      "<cleaned address string>",
          "destination": "<cleaned address string>"
        }
        If only one location is mentioned, put it in "destination" and set
        "pickup" to "current location".
    """)

    def _register_tools(self) -> None:
        self._tool_registry.register(
            {
                "name": "geocode",
                "description": "Convert a Nairobi address string to lat/lon coordinates.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "address": {"type": "string", "description": "Address to geocode"},
                    },
                    "required": ["address"],
                },
            },
            self._geocode,
        )

    @staticmethod
    def _geocode(address: str) -> dict:
        """
        Lookup against known landmarks; fall back to Nairobi CBD with slight
        random jitter so distances vary realistically in the demo.
        In production call Google Maps Geocoding API here.
        """
        import random, math
        key = address.lower().strip()
        for landmark, coords in NAIROBI_LANDMARKS.items():
            if landmark in key or key in landmark:
                jitter = lambda: (random.random() - 0.5) * 0.005
                return {
                    "address": address,
                    "lat":     round(coords[0] + jitter(), 6),
                    "lon":     round(coords[1] + jitter(), 6),
                    "found":   True,
                }
        # Unknown address — place near CBD with wider jitter
        import random
        return {
            "address": address,
            "lat":     round(-1.2833 + (random.random() - 0.5) * 0.06, 6),
            "lon":     round(36.8172 + (random.random() - 0.5) * 0.06, 6),
            "found":   False,
        }

    def parse_and_geocode(self, message: str) -> dict:
        """
        Parse rider message → extract addresses → geocode both.
        Returns: {pickup, destination, pickup_coords, drop_coords}
        """
        try:
            raw   = self.run(message, inject_history=False)
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
        except Exception:
            parsed = {"pickup": "current location", "destination": message}

        pickup_text = parsed.get("pickup", "current location")
        dest_text   = parsed.get("destination", "Nairobi CBD")

        # Use CBD as default for "current location"
        pickup_geo = (
            {"lat": -1.2833, "lon": 36.8172, "found": True}
            if "current" in pickup_text.lower()
            else self._geocode(pickup_text)
        )
        drop_geo = self._geocode(dest_text)

        return {
            "pickup":       pickup_text,
            "destination":  dest_text,
            "pickup_lat":   pickup_geo["lat"],
            "pickup_lon":   pickup_geo["lon"],
            "drop_lat":     drop_geo["lat"],
            "drop_lon":     drop_geo["lon"],
        }


class RideAgent(BaseAgent):
    """
    Queries all 7 EV providers in parallel, scores offers, and returns a
    ranked list with contextual analysis.
    """

    name   = "RideAgent"
    system = textwrap.dedent("""\
        You are the Go Green ride selection expert.
        You have access to EV ride offers from 7 providers.
        Use the fetch_rides tool to get live offers, then analyse them.
        Rank by: value (price + quality), ETA, driver rating, and eco impact.
        Respond ONLY with the JSON output from the tool.
    """)

    def _register_tools(self) -> None:
        self._tool_registry.register(
            {
                "name": "fetch_rides",
                "description": "Fetch EV ride offers from all providers for given coordinates.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pickup_lat":  {"type": "number"},
                        "pickup_lon":  {"type": "number"},
                        "drop_lat":    {"type": "number"},
                        "drop_lon":    {"type": "number"},
                    },
                    "required": ["pickup_lat", "pickup_lon", "drop_lat", "drop_lon"],
                },
            },
            self._fetch_rides,
        )

    @staticmethod
    def _fetch_rides(
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> dict:
        offers = get_all_offers(pickup_lat, pickup_lon, drop_lat, drop_lon)
        return {"offers": [o.to_dict() for o in offers]}

    def get_offers(
        self,
        pickup_lat: float, pickup_lon: float,
        drop_lat:   float, drop_lon:   float,
    ) -> list[dict]:
        """Direct (non-LLM) ride fetch for speed."""
        offers = get_all_offers(pickup_lat, pickup_lon, drop_lat, drop_lon)
        return [o.to_dict() for o in offers]


class PaymentAgent(BaseAgent):
    """
    Handles M-Pesa STK push payments.
    Validates phone numbers, initiates push, tracks status.
    """

    name   = "PaymentAgent"
    system = textwrap.dedent("""\
        You are the Go Green payment specialist.
        You initiate M-Pesa STK push payments for EV rides.
        Use the mpesa_push tool to send payment requests.
        Always confirm the amount and phone number before proceeding.
    """)

    def _register_tools(self) -> None:
        self._tool_registry.register(
            {
                "name": "mpesa_push",
                "description": "Send M-Pesa STK push to rider's phone number.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phone":       {"type": "string", "description": "Rider phone: 2547XXXXXXXX"},
                        "amount_kes":  {"type": "number", "description": "Amount in KES"},
                        "trip_id":     {"type": "string", "description": "Trip reference ID"},
                        "description": {"type": "string", "description": "Payment description"},
                    },
                    "required": ["phone", "amount_kes", "trip_id"],
                },
            },
            self._mpesa_push,
        )

    @staticmethod
    def _mpesa_push(
        phone:       str,
        amount_kes:  float,
        trip_id:     str,
        description: str = "Go Green EV Ride",
    ) -> dict:
        req = STKPushRequest(
            phone_number = mpesa.normalise_phone(phone),
            amount       = int(round(amount_kes)),
            account_ref  = trip_id[:12],
            description  = description[:13],
        )
        resp = mpesa.stk_push(req)
        return resp.to_dict()

    def initiate_payment(self, phone: str, amount_kes: float, trip_id: str) -> dict:
        """Direct payment initiation (no LLM loop needed)."""
        return self._mpesa_push(phone, amount_kes, trip_id)


# ─────────────────────────────────────────────────────────────────────────────
# Trip state machine
# ─────────────────────────────────────────────────────────────────────────────

class TripState(str, Enum):
    IDLE            = "idle"
    LOCATING        = "locating"
    SHOWING_RIDES   = "showing_rides"
    AWAITING_CHOICE = "awaiting_choice"
    CONFIRMING      = "confirming"
    PAYING          = "paying"
    BOOKED          = "booked"
    CANCELLED       = "cancelled"


@dataclass
class TripSession:
    session_id:    str              = field(default_factory=lambda: str(uuid.uuid4())[:8])
    phone:         str              = ""
    state:         TripState        = TripState.IDLE
    pickup:        str              = ""
    destination:   str              = ""
    pickup_lat:    float            = 0.0
    pickup_lon:    float            = 0.0
    drop_lat:      float            = 0.0
    drop_lon:      float            = 0.0
    offers:        list[dict]       = field(default_factory=list)
    chosen_offer:  dict | None      = None
    trip_id:       str              = ""
    checkout_id:   str              = ""
    paid:          bool             = False
    carbon_result: dict | None      = None   # Verra VM0038 result for this trip

    def to_dict(self) -> dict:
        return {
            "session_id":   self.session_id,
            "phone":        self.phone,
            "state":        self.state.value,
            "pickup":       self.pickup,
            "destination":  self.destination,
            "offers_count": len(self.offers),
            "chosen":       self.chosen_offer.get("provider") if self.chosen_offer else None,
            "trip_id":      self.trip_id,
            "paid":         self.paid,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class GoGreenOrchestrator:
    """
    Stateful orchestrator for a single rider's trip booking flow.

    One instance per active session (keyed by phone number).
    """

    def __init__(self, model: str | None = None) -> None:
        self.location  = LocationAgent(model=model)
        self.ride      = RideAgent(model=model)
        self.payment   = PaymentAgent(model=model)
        self.log       = ExecutionLog()
        self.hitl      = HITLGate()
        self.mcp       = MCPClient()
        self.memory    = LongTermMemory()
        self.session   = TripSession()
        self._on_step: Callable[[dict], None] | None = None

        # ── Carbon credit engine (Verra VM0038) ───────────────────────────────
        self._carbon_ledger = CarbonLedger(self.memory)
        self.carbon         = CarbonAgent(model=model)
        self.carbon.set_ledger(self._carbon_ledger)

        self._wire_mcp()

    # ── public API ────────────────────────────────────────────────────────────

    def on_step_update(self, fn: Callable[[dict], None]) -> None:
        self._on_step = fn

    def handle_message(self, phone: str, text: str) -> "OrchestratorResponse":
        """
        Main entry point. Called for every inbound WhatsApp message.
        Returns a structured response for the WhatsApp agent to render.
        """
        self.session.phone = phone
        self.log.clear()
        text = text.strip()

        state = self.session.state

        # ── Greet / reset ─────────────────────────────────────────────────────
        if state == TripState.IDLE or text.lower() in ("hi", "hello", "hey", "start", "reset", "menu"):
            return self._greet(phone)

        # ── Location input → show rides ───────────────────────────────────────
        if state in (TripState.IDLE, TripState.SHOWING_RIDES) or (
            state == TripState.AWAITING_CHOICE and not self._is_ride_choice(text)
        ):
            return self._locate_and_fetch(phone, text)

        # ── Ride choice ───────────────────────────────────────────────────────
        if state == TripState.AWAITING_CHOICE:
            return self._handle_choice(phone, text)

        # ── Booking confirmation ──────────────────────────────────────────────
        if state == TripState.CONFIRMING:
            return self._handle_confirmation(phone, text)

        # ── Payment pending ───────────────────────────────────────────────────
        if state == TripState.PAYING:
            return self._check_payment(phone, text)

        return self._greet(phone)

    # ── Step handlers ─────────────────────────────────────────────────────────

    def _greet(self, phone: str) -> "OrchestratorResponse":
        self.session = TripSession(phone=phone, state=TripState.IDLE)
        name = self.memory.recall(f"rider:{phone}:name", "")
        greeting = f"Hi {name}! 👋" if name else "Hi there! 👋"
        return OrchestratorResponse(
            message=(
                f"🌿 *Welcome to Go Green!*\n\n"
                f"{greeting} I'll book you a clean ⚡ EV ride.\n\n"
                f"Just tell me where you're going:\n"
                f"_e.g. 'Westlands to Karen' or 'Take me to JKIA'_"
            ),
            state=TripState.IDLE.value,
            log=self.log.as_dicts(),
        )

    def _locate_and_fetch(self, phone: str, text: str) -> "OrchestratorResponse":
        # ── Step 1: Geocode ───────────────────────────────────────────────────
        s1 = self._step("LocationAgent", f"Geocode: {text[:60]}")
        geo = self.location.parse_and_geocode(text)
        self._done(s1, f"{geo['pickup']} → {geo['destination']}")

        self.session.pickup      = geo["pickup"]
        self.session.destination = geo["destination"]
        self.session.pickup_lat  = geo["pickup_lat"]
        self.session.pickup_lon  = geo["pickup_lon"]
        self.session.drop_lat    = geo["drop_lat"]
        self.session.drop_lon    = geo["drop_lon"]
        self.session.state       = TripState.SHOWING_RIDES

        # ── Step 2: Fetch rides ───────────────────────────────────────────────
        s2 = self._step("RideAgent", "Fetch EV rides from all providers")
        offers = self.ride.get_offers(
            geo["pickup_lat"], geo["pickup_lon"],
            geo["drop_lat"],   geo["drop_lon"],
        )
        self._done(s2, f"{len(offers)} offers fetched")
        self.session.offers = offers
        self.session.state  = TripState.AWAITING_CHOICE

        # Persist search to memory
        self.memory.remember(f"rider:{phone}:last_search", {
            "pickup": geo["pickup"], "destination": geo["destination"],
            "ts": int(time.time()),
        })

        return OrchestratorResponse(
            message    = self._format_ride_list(geo, offers),
            offers     = offers,
            pickup     = geo["pickup"],
            destination= geo["destination"],
            pickup_lat = geo["pickup_lat"],
            pickup_lon = geo["pickup_lon"],
            drop_lat   = geo["drop_lat"],
            drop_lon   = geo["drop_lon"],
            state      = TripState.AWAITING_CHOICE.value,
            log        = self.log.as_dicts(),
        )

    def _handle_choice(self, phone: str, text: str) -> "OrchestratorResponse":
        offers  = self.session.offers
        chosen  = self._resolve_choice(text, offers)

        if not chosen:
            return OrchestratorResponse(
                message="Please reply with the number (1-7) or provider name, e.g. *Bolt* or *3*.",
                state=TripState.AWAITING_CHOICE.value,
                log=self.log.as_dicts(),
            )

        self.session.chosen_offer = chosen
        self.session.state        = TripState.CONFIRMING
        self.session.trip_id      = f"GG-{int(time.time())}"

        msg = (
            f"✅ *{chosen['provider']} — {chosen['ride_type']}*\n\n"
            f"🚗 {chosen['ev_model']}\n"
            f"👤 {chosen['driver_name']}  ⭐ {chosen['driver_rating']}\n"
            f"🚘 {chosen['plate']}\n"
            f"📍 ETA: *{chosen['eta_min']} min*\n"
            f"🛣️ {chosen['distance_km']:.1f} km  •  ~{chosen['duration_min']} min ride\n"
            f"💰 *{chosen['fare_display'] if callable(chosen.get('fare_display')) else 'KSh {:,.0f}'.format(chosen['price_kes'])}*\n"
            f"🌱 You'll save ~{chosen['co2_saved_g']:.0f}g CO₂ vs a petrol cab\n\n"
            f"{'🏷️ Promo *' + chosen['promo_code'] + '* applied!  ' if chosen.get('promo_code') else ''}"
            f"Reply *YES* to confirm & pay, or *NO* to go back."
        )

        return OrchestratorResponse(
            message      = msg,
            chosen_offer = chosen,
            state        = TripState.CONFIRMING.value,
            log          = self.log.as_dicts(),
        )

    def _handle_confirmation(self, phone: str, text: str) -> "OrchestratorResponse":
        if text.lower() not in ("yes", "y", "confirm", "ok", "sure", "yeah", "yep"):
            if text.lower() in ("no", "n", "cancel", "back"):
                self.session.state = TripState.AWAITING_CHOICE
                return OrchestratorResponse(
                    message="No problem! Reply with your choice again (1-7) or send a new destination.",
                    state=TripState.AWAITING_CHOICE.value,
                    log=self.log.as_dicts(),
                )
            return OrchestratorResponse(
                message="Reply *YES* to confirm your booking or *NO* to go back.",
                state=TripState.CONFIRMING.value,
                log=self.log.as_dicts(),
            )

        # ── Step 3: Initiate M-Pesa STK push ─────────────────────────────────
        offer  = self.session.chosen_offer
        amount = int(round(offer["price_kes"]))
        s3 = self._step("PaymentAgent", f"M-Pesa STK push → {phone} KSh {amount}")

        result = self.payment.initiate_payment(phone, amount, self.session.trip_id)
        self._done(s3, result.get("customer_msg", "")[:100])

        self.session.state       = TripState.PAYING
        self.session.checkout_id = result.get("checkout_request_id", "")

        if result.get("success"):
            msg = (
                f"💳 *M-Pesa payment request sent!*\n\n"
                f"📱 Check your phone *{mpesa.normalise_phone(phone)}*\n"
                f"Enter your M-Pesa PIN to pay *KSh {amount:,}*\n\n"
                f"Trip ID: `{self.session.trip_id}`\n\n"
                f"_Once payment is confirmed, your driver will be on the way! 🚗⚡_"
            )
            self.session.paid  = True
            self.session.state = TripState.BOOKED

            # ── Step 4: Carbon credits (Verra VM0038) ─────────────────────────
            s4 = self._step("CarbonAgent", f"Calculate VM0038 GHG reductions — {self.session.trip_id}")
            try:
                carbon_result = self.carbon.process_trip(
                    phone            = phone,
                    trip_id          = self.session.trip_id,
                    vehicle_category = VehicleCategory.PSV_PASSENGER_CAR,
                    distance_km      = offer.get("distance_km", 10.0),
                    charger_type     = "L2",
                )
                self.session.carbon_result = carbon_result
                vcu_earned = carbon_result.get("net_vcu", 0)
                co2_saved  = carbon_result.get("net_reduction_kg", 0)
                self._done(s4, f"{co2_saved*1000:.0f}g CO₂ saved → {vcu_earned:.8f} VCU")

                # Append carbon summary to the WhatsApp confirmation message
                msg += (
                    f"\n\n🌿 *Carbon Credits Earned*\n"
                    f"CO₂ saved: *{co2_saved*1000:.0f}g* ({co2_saved/1000:.5f} tCO₂e)\n"
                    f"💎 VCUs: *{vcu_earned:.7f}* (Verra VM0038)\n"
                    f"💰 Value: *KSh {carbon_result.get('vcu_value_kes',0):.4f}*\n"
                    f"🌳 ≈ {carbon_result.get('trees_equivalent',0):.3f} trees/yr"
                )
            except Exception as exc:
                logger.warning("Carbon calculation failed: %s", exc)
                self._done(s4, f"Error: {exc}")

            # Persist trip with carbon data
            self.memory.remember(f"trip:{self.session.trip_id}", {
                "phone":        phone,
                "provider":     offer["provider"],
                "pickup":       self.session.pickup,
                "destination":  self.session.destination,
                "amount":       amount,
                "distance_km":  offer.get("distance_km", 0),
                "carbon":       self.session.carbon_result,
                "ts":           int(time.time()),
            })
        else:
            msg = (
                f"⚠️ Payment request failed: {result.get('error', 'unknown error')}\n"
                f"Please try again or choose a different payment method."
            )
            self.session.state = TripState.CONFIRMING

        return OrchestratorResponse(
            message       = msg,
            chosen_offer  = offer,
            payment       = result,
            trip_id       = self.session.trip_id,
            carbon_result = self.session.carbon_result,
            state         = self.session.state.value,
            log           = self.log.as_dicts(),
        )

    def _check_payment(self, phone: str, text: str) -> "OrchestratorResponse":
        """Rider messages while payment is pending."""
        if self.session.paid:
            offer = self.session.chosen_offer or {}
            return OrchestratorResponse(
                message=(
                    f"✅ *Booking confirmed!*\n\n"
                    f"🚗 {offer.get('ev_model','EV')} is on the way\n"
                    f"👤 {offer.get('driver_name','Your driver')} • ⭐ {offer.get('driver_rating',5.0)}\n"
                    f"📞 {offer.get('driver_phone','')}\n"
                    f"🚘 {offer.get('plate','')}\n"
                    f"⏱️ ETA: {offer.get('eta_min',5)} min\n\n"
                    f"🌿 _Thank you for choosing a green ride!_\n"
                    f"Reply *MENU* to book another ride."
                ),
                state=TripState.BOOKED.value,
                log=self.log.as_dicts(),
            )
        return OrchestratorResponse(
            message="⏳ Waiting for payment confirmation… Please complete the M-Pesa prompt on your phone.",
            state=TripState.PAYING.value,
            log=self.log.as_dicts(),
        )

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _format_ride_list(self, geo: dict, offers: list[dict]) -> str:
        dist = offers[0]["distance_km"] if offers else 0
        lines = [
            f"🌿 *Go Green EV Rides*\n",
            f"📍 *From:* {geo['pickup']}",
            f"🏁 *To:* {geo['destination']}",
            f"🛣️ Distance: ~{dist:.1f} km\n",
            "Choose your ride:\n",
        ]
        for i, o in enumerate(offers[:7], 1):
            surge_tag = f" 🔺×{o['surge']}" if o["surge"] > 1.0 else ""
            promo_tag = f" 🏷️{o['promo_code']}" if o.get("promo_code") else ""
            lines.append(
                f"*{i}.* {o['provider']} — {o['ride_type']}\n"
                f"   💰 *KSh {o['price_kes']:,.0f}*{surge_tag}{promo_tag}\n"
                f"   ⏱️ {o['eta_min']} min ETA  •  🚗 {o['ev_model']}\n"
                f"   ⭐ {o['driver_rating']}  •  🌱 {o['co2_saved_g']:.0f}g CO₂ saved\n"
            )
        lines.append("_Reply with a number (1-7) to select your ride._")
        return "\n".join(lines)

    def _is_ride_choice(self, text: str) -> bool:
        t = text.lower().strip()
        if t.isdigit() and 1 <= int(t) <= 7:
            return True
        providers = ["uber","bolt","yego","faras","little","wasili","weego"]
        return any(p in t for p in providers)

    def _resolve_choice(self, text: str, offers: list[dict]) -> dict | None:
        t = text.lower().strip()
        if t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(offers):
                return offers[idx]
        for o in offers:
            if o["provider"].lower() in t or o["provider_slug"] in t:
                return o
        return None

    # ── Execution log helpers ─────────────────────────────────────────────────

    def _step(self, agent: str, task: str) -> ExecutionStep:
        step = self.log.add(ExecutionStep(agent_name=agent, task=task, status=StepStatus.RUNNING))
        if self._on_step:
            self._on_step(step.to_dict())
        return step

    def _done(self, step: ExecutionStep, result: str) -> None:
        step.status = StepStatus.DONE
        step.result = result
        if self._on_step:
            self._on_step(step.to_dict())

    # ── MCP wiring ────────────────────────────────────────────────────────────

    def _wire_mcp(self) -> None:
        def save_place(phone: str, label: str, address: str) -> str:
            self.memory.remember(f"saved:{phone}:{label}", address)
            return f"Saved '{label}' = {address}"

        def get_saved(phone: str) -> dict:
            return self.memory.search(f"saved:{phone}:")

        def trip_history(phone: str) -> list:
            return list(self.memory.search("trip:").values())

        self.mcp.connect_server("places", "Saved places (home, work, etc.)", {
            "save": save_place, "get": get_saved,
        })
        self.mcp.connect_server("history", "Trip history", {
            "list": trip_history,
        })
        self.mcp.connect_server("carbon-ledger", "Verra VM0038 carbon credit ledger per rider", {
            "summary": lambda phone: self._carbon_ledger.summary(phone),
            "total_vcu": lambda phone: self._carbon_ledger.total_vcu(phone),
            "total_co2_kg": lambda phone: self._carbon_ledger.total_co2_saved_kg(phone),
        })


# ─────────────────────────────────────────────────────────────────────────────
# Response model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResponse:
    message:       str
    state:         str        = TripState.IDLE.value
    log:           list[dict] = field(default_factory=list)
    offers:        list[dict] = field(default_factory=list)
    chosen_offer:  dict | None = None
    payment:       dict | None = None
    carbon_result: dict | None = None   # Verra VM0038 GHG result
    pickup:        str        = ""
    destination:   str        = ""
    pickup_lat:    float      = 0.0
    pickup_lon:    float      = 0.0
    drop_lat:      float      = 0.0
    drop_lon:      float      = 0.0
    trip_id:       str        = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})}
