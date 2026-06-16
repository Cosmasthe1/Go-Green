"""
app.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
Entry point. Runs two services in one process:

  1. Gradio  — interactive WhatsApp simulator UI  (port 7860)
             Tabs: WhatsApp | Rides | Map | 💳 Payment | 🌿 Carbon Credits
  2. Flask   — real WhatsApp webhook server       (port 5000)

Carbon credit engine (Verra VM0038 v1.0) fires automatically after
every confirmed M-Pesa payment and accrues VCUs to the rider ledger.

Run:
  pip install gradio anthropic flask requests
  export ANTHROPIC_API_KEY=sk-...
  python app.py
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time

import gradio as gr
from flask import Flask

from carbon.ghg_calculator import GHGCalculator
from carbon.verra_constants import VehicleCategory, VCU_PRICE_KES, NET_VCU_FACTOR
from orchestrator_agent import TripState
from whatsapp_agent import WhatsAppAgent, create_whatsapp_blueprint

# ─────────────────────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────────────────────

wa_agent    = WhatsAppAgent()
_step_queue: queue.Queue[dict] = queue.Queue()
DEMO_PHONE  = "+254712345678"


# ─────────────────────────────────────────────────────────────────────────────
# Flask webhook (background thread)
# ─────────────────────────────────────────────────────────────────────────────

flask_app = Flask(__name__)
flask_app.register_blueprint(create_whatsapp_blueprint(), url_prefix="/api/whatsapp")

@flask_app.route("/health")
def health():
    return {"status": "ok", "service": "Go Green"}

def _run_flask():
    flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


# ─────────────────────────────────────────────────────────────────────────────
# HTML renderers
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_META = {
    "Uber":        {"color": "#ffffff", "bg": "#111"},
    "Bolt":        {"color": "#34D186", "bg": "#0d2a1e"},
    "Yego":        {"color": "#FF6B00", "bg": "#2a1600"},
    "Faras":       {"color": "#1A56DB", "bg": "#0d1a33"},
    "Little Cabs": {"color": "#FECC00", "bg": "#2a2500"},
    "Wasili":      {"color": "#7C3AED", "bg": "#1a0d33"},
    "Weego":       {"color": "#059669", "bg": "#0d2a1e"},
}


def render_ride_cards(offers: list[dict]) -> str:
    if not offers:
        return ""
    cards = []
    for i, o in enumerate(offers[:7]):
        meta   = PROVIDER_META.get(o["provider"], {"color": "#6366f1", "bg": "#0f172a"})
        ac, bg = meta["color"], meta["bg"]
        is_top = i == 0
        surge  = (f'<span style="color:#f87171;font-size:10px;font-weight:700"> ▲×{o["surge"]}</span>'
                  if o["surge"] > 1.0 else "")
        promo  = (f'<span style="background:#14532d;color:#4ade80;padding:1px 8px;border-radius:10px;'
                  f'font-size:10px;font-weight:700;margin-left:6px">🏷 {o["promo_code"]}</span>'
                  if o.get("promo_code") else "")
        txt    = "#000" if ac in ("#FECC00","#34D186","#ffffff") else "#fff"
        cards.append(f"""
<div style="background:{bg};border:{'2px solid '+ac if is_top else '1px solid #1e293b'};
  border-radius:12px;padding:12px 14px;margin-bottom:8px;position:relative;
  transition:transform .15s" onmouseover="this.style.transform='translateY(-2px)'"
  onmouseout="this.style.transform='none'">
  {'<div style="position:absolute;top:-8px;left:12px;background:'+ac+';color:'+txt+';font-size:9px;font-weight:800;padding:2px 10px;border-radius:20px">🏆 BEST VALUE</div>' if is_top else ''}
  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="background:{ac};color:{txt};font-size:10px;font-weight:900;padding:3px 10px;border-radius:7px">{o['provider'].upper()}</div>
      <div>
        <div style="font-size:12px;font-weight:700;color:#e2e8f0">{o['ride_type']}</div>
        <div style="font-size:10px;color:#475569">{o['ev_model']}</div>
      </div>
    </div>
    <div style="text-align:right">
      <div style="font-size:20px;font-weight:900;color:{ac}">KSh {o['price_kes']:,.0f}{surge}</div>
      <div style="font-size:10px;color:#475569">{o['distance_km']:.1f} km</div>
    </div>
  </div>
  <div style="display:flex;gap:14px;margin-top:8px;flex-wrap:wrap;font-size:10px;color:#94a3b8">
    <span>⏱ <b style="color:#e2e8f0">{o['eta_min']}m</b></span>
    <span>⭐ {o['driver_rating']}</span>
    <span>👤 {o['driver_name']}</span>
    <span style="color:#4ade80">🌱 {o['co2_saved_g']:.0f}g CO₂</span>
    {promo}
  </div>
</div>""")
    return "\n".join(cards)


def render_map_html(
    pickup_lat: float, pickup_lon: float,
    drop_lat:   float, drop_lon:   float,
    pickup_name: str = "Pickup",
    drop_name:   str = "Destination",
) -> str:
    if not pickup_lat or not drop_lat:
        return ""
    center_lat = (pickup_lat + drop_lat) / 2
    center_lon = (pickup_lon + drop_lon) / 2
    return f"""
<div id="gogreen-map" style="height:280px;border-radius:14px;overflow:hidden;border:1px solid #1a3a1a"></div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){{
  var s=document.createElement('script');s.id='_gg_map_init';
  s.textContent=`setTimeout(function(){{
    var old=L._ggmap;if(old)old.remove();
    var map=L.map('gogreen-map',{{zoomControl:true,attributionControl:false}}).setView([{center_lat},{center_lon}],13);
    L._ggmap=map;
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{subdomains:'abcd',maxZoom:19}}).addTo(map);
    var gi=L.divIcon({{html:'<div style="background:#22c55e;width:13px;height:13px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 8px #22c55e88"></div>',className:'',iconAnchor:[6,6]}});
    var ri=L.divIcon({{html:'<div style="background:#f43f5e;width:13px;height:13px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 8px #f43f5e88"></div>',className:'',iconAnchor:[6,6]}});
    L.marker([{pickup_lat},{pickup_lon}],{{icon:gi}}).addTo(map).bindPopup('<b>📍 {pickup_name}</b>').openPopup();
    L.marker([{drop_lat},{drop_lon}],{{icon:ri}}).addTo(map).bindPopup('<b>🏁 {drop_name}</b>');
    L.polyline([[{pickup_lat},{pickup_lon}],[{drop_lat},{drop_lon}]],{{color:'#34d186',weight:3,dashArray:'6 4',opacity:.85}}).addTo(map);
    map.fitBounds([[{pickup_lat},{pickup_lon}],[{drop_lat},{drop_lon}]],{{padding:[30,30]}});
  }},200);`;
  var old=document.getElementById('_gg_map_init');if(old)old.remove();
  document.body.appendChild(s);
}})();
</script>"""


def render_payment_html(offer: dict, trip_id: str, phone: str) -> str:
    ac = PROVIDER_META.get(offer.get("provider", ""), {}).get("color", "#34d186")
    return f"""
<div style="background:#0d1f0d;border:1px solid #22c55e44;border-radius:14px;padding:18px">
  <div style="font-size:11px;color:#4ade80;letter-spacing:.8px;margin-bottom:8px">💳 M-PESA PAYMENT</div>
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
    <div style="background:#22c55e22;border:1px solid #22c55e44;border-radius:10px;padding:8px 16px;
         font-size:24px;font-weight:900;color:#22c55e">KSh {offer.get('price_kes',0):,.0f}</div>
    <div>
      <div style="font-size:11px;color:#94a3b8">Trip ID</div>
      <div style="font-size:12px;font-weight:700;color:#e2e8f0;font-family:monospace">{trip_id}</div>
    </div>
  </div>
  <div style="background:#0a2e0a;border-radius:10px;padding:12px;font-size:12px;color:#86efac;line-height:1.8">
    📱 STK push → <b>{phone}</b><br>
    Enter M-Pesa PIN to confirm payment.<br>
    <span style="color:#4ade80;font-weight:700">✓ Secure · Instant · No card needed</span>
  </div>
</div>"""


def render_carbon_html(carbon: dict, phone: str, orch=None) -> str:
    """Render Verra VM0038 carbon credit panel with per-trip result + portfolio total."""
    if not carbon:
        return '<div style="color:#1a3a1a;padding:30px;text-align:center;font-size:12px">✦ Carbon credits will appear after your first confirmed trip</div>'

    vcu      = carbon.get("net_vcu", 0)
    kg       = carbon.get("net_reduction_kg", 0)
    trees    = carbon.get("trees_equivalent", 0)
    kes      = carbon.get("vcu_value_kes", 0)
    be_kg    = carbon.get("baseline_emissions_kg", 0)
    pe_kg    = carbon.get("project_emissions_kg", 0)
    dist     = carbon.get("distance_km", 0)
    charger  = carbon.get("charger_type", "L2")

    # Portfolio totals from ledger
    total_vcu, total_kg, total_kes, total_trips = vcu, kg, kes, 1
    if orch:
        try:
            ledger  = orch._carbon_ledger
            total_vcu   = ledger.total_vcu(phone)
            total_kg    = ledger.total_co2_saved_kg(phone)
            total_kes   = ledger.total_value_kes(phone)
            total_trips = len(ledger.get_entries(phone))
        except Exception:
            pass

    def card(title, value, sub, color):
        return f"""<div style="background:#060f07;border:1px solid {color}33;border-left:3px solid {color};
          border-radius:10px;padding:11px 13px">
          <div style="font-size:9px;color:#475569;letter-spacing:.6px;margin-bottom:3px">{title}</div>
          <div style="font-size:18px;font-weight:800;color:{color};font-family:'IBM Plex Mono',monospace;line-height:1.1">{value}</div>
          <div style="font-size:9px;color:#334155;margin-top:2px">{sub}</div>
        </div>"""

    return f"""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<div style="font-family:'Outfit',sans-serif">
  <div style="font-size:10px;color:#4ade80;letter-spacing:.8px;margin-bottom:10px">🌿 THIS TRIP — VERRA VM0038 v1.0</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px">
    {card("🌿 CO₂ SAVED",    f"{kg*1000:.0f}g",       f"{kg/1000:.6f} tCO₂e",      "#10b981")}
    {card("💎 VCUs EARNED",  f"{vcu:.8f}",              "Verra Verified Credits",     "#8b5cf6")}
    {card("💰 VCU VALUE",    f"KSh {kes:.4f}",          f"≈ USD {kes/130:.5f}",       "#f59e0b")}
    {card("🌳 TREES EQUIV.", f"{trees:.4f}",             "trees absorbing CO₂/yr",    "#22c55e")}
    {card("⛽ BASELINE",     f"{be_kg*1000:.0f}g",       f"ICE would have emitted",   "#ef4444")}
    {card("🔋 GRID PE",      f"{pe_kg*1000:.1f}g",       f"EV grid: 0.061 kgCO₂/kWh","#6366f1")}
  </div>

  <div style="background:#030d04;border:1px solid #0d2a10;border-radius:10px;padding:11px 13px;
       font-family:'IBM Plex Mono',monospace;font-size:10px;color:#4ade80;line-height:1.8;margin-bottom:12px">
    <div style="font-size:9px;color:#1e4d20;letter-spacing:.6px;margin-bottom:5px">VM0038 FORMULA</div>
    BE = {dist:.1f}km × AFEC × EF_petrol × WTT = <b>{be_kg*1000:.0f}g CO₂e</b><br>
    PE = kWh ÷ η_{charger} × 0.061 kgCO₂/kWh = <b>{pe_kg*1000:.1f}g CO₂e</b><br>
    ER = BE − PE − 3% leakage = <b>{kg*1000:.0f}g</b> → VCS buffer → <b style="color:#a3e635">{vcu:.8f} VCU</b>
  </div>

  <div style="font-size:10px;color:#4ade80;letter-spacing:.8px;margin-bottom:8px">📊 YOUR PORTFOLIO — ALL TRIPS</div>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:10px">
    {card("🚗 EV TRIPS",       str(total_trips),                f"Go Green rides taken",            "#6366f1")}
    {card("🌿 TOTAL CO₂",      f"{total_kg*1000:.0f}g",         f"= {total_kg/1000:.5f} tCO₂e",     "#10b981")}
    {card("💎 TOTAL VCUs",     f"{total_vcu:.7f}",               "Verra Verified Carbon Units",      "#8b5cf6")}
    {card("💰 PORTFOLIO",      f"KSh {total_kes:.2f}",           f"≈ USD {total_kes/130:.4f}",        "#f59e0b")}
  </div>

  <div style="background:#0d1f0d;border:1px solid #22c55e22;border-radius:8px;
       padding:9px 12px;font-size:10px;color:#1e4d20;line-height:1.7;font-family:'IBM Plex Mono',monospace">
    <b style="color:#4ade80">Methodology:</b> Verra VM0038 v1.0 · EV Charging Systems<br>
    <b style="color:#4ade80">Additionality:</b> VMD0049 positive list — Kenya EV &lt;5% ✅<br>
    <b style="color:#4ade80">Grid EF:</b> 0.061 kgCO₂e/kWh (IEA 2024, >90% renewable)<br>
    <b style="color:#4ade80">NET_FACTOR:</b> {NET_VCU_FACTOR:.4f} (3% leakage + 10% VCS buffer)
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Gradio chat logic
# ─────────────────────────────────────────────────────────────────────────────

def send_message(phone: str, user_text: str, history: list):
    if not user_text.strip():
        yield history, "", "", "", "", ""
        return

    phone   = phone.strip() or DEMO_PHONE
    history = history + [[user_text, None]]
    yield history, "", "", "", "", ""

    resp = wa_agent.process_message(phone, user_text)
    history[-1][1] = resp.message
    yield history, "", "", "", "", ""

    cards_html   = render_ride_cards(resp.offers) if resp.offers else ""
    map_html     = ""
    payment_html = ""
    carbon_html  = ""

    if resp.pickup_lat and resp.drop_lat:
        map_html = render_map_html(
            resp.pickup_lat, resp.pickup_lon,
            resp.drop_lat,   resp.drop_lon,
            resp.pickup or "Pickup",
            resp.destination or "Destination",
        )

    if resp.payment and resp.payment.get("success") and resp.chosen_offer:
        payment_html = render_payment_html(resp.chosen_offer, resp.trip_id or "", phone)

    if resp.carbon_result:
        orch = wa_agent.get_or_create(phone)
        carbon_html = render_carbon_html(resp.carbon_result, phone, orch)

    log_md = _render_log(resp.log)
    yield history, cards_html, map_html, payment_html, carbon_html, log_md


def _render_log(steps: list[dict]) -> str:
    if not steps:
        return "_Agents standing by…_"
    icons = {"running": "🔄", "done": "✅", "error": "❌", "pending": "⬜", "awaiting_human": "🟡"}
    lines = []
    for s in steps:
        icon = icons.get(s["status"], "•")
        line = f"{icon} **[{s['agent']}]** {s['task']}"
        if s.get("result"):
            line += f"\n   ↳ _{s['result'][:90]}_"
        lines.append(line)
    return "\n\n".join(lines)


def reset_chat(phone: str):
    phone = phone.strip() or DEMO_PHONE
    wa_agent.reset_session(phone)
    return [], "", "", "", "", "_Session reset._"


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800;900&family=Space+Mono:wght@400;700&display=swap');

*, body, .gradio-container {
    font-family: 'Outfit', sans-serif !important;
    background-color: #030a06 !important;
    color: #e2e8f0 !important;
}
#gg-header { text-align:center; padding:2rem 1rem 1rem; position:relative }
#gg-header::before { content:''; position:absolute; inset:0;
  background:radial-gradient(ellipse 600px 200px at 50% 0%,#14532d22,transparent); pointer-events:none }
#gg-header h1 { font-size:2.6rem; font-weight:900; letter-spacing:-1px;
  background:linear-gradient(135deg,#22c55e 0%,#4ade80 40%,#86efac 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; line-height:1; margin:0 0 .3rem }
#gg-header .tagline { color:#475569; font-size:.88rem; margin-bottom:.8rem }
.ev-badge { display:inline-block; background:#14532d44; border:1px solid #22c55e22; color:#4ade80;
  padding:3px 12px; border-radius:20px; font-size:10px; font-weight:700; margin:2px 3px; letter-spacing:.3px }
#phone-input input { background:#0d1f0d !important; border:1px solid #1a3a1a !important;
  border-radius:10px !important; color:#4ade80 !important; font-family:'Space Mono',monospace !important }
#wa-chat { background:#0a1a0d !important; border:1px solid #1a3a1a !important; border-radius:16px !important; min-height:400px !important }
#wa-chat .message.user { background:#14532d !important; border-radius:14px 14px 4px 14px !important; color:#dcfce7 !important; font-size:12px !important; max-width:75% !important }
#wa-chat .message.bot  { background:#0d1f0d !important; border:1px solid #1a3a1a !important; border-radius:14px 14px 14px 4px !important; color:#bbf7d0 !important; font-size:12px !important; max-width:85% !important; white-space:pre-wrap !important }
#msg-input textarea { background:#0d1f0d !important; border:1px solid #1a3a1a !important; border-radius:12px !important; color:#e2e8f0 !important }
#msg-input textarea:focus { border-color:#22c55e !important }
#send-btn  { background:linear-gradient(135deg,#16a34a,#22c55e) !important; border:none !important; border-radius:12px !important; color:#fff !important; font-weight:800 !important; height:48px !important }
#reset-btn { background:transparent !important; border:1px solid #1a3a1a !important; border-radius:12px !important; color:#475569 !important; height:48px !important }
.qr-chip { background:#0d1f0d; border:1px solid #1a3a1a; border-radius:20px; padding:5px 13px;
  font-size:11px; color:#4ade80; cursor:pointer; display:inline-block; margin:3px; transition:all .15s }
.qr-chip:hover { background:#14532d; border-color:#22c55e }
#rides-panel,#map-panel,#payment-panel,#carbon-panel {
  background:#070f09 !important; border:1px solid #1a3a1a !important; border-radius:14px !important; padding:14px !important; min-height:80px !important }
#log-panel { background:#050d07 !important; border:1px solid #1a3a1a !important; border-radius:12px !important;
  font-family:'Space Mono',monospace !important; font-size:.72rem !important; padding:12px !important; color:#4b6650 !important }
.tab-nav button { color:#4b6650 !important; font-weight:700 !important }
.tab-nav button.selected { color:#22c55e !important; border-bottom:2px solid #22c55e !important }
"""

QUICK_REPLIES = ["Hi","Westlands to Karen","CBD to JKIA","Kilimani to Gigiri","1","2","3","YES","NO","MENU","Credits"]

# ─────────────────────────────────────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────────────────────────────────────

with gr.Blocks(css=CSS, title="Go Green — EV Ride Agent") as demo:

    gr.HTML("""
    <div id="gg-header">
      <h1>🌿 Go Green</h1>
      <div class="tagline">AI EV ride ordering · WhatsApp · M-Pesa · Verra VM0038 Carbon Credits</div>
      <div>
        <span class="ev-badge">⚡ Uber Green</span><span class="ev-badge">⚡ Bolt EV</span>
        <span class="ev-badge">⚡ Yego</span><span class="ev-badge">⚡ Faras</span>
        <span class="ev-badge">⚡ Little Cabs</span><span class="ev-badge">⚡ Wasili</span>
        <span class="ev-badge">⚡ Weego</span>
        <span class="ev-badge" style="background:#14532d88;border-color:#22c55e55;color:#86efac">🌿 VM0038 VCUs</span>
      </div>
    </div>""")

    with gr.Row():
        phone_input = gr.Textbox(
            value=DEMO_PHONE, label="📱 WhatsApp Number (M-Pesa registered)",
            placeholder="+254712345678", elem_id="phone-input", scale=1,
        )

    with gr.Row(equal_height=False):

        # ── Left: WhatsApp simulator ──────────────────────────────────────────
        with gr.Column(scale=2):
            gr.HTML("""<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
              <div style="width:9px;height:9px;background:#22c55e;border-radius:50%;box-shadow:0 0 6px #22c55e"></div>
              <span style="font-size:11px;color:#4ade80;font-weight:700">Go Green · WhatsApp Simulator</span>
            </div>""")

            chatbot = gr.Chatbot(
                label="", elem_id="wa-chat", height=440, show_copy_button=False,
                avatar_images=(
                    "https://api.dicebear.com/7.x/thumbs/svg?seed=rider&backgroundColor=14532d",
                    "https://api.dicebear.com/7.x/bottts/svg?seed=gogreen&backgroundColor=166534",
                ),
            )

            gr.HTML(
                '<div style="margin:6px 0 4px;font-size:9px;color:#4b6650;letter-spacing:.5px">QUICK REPLIES</div><div>'
                + "".join(
                    f'<span class="qr-chip" onclick="(()=>{{let t=document.querySelector(\'#msg-input textarea\');'
                    f't.value=\'{r}\';t.dispatchEvent(new Event(\'input\',{{bubbles:true}}));}})();">{r}</span>'
                    for r in QUICK_REPLIES
                ) + "</div>"
            )

            with gr.Row():
                msg_input = gr.Textbox(placeholder="Type your message…", show_label=False, lines=1, elem_id="msg-input", scale=5)
                send_btn  = gr.Button("Send ↑", elem_id="send-btn",  scale=1)
                reset_btn = gr.Button("↺",      elem_id="reset-btn", scale=0)

        # ── Right: Panels ─────────────────────────────────────────────────────
        with gr.Column(scale=3):
            with gr.Tabs():

                with gr.Tab("⚡ Rides"):
                    rides_html = gr.HTML(
                        value='<div style="color:#1a3a1a;padding:40px;text-align:center;font-size:12px">✦ Available EV rides will appear here</div>',
                        elem_id="rides-panel",
                    )

                with gr.Tab("🗺️ Map"):
                    map_html = gr.HTML(
                        value='<div style="color:#1a3a1a;padding:40px;text-align:center;font-size:12px">✦ Route map will appear here</div>',
                        elem_id="map-panel",
                    )

                with gr.Tab("💳 Payment"):
                    payment_html = gr.HTML(
                        value='<div style="color:#1a3a1a;padding:40px;text-align:center;font-size:12px">✦ M-Pesa payment status will appear here</div>',
                        elem_id="payment-panel",
                    )

                with gr.Tab("🌿 Carbon Credits"):
                    carbon_html = gr.HTML(
                        value='<div style="color:#1a3a1a;padding:40px;text-align:center;font-size:12px">'
                              '✦ Verra VM0038 carbon credits will appear after your first confirmed trip</div>',
                        elem_id="carbon-panel",
                    )

            gr.Markdown("#### 🤖 Agent Activity")
            log_md = gr.Markdown(value="_Agents standing by…_", elem_id="log-panel")

    # ── Event wiring ──────────────────────────────────────────────────────────
    outputs = [chatbot, rides_html, map_html, payment_html, carbon_html, log_md]

    send_btn.click(fn=send_message, inputs=[phone_input, msg_input, chatbot],
                   outputs=outputs, show_progress=False).then(fn=lambda: "", outputs=msg_input)

    msg_input.submit(fn=send_message, inputs=[phone_input, msg_input, chatbot],
                     outputs=outputs, show_progress=False).then(fn=lambda: "", outputs=msg_input)

    reset_btn.click(fn=reset_chat, inputs=[phone_input], outputs=outputs)


# ─────────────────────────────────────────────────────────────────────────────
# Launch
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  Set ANTHROPIC_API_KEY before running.")

    threading.Thread(target=_run_flask, daemon=True).start()
    print("✅  Flask webhook  → http://0.0.0.0:5000/api/whatsapp/webhook")
    print("✅  Carbon dashboard (separate) → python carbon_dashboard.py  [port 7861]")

    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False, show_api=False,
    )
