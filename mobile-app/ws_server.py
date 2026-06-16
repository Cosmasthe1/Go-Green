"""
ws_server.py — Go Green
────────────────────────────────────────────────────────────────────────────
WebSocket server + REST API endpoints that the Ionic app connects to.

Add to app.py:
    from ws_server import register_ws_and_api
    register_ws_and_api(flask_app, wa_agent)

Requires:
    pip install flask-sock

Endpoints added:
  GET  /ws                             WebSocket (real-time trip updates)
  GET  /api/whatsapp/history/<phone>   Chat history sync
  POST /api/whatsapp/send              Send message through WhatsApp agent
  POST /api/rides/search               Search EV rides
  POST /api/rides/book                 Book a ride + M-Pesa STK push
  GET  /api/rides/status/<request_id>  Trip status poll
  POST /api/rides/cancel               Cancel trip
  GET  /api/carbon/portfolio/<phone>   Carbon VCU portfolio
  POST /api/geo/geocode                Geocode an address
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from flask import Flask, jsonify, request
from flask_sock import Sock

logger = logging.getLogger(__name__)

# Active WebSocket connections keyed by phone number
_ws_connections: dict[str, Any] = {}
_ws_lock = threading.Lock()


def register_ws_and_api(app: Flask, wa_agent) -> None:
    """
    Register all WebSocket and REST API routes on the Flask app.
    Call once in app.py after creating the Flask instance.
    """
    sock = Sock(app)

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @sock.route('/ws')
    def ws_handler(ws):
        """
        Real-time WebSocket connection.
        Client sends: {"type": "auth", "phone": "+254712345678"}
        Server pushes: {"type": "trip_status"|"agent_step"|"message", "payload": {...}}
        """
        phone = request.args.get('phone', 'unknown')
        logger.info("WS connected: %s", phone)

        with _ws_lock:
            _ws_connections[phone] = ws

        try:
            while True:
                raw = ws.receive(timeout=30)
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                    if msg.get('type') == 'ping':
                        ws.send(json.dumps({'type': 'pong'}))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with _ws_lock:
                _ws_connections.pop(phone, None)
            logger.info("WS disconnected: %s", phone)

    # ── WhatsApp history sync ─────────────────────────────────────────────────

    @app.route('/api/whatsapp/history/<path:phone>')
    def wa_history(phone: str):
        """Return the conversation history for a phone number."""
        try:
            orch = wa_agent.get_or_create(phone)
            history = orch.short_term.get_history()
            messages = []
            for i, m in enumerate(history):
                messages.append({
                    'id':        str(i),
                    'role':      'user' if m['role'] == 'user' else 'bot',
                    'text':      m['content'] if isinstance(m['content'], str) else str(m['content']),
                    'timestamp': 0,
                })
            return jsonify(messages)
        except Exception as e:
            return jsonify([]), 200

    # ── Send WhatsApp message ─────────────────────────────────────────────────

    @app.route('/api/whatsapp/send', methods=['POST'])
    def wa_send():
        """Send a message through the WhatsApp orchestrator and return the reply."""
        data   = request.get_json() or {}
        phone  = data.get('phone', '+254712345678')
        text   = data.get('text', '')

        try:
            resp = wa_agent.process_message(phone, text)
            result = {
                'reply':  resp.message,
                'state':  resp.state,
                'offers': resp.offers or [],
            }
            # Push reply to WebSocket if connected
            _ws_push(phone, {'type': 'message', 'payload': {
                'id':        f'ws-{id(resp)}',
                'role':      'bot',
                'text':      resp.message,
                'timestamp': 0,
                'offers':    resp.offers or [],
            }})
            return jsonify(result)
        except Exception as e:
            return jsonify({'reply': f'Error: {e}', 'state': 'idle', 'offers': []}), 500

    # ── Ride search ───────────────────────────────────────────────────────────

    @app.route('/api/rides/search', methods=['POST'])
    def rides_search():
        """Search for EV rides on a route."""
        data  = request.get_json() or {}
        phone = data.get('phone', '+254712345678')
        query = data.get('query', 'Westlands to Karen')

        try:
            orch = wa_agent.get_or_create(phone)
            # Parse and geocode
            geo  = orch.location.parse_and_geocode(query)
            offers = orch.ride.get_offers(
                geo['pickup_lat'], geo['pickup_lon'],
                geo['drop_lat'],   geo['drop_lon'],
            )
            return jsonify({
                'pickup':      geo['pickup'],
                'destination': geo['destination'],
                'pickup_lat':  geo['pickup_lat'],
                'pickup_lon':  geo['pickup_lon'],
                'drop_lat':    geo['drop_lat'],
                'drop_lon':    geo['drop_lon'],
                'offers':      offers,
                'log':         [],
            })
        except Exception as e:
            logger.exception("rides_search error")
            return jsonify({'error': str(e), 'offers': []}), 500

    # ── Book ride ─────────────────────────────────────────────────────────────

    @app.route('/api/rides/book', methods=['POST'])
    def rides_book():
        """Book a ride and initiate M-Pesa STK push."""
        data     = request.get_json() or {}
        phone    = data.get('phone', '+254712345678')
        offer    = data.get('offer', {})

        try:
            orch  = wa_agent.get_or_create(phone)
            # Simulate the confirmation flow
            orch.session.chosen_offer = offer
            orch.session.trip_id = f"GG-{__import__('time').time_ns() // 1_000_000}"
            orch.session.pickup      = data.get('pickup', '')
            orch.session.destination = data.get('destination', '')

            # Trigger payment
            from mpesa import STKPushRequest, mpesa as _mpesa
            amount = int(round(offer.get('price_kes', 500)))
            req    = STKPushRequest(
                phone_number = _mpesa.normalise_phone(phone),
                amount       = amount,
                account_ref  = orch.session.trip_id[:12],
                description  = 'Go Green EV Ride',
            )
            pay_result = _mpesa.stk_push(req)

            # Carbon calculation
            carbon_result = None
            try:
                dist = offer.get('distance_km', 10.0)
                from carbon import GHGCalculator, VehicleCategory
                cr = GHGCalculator.calculate_trip(VehicleCategory.PSV_PASSENGER_CAR, dist, 'L2')
                carbon_result = cr.to_dict()
            except Exception:
                pass

            # Push to WebSocket
            _ws_push(phone, {'type': 'payment_confirmed', 'payload': {
                'trip_id': orch.session.trip_id,
                'amount':  amount,
            }})

            return jsonify({
                'success':      pay_result.get('success', True),
                'trip_id':      orch.session.trip_id,
                'request_id':   pay_result.get('checkout_request_id', ''),
                'status':       'processing',
                'customer_msg': pay_result.get('customer_msg', 'STK push sent'),
                'driver_name':  offer.get('driver_name', ''),
                'driver_phone': offer.get('driver_phone', ''),
                'plate':        offer.get('plate', ''),
                'ev_model':     offer.get('ev_model', ''),
                'carbon_result': carbon_result,
                'error':        pay_result.get('error', ''),
            })
        except Exception as e:
            logger.exception("rides_book error")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ── Trip status ───────────────────────────────────────────────────────────

    @app.route('/api/rides/status/<request_id>')
    def rides_status(request_id: str):
        """Poll Uber trip status."""
        try:
            from uber_green import uber_client
            detail = uber_client.get_trip(request_id)
            return jsonify({
                'request_id':    request_id,
                'status':        detail.status,
                'driver_name':   detail.driver.name   if detail.driver  else '',
                'driver_phone':  detail.driver.phone_number if detail.driver else '',
                'driver_rating': detail.driver.rating if detail.driver  else 4.8,
                'plate':         detail.vehicle.license_plate if detail.vehicle else '',
                'ev_model':      f"{detail.vehicle.make} {detail.vehicle.model}" if detail.vehicle else '',
                'eta_min':       detail.eta or 5,
            })
        except Exception:
            return jsonify({'request_id': request_id, 'status': 'processing', 'eta_min': 5})

    # ── Cancel trip ───────────────────────────────────────────────────────────

    @app.route('/api/rides/cancel', methods=['POST'])
    def rides_cancel():
        data = request.get_json() or {}
        rid  = data.get('request_id', '')
        try:
            from uber_green import uber_client
            ok = uber_client.cancel_trip(rid)
            return jsonify({'success': ok})
        except Exception:
            return jsonify({'success': True})   # best-effort

    # ── Carbon portfolio ──────────────────────────────────────────────────────

    @app.route('/api/carbon/portfolio/<path:phone>')
    def carbon_portfolio(phone: str):
        """Return a rider's carbon credit portfolio."""
        try:
            orch = wa_agent.get_or_create(phone)
            summary = orch._carbon_ledger.summary(phone)
            return jsonify(summary)
        except Exception as e:
            return jsonify({'phone': phone, 'total_trips': 0, 'total_vcu': 0,
                            'total_co2_kg': 0, 'total_value_kes': 0, 'entries': []})

    # ── Geocode ───────────────────────────────────────────────────────────────

    @app.route('/api/geo/geocode', methods=['POST'])
    def geo_geocode():
        data    = request.get_json() or {}
        address = data.get('address', '')
        try:
            from orchestrator_agent import LocationAgent
            result = LocationAgent._geocode(address)
            return jsonify({'lat': result['lat'], 'lon': result['lon'], 'found': result['found']})
        except Exception:
            return jsonify({'lat': -1.2833, 'lon': 36.8172, 'found': False})


# ── WebSocket push helper ─────────────────────────────────────────────────────

def _ws_push(phone: str, payload: dict) -> None:
    """Push a JSON event to a connected WebSocket client."""
    with _ws_lock:
        ws = _ws_connections.get(phone)
    if ws:
        try:
            ws.send(json.dumps(payload))
        except Exception as e:
            logger.debug("WS push failed for %s: %s", phone, e)


def push_trip_update(phone: str, status: str, detail: dict) -> None:
    """Call this from the orchestrator to push live driver updates."""
    _ws_push(phone, {'type': 'trip_status', 'payload': {'status': status, **detail}})


def push_agent_step(phone: str, step: dict) -> None:
    """Call this from agent callbacks to stream agent steps to the app."""
    _ws_push(phone, {'type': 'agent_step', 'payload': step})
