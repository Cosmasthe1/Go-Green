"""
whatsapp_agent.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
WhatsApp channel agent.

Handles:
  • Inbound webhook from Twilio WhatsApp Sandbox OR Meta WhatsApp Cloud API
  • Parses rider messages and routes them to GoGreenOrchestrator
  • Formats and sends rich WhatsApp responses back to the rider
  • Maintains one TripSession per phone number (in-process dict)

Environment variables needed:
  Provider: "twilio" (default) or "meta"

  -- Twilio --
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_WHATSAPP_FROM   e.g. whatsapp:+14155238886

  -- Meta Cloud API --
  META_ACCESS_TOKEN
  META_PHONE_NUMBER_ID
  META_VERIFY_TOKEN      (for webhook verification)

  GOGREEN_BASE_URL       public base URL of this server (for webhook registration)
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

import requests
from flask import Flask, Request, jsonify, request

from orchestrator_agent import GoGreenOrchestrator, OrchestratorResponse, TripState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER           = os.environ.get("WA_PROVIDER", "twilio").lower()   # "twilio" | "meta"

# Twilio
TWILIO_SID         = os.environ.get("TWILIO_ACCOUNT_SID",    "")
TWILIO_TOKEN       = os.environ.get("TWILIO_AUTH_TOKEN",     "")
TWILIO_FROM        = os.environ.get("TWILIO_WHATSAPP_FROM",  "whatsapp:+14155238886")

# Meta
META_ACCESS_TOKEN  = os.environ.get("META_ACCESS_TOKEN",     "")
META_PHONE_ID      = os.environ.get("META_PHONE_NUMBER_ID",  "")
META_VERIFY_TOKEN  = os.environ.get("META_VERIFY_TOKEN",     "gogreen_verify_2025")

# ─────────────────────────────────────────────────────────────────────────────
# Session store  (phone → orchestrator)
# In production use Redis + pickle / JSON serialisation
# ─────────────────────────────────────────────────────────────────────────────

_sessions: dict[str, GoGreenOrchestrator] = {}
_session_ts: dict[str, float]             = {}
SESSION_TTL = 3600   # 1 hour idle before reset


def _get_orchestrator(phone: str) -> GoGreenOrchestrator:
    now = time.time()
    if phone in _sessions and now - _session_ts.get(phone, 0) < SESSION_TTL:
        _session_ts[phone] = now
        return _sessions[phone]
    orch = GoGreenOrchestrator()
    _sessions[phone] = orch
    _session_ts[phone] = now
    return orch


# ─────────────────────────────────────────────────────────────────────────────
# Outbound message senders
# ─────────────────────────────────────────────────────────────────────────────

def _send_twilio(to_phone: str, body: str) -> bool:
    """Send a WhatsApp message via Twilio."""
    try:
        from twilio.rest import Client  # pip install twilio
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body = body,
            from_= TWILIO_FROM,
            to   = f"whatsapp:{to_phone}",
        )
        return True
    except ImportError:
        # Fallback: raw REST call
        import base64
        auth  = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        url   = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        resp  = requests.post(url, headers={"Authorization": f"Basic {auth}"}, data={
            "Body": body, "From": TWILIO_FROM, "To": f"whatsapp:{to_phone}",
        }, timeout=10)
        return resp.status_code == 201
    except Exception as exc:
        logger.error("Twilio send failed: %s", exc)
        return False


def _send_meta(to_phone: str, body: str) -> bool:
    """Send a WhatsApp message via Meta Cloud API."""
    url = f"https://graph.facebook.com/v19.0/{META_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to":   to_phone,
        "type": "text",
        "text": {"body": body, "preview_url": False},
    }
    try:
        resp = requests.post(
            url,
            json    = payload,
            headers = {
                "Authorization": f"Bearer {META_ACCESS_TOKEN}",
                "Content-Type":  "application/json",
            },
            timeout = 10,
        )
        return resp.status_code == 200
    except Exception as exc:
        logger.error("Meta send failed: %s", exc)
        return False


def send_whatsapp(phone: str, message: str) -> bool:
    """Unified send — routes to Twilio or Meta based on PROVIDER env var."""
    logger.info("→ WhatsApp [%s]: %s…", phone, message[:60])
    if PROVIDER == "meta":
        return _send_meta(phone, message)
    return _send_twilio(phone, message)


# ─────────────────────────────────────────────────────────────────────────────
# Inbound message parsers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_twilio(req: Request) -> tuple[str, str] | None:
    """Extract (phone, body) from a Twilio WhatsApp webhook POST."""
    form = req.form
    phone = form.get("From", "").replace("whatsapp:", "")
    body  = form.get("Body", "").strip()
    if not phone or not body:
        return None
    return phone, body


def _parse_meta(req: Request) -> tuple[str, str] | None:
    """Extract (phone, body) from a Meta Cloud API webhook POST."""
    try:
        data   = req.get_json(force=True) or {}
        entry  = data.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value  = change.get("value", {})
        msgs   = value.get("messages", [])
        if not msgs:
            return None
        msg   = msgs[0]
        phone = msg.get("from", "")
        body  = msg.get("text", {}).get("body", "").strip()
        if not phone or not body:
            return None
        return phone, body
    except Exception as exc:
        logger.warning("Meta parse error: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Flask webhook blueprint
# ─────────────────────────────────────────────────────────────────────────────

def create_whatsapp_blueprint():
    """
    Returns a Flask Blueprint with WhatsApp webhook routes.
    Mount at /api/whatsapp in app.py.
    """
    from flask import Blueprint
    bp = Blueprint("whatsapp", __name__)

    @bp.route("/webhook", methods=["GET"])
    def verify():
        """Meta webhook verification handshake."""
        mode      = request.args.get("hub.mode")
        token     = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == META_VERIFY_TOKEN:
            logger.info("Meta webhook verified")
            return challenge, 200
        return "Forbidden", 403

    @bp.route("/webhook", methods=["POST"])
    def webhook():
        """Inbound message handler."""
        if PROVIDER == "meta":
            parsed = _parse_meta(request)
        else:
            parsed = _parse_twilio(request)

        if not parsed:
            return jsonify({"status": "ignored"}), 200

        phone, body = parsed
        logger.info("← WhatsApp [%s]: %s", phone, body[:80])

        try:
            orch     = _get_orchestrator(phone)
            response = orch.handle_message(phone, body)
            send_whatsapp(phone, response.message)
        except Exception as exc:
            logger.exception("Webhook handler error: %s", exc)
            send_whatsapp(phone, "⚠️ Something went wrong. Please try again or type *MENU*.")

        # Twilio expects 200 + empty TwiML or plain 200
        return jsonify({"status": "ok"}), 200

    return bp


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Agent class  (used by app.py UI for the demo simulator)
# ─────────────────────────────────────────────────────────────────────────────

class WhatsAppAgent:
    """
    Thin wrapper used by the Gradio demo UI to simulate WhatsApp conversations
    without a real webhook. The UI calls process_message() directly.
    """

    def __init__(self) -> None:
        self._orchestrators: dict[str, GoGreenOrchestrator] = {}

    def get_or_create(self, phone: str) -> GoGreenOrchestrator:
        if phone not in self._orchestrators:
            self._orchestrators[phone] = GoGreenOrchestrator()
        return self._orchestrators[phone]

    def process_message(self, phone: str, text: str) -> OrchestratorResponse:
        orch = self.get_or_create(phone)
        return orch.handle_message(phone, text)

    def reset_session(self, phone: str) -> None:
        if phone in self._orchestrators:
            del self._orchestrators[phone]

    def session_state(self, phone: str) -> str:
        orch = self._orchestrators.get(phone)
        if orch:
            return orch.session.state.value
        return TripState.IDLE.value
