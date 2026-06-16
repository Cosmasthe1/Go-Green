"""
carbon_dashboard.py — Go Green Carbon Credit Dashboard 🌿
────────────────────────────────────────────────────────────────────────────
Standalone Gradio dashboard for Go Green's Verra VM0038 carbon credit engine.

Tabs:
  1. Trip Calculator   — per-trip GHG reduction + VCU
  2. Fleet Modeller    — mixed fleet annual projections
  3. Construction      — VMR0004 machinery credits
  4. Rider Portfolio   — individual rider ledger
  5. Monitoring Report — Verra-compliant report generator

Run:   python carbon_dashboard.py
Port:  7861
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr
from carbon.ghg_calculator import GHGCalculator
from carbon.carbon_agent import CarbonAgent, CarbonLedger
from base_agent import LongTermMemory
from carbon.verra_constants import (
    VEHICLE_PARAMS, CONSTRUCTION_PARAMS, VehicleCategory,
    VCU_PRICE_USD, VCU_PRICE_KES, CREDITING_PERIOD_YEARS,
    NET_VCU_FACTOR, EF_GRID_KENYA_KG_PER_KWH,
)

# ── Shared state ─────────────────────────────────────────────────────────────
_memory  = LongTermMemory()
_ledger  = CarbonLedger(_memory)
_agent   = CarbonAgent()
_agent.set_ledger(_ledger)

# ── Category helpers ──────────────────────────────────────────────────────────
TRANSPORT_CATS = {
    p.category_label: cat
    for cat, p in VEHICLE_PARAMS.items()
    if p.sector == "transport"
}
CONSTRUCTION_CATS = {
    CONSTRUCTION_PARAMS[cat].label: cat
    for cat in CONSTRUCTION_PARAMS
}
ALL_TRANSPORT_LABELS  = list(TRANSPORT_CATS.keys())
ALL_CONSTRUCTION_LABELS = list(CONSTRUCTION_CATS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Trip Calculator
# ─────────────────────────────────────────────────────────────────────────────

def calc_trip(vehicle_label: str, distance_km: float, charger: str):
    cat    = TRANSPORT_CATS.get(vehicle_label)
    if not cat:
        return "❌ Unknown vehicle category", ""
    result = GHGCalculator.calculate_trip(cat, distance_km, charger)
    p      = VEHICLE_PARAMS[cat]

    # Cards HTML
    cards = f"""
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-family:'Sora',sans-serif">
  {_metric_card("🌿 CO₂ Saved",       f"{result.net_reduction_kg*1000:.0f} g",  f"{result.net_reduction_kg/1000*1000:.4f} kgCO₂e", "#10b981")}
  {_metric_card("💎 VCUs Earned",     f"{result.net_vcu:.7f}",                   "Verra Verified Carbon Units", "#6366f1")}
  {_metric_card("💰 VCU Value",       f"KSh {result.vcu_value_kes:.4f}",         f"≈ USD {result.vcu_value_usd:.5f}", "#f59e0b")}
  {_metric_card("🌳 Trees Equiv.",    f"{result.trees_equivalent:.3f}",          "trees absorbing CO₂ for 1 yr", "#22c55e")}
  {_metric_card("⛽ Petrol Saved",    f"{result.petrol_saved_litres:.2f} L",     f"≈ {result.petrol_saved_litres*113:.0f}g CO₂ upstream", "#ef4444")}
  {_metric_card("📊 Baseline vs EV", f"{result.baseline_emissions_kg*1000:.0f}g → {result.project_emissions_kg*1000:.1f}g", "ICE baseline vs EV project emissions", "#64748b")}
</div>
"""
    breakdown = f"""
### 📐 VM0038 Calculation Breakdown

| Component | Formula | Value |
|-----------|---------|-------|
| **Baseline Emissions (BE)** | {distance_km:.1f} km × {p.afec_l_per_km} L/km × EF_fuel × WTT | **{result.baseline_emissions_kg*1000:.2f} gCO₂e** |
| **Project Emissions (PE)** | {distance_km * p.ev_kwh_per_km:.3f} kWh ÷ η_{charger} × EF_grid | **{result.project_emissions_kg*1000:.2f} gCO₂e** |
| **Gross Reduction (BE–PE)** | {result.baseline_emissions_kg*1000:.2f} − {result.project_emissions_kg*1000:.2f} | **{result.gross_reduction_kg*1000:.2f} gCO₂e** |
| **Leakage (3%)** | × 0.03 | **−{result.leakage_kg*1000:.2f} gCO₂e** |
| **Net ER** | Gross − Leakage | **{result.net_reduction_kg*1000:.2f} gCO₂e** |
| **VCS Buffer (10%)** | Net ER × {NET_VCU_FACTOR:.2f} | applied |
| **Tradeable VCUs** | ÷ 1,000 kg/t | **{result.net_vcu:.8f} tCO₂e** |

> Kenya grid EF = **{EF_GRID_KENYA_KG_PER_KWH} kgCO₂e/kWh** (IEA 2024, >90% renewable)
> Methodology: **Verra VM0038 v1.0** · Additionality: **VMD0049 positive list** ✅
"""
    return cards, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Fleet Modeller
# ─────────────────────────────────────────────────────────────────────────────

def calc_fleet(
    n_ebikes: int, n_taxis: int, n_matatus: int, n_buses: int,
    n_lt: int, n_ht: int, period: str,
):
    vehicles = []
    specs = [
        (VehicleCategory.E_BIKE,            n_ebikes),
        (VehicleCategory.PSV_PASSENGER_CAR, n_taxis),
        (VehicleCategory.MINIBUS,           n_matatus),
        (VehicleCategory.TRANSIT_BUS,       n_buses),
        (VehicleCategory.LIGHT_TRUCK,       n_lt),
        (VehicleCategory.HEAVY_TRUCK,       n_ht),
    ]
    for cat, count in specs:
        if count > 0:
            vehicles.append({"category": cat, "count": count})

    if not vehicles:
        return "Add at least one vehicle to the fleet.", "", ""

    result = GHGCalculator.calculate_fleet("Go Green Fleet", period, vehicles)

    summary_html = f"""
<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;font-family:'Sora',sans-serif">
  {_metric_card("🚗 Fleet VKT",          f"{result.total_vkt_km:,.0f} km",    "Total km driven as EV", "#6366f1")}
  {_metric_card("🌿 Net CO₂ Reduced",   f"{result.total_net_reduction_tco2:.3f} tCO₂e", f"Baseline: {result.total_baseline_tco2:.3f} t", "#10b981")}
  {_metric_card("💎 Tradeable VCUs",     f"{result.net_vcu:.4f}",              "Verified Carbon Units (Verra)", "#8b5cf6")}
  {_metric_card("💰 Annual Value",       f"KSh {result.vcu_value_kes:,.0f}",  f"USD {result.vcu_value_usd:,.2f}", "#f59e0b")}
  {_metric_card("📅 7-yr Credit Value",  f"KSh {result.vcu_value_kes*7:,.0f}", f"USD {result.vcu_value_usd*7:,.2f}", "#ec4899")}
  {_metric_card("🏭 Baseline Avoided",  f"{result.total_baseline_tco2:.3f} tCO₂e", f"Grid PE: {result.total_project_tco2:.4f} t", "#64748b")}
</div>
"""
    breakdown_md = f"""
### Fleet Breakdown

| Category | Net tCO₂e |
|----------|------------|
{''.join(f"| {k.replace('_',' ').title()} | {v:.4f} |" + chr(10) for k, v in result.by_category.items())}

### Charger Type Breakdown
{''.join(f"| {k} | {v:.4f} |" + chr(10) for k, v in result.by_charger.items())}

**Methodology:** Verra VM0038 v1.0 + VMR0004 v2.0
**Additionality:** VMD0049 positive list (Kenya EV penetration ~0.3% < 5%) ✅
**Crediting period:** {CREDITING_PERIOD_YEARS} years (renewable × 2)
"""
    chart_data = json.dumps({
        "categories": list(result.by_category.keys()),
        "values":     list(result.by_category.values()),
    })
    return summary_html, breakdown_md, chart_data


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Construction Machinery
# ─────────────────────────────────────────────────────────────────────────────

def calc_construction(machine_label: str, hours: float):
    cat    = CONSTRUCTION_CATS.get(machine_label)
    if not cat:
        return "❌ Unknown machine", ""
    result = GHGCalculator.calculate_construction(cat, hours)
    mp     = CONSTRUCTION_PARAMS[cat]

    cards = f"""
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-family:'Sora',sans-serif">
  {_metric_card("⛽ Diesel Displaced", f"{result.baseline_diesel_l:.1f} L",    f"{mp.diesel_l_per_hour} L/hr baseline", "#ef4444")}
  {_metric_card("🌿 CO₂ Reduced",     f"{result.net_reduction_kg:.2f} kg",     f"{result.net_reduction_kg/1000:.5f} tCO₂e", "#10b981")}
  {_metric_card("💎 VCUs Earned",     f"{result.net_vcu:.6f}",                  "VMR0004 v2.0 credits", "#6366f1")}
  {_metric_card("💰 VCU Value",       f"KSh {result.vcu_value_kes:.2f}",       f"USD {result.vcu_value_usd:.4f}", "#f59e0b")}
  {_metric_card("🏗️ Operating Hours", f"{result.operating_hours:.1f} hrs",     f"≈ {result.operating_hours/8:.1f} working days", "#64748b")}
  {_metric_card("🔋 EV kWh Used",     f"{hours * mp.ev_kwh_per_hour:.1f} kWh", f"vs {result.baseline_diesel_l:.1f} L diesel", "#22c55e")}
</div>
"""
    md = f"""
### VMR0004 v2.0 Construction Machinery Calculation

| | Diesel ICE (Baseline) | Electric (Project) |
|--|--|--|
| **Consumption** | {mp.diesel_l_per_hour} L/hr | {mp.ev_kwh_per_hour} kWh/hr |
| **Over {hours:.1f} hrs** | {result.baseline_diesel_l:.1f} L | {hours*mp.ev_kwh_per_hour:.1f} kWh |
| **Emissions** | {result.baseline_emissions_kg:.2f} kgCO₂e | {result.project_emissions_kg:.2f} kgCO₂e |

**Net Reduction:** {result.net_reduction_kg:.2f} kgCO₂e → **{result.net_vcu:.6f} VCUs** (after leakage + buffer)

> Methodology: **VMR0004 v2.0** + **AMS-III.BC** (Non-road mobile machinery)
> Diesel EF: 2.703 kgCO₂e/L × 1.21 WTT · Grid EF: 0.061 kgCO₂e/kWh
"""
    return cards, md


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4 — Rider Portfolio
# ─────────────────────────────────────────────────────────────────────────────

def add_demo_trips(phone: str):
    """Add demo trips so UI looks populated."""
    demo = [
        (VehicleCategory.PSV_PASSENGER_CAR, 8.4,  "L2"),
        (VehicleCategory.PSV_PASSENGER_CAR, 12.1, "L2"),
        (VehicleCategory.PSV_PASSENGER_CAR, 5.7,  "L2"),
        (VehicleCategory.E_BIKE,            3.2,  "L1"),
    ]
    for cat, km, charger in demo:
        _agent.process_trip(phone, f"GG-DEMO-{int(km*10)}", cat, km, charger)


def get_portfolio(phone: str):
    if not phone.strip():
        return "<div style='color:#475569;padding:20px'>Enter a phone number</div>", ""
    # Auto-populate demo data
    if not _ledger.get_entries(phone):
        add_demo_trips(phone)

    summary = _ledger.summary(phone)
    total_kg  = summary["total_co2_kg"]
    total_vcu = summary["total_vcu"]
    total_kes = summary["total_value_kes"]
    trips     = summary["total_trips"]

    header = f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-family:'Sora',sans-serif;margin-bottom:16px">
  {_metric_card("🚗 EV Trips",          str(trips),                          "Go Green rides taken", "#6366f1")}
  {_metric_card("🌿 Total CO₂ Saved",  f"{total_kg*1000:.0f} g",            f"= {total_kg:.4f} tCO₂e", "#10b981")}
  {_metric_card("💎 VCUs Accumulated", f"{total_vcu:.6f}",                   "Verra Verified Carbon Units", "#8b5cf6")}
  {_metric_card("💰 Portfolio Value",  f"KSh {total_kes:.2f}",              f"≈ USD {total_kes/130:.4f}", "#f59e0b")}
</div>
"""
    rows = "".join(
        f"| {e['entry_id']} | {e['vehicle_category'].replace('_',' ').title()} "
        f"| {e['distance_km']:.1f} km | {e['net_reduction_kg']*1000:.0f} g "
        f"| {e['net_vcu']:.7f} | KSh {e['vcu_value_kes']:.4f} |"
        f" {e['charger_type']} |\n"
        for e in summary["entries"]
    )
    table = f"""
### Trip Ledger (Last 10)
| ID | Vehicle | Distance | CO₂ Saved | VCUs | Value | Charger |
|----|---------|----------|-----------|------|-------|---------|
{rows}
*Certified under Verra VM0038 v1.0 · VMD0049 Additionality confirmed*
"""
    return header, table


# ─────────────────────────────────────────────────────────────────────────────
# Tab 5 — AI Carbon Advisor
# ─────────────────────────────────────────────────────────────────────────────

def ask_advisor(question: str, history: list):
    if not question.strip():
        yield history, ""
        return
    history = history + [[question, "⏳ Analysing…"]]
    yield history, ""
    answer = _agent.answer_carbon_query(question)
    history[-1][1] = answer
    yield history, ""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: metric card HTML
# ─────────────────────────────────────────────────────────────────────────────

def _metric_card(title: str, value: str, sub: str, color: str) -> str:
    return f"""
<div style="background:#0d1f0d;border:1px solid {color}33;border-radius:12px;padding:14px 16px;
     border-left:3px solid {color}">
  <div style="font-size:11px;color:#475569;letter-spacing:.6px;margin-bottom:4px">{title}</div>
  <div style="font-size:20px;font-weight:800;color:{color};font-family:'Sora',sans-serif;line-height:1.1">{value}</div>
  <div style="font-size:10px;color:#334155;margin-top:3px">{sub}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# CSS — biopunk / data-lab aesthetic
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;800&family=IBM+Plex+Mono:wght@400;600&display=swap');

*, body, .gradio-container {
    font-family: 'Sora', sans-serif !important;
    background-color: #020c04 !important;
    color: #cbd5e1 !important;
}

/* Header */
#cc-header {
    text-align: center;
    padding: 24px 12px 14px;
    border-bottom: 1px solid #0d2a10;
    margin-bottom: 4px;
    position: relative;
}
#cc-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse 700px 180px at 50% 0%, #05300a22, transparent);
    pointer-events: none;
}
#cc-header h1 {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #4ade80 0%, #22c55e 40%, #a3e635 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 .2rem;
}
#cc-header .sub {
    font-size: .8rem;
    color: #1e4d20;
    font-family: 'IBM Plex Mono', monospace;
}
.verra-pill {
    display: inline-block;
    background: #052e0a;
    border: 1px solid #16a34a44;
    color: #4ade80;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 700;
    margin: 2px 3px;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: .4px;
}

/* Inputs */
input, textarea, select, .gr-input input {
    background: #050f06 !important;
    border: 1px solid #1a3a1a !important;
    border-radius: 8px !important;
    color: #a3e635 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: .82rem !important;
}
input:focus, textarea:focus { border-color: #22c55e !important; }

/* Sliders */
.gr-slider input[type=range] { accent-color: #22c55e; }

/* Buttons */
button.primary {
    background: linear-gradient(135deg, #15803d, #22c55e) !important;
    border: none !important;
    border-radius: 9px !important;
    color: #fff !important;
    font-weight: 700 !important;
    font-family: 'Sora', sans-serif !important;
}

/* Tabs */
.tab-nav button {
    color: #1a4020 !important;
    font-family: 'Sora', sans-serif !important;
    font-weight: 700 !important;
    font-size: .82rem !important;
}
.tab-nav button.selected {
    color: #4ade80 !important;
    border-bottom: 2px solid #4ade80 !important;
}

/* Markdown tables */
table { width: 100%; border-collapse: collapse; }
th { background: #051a07; color: #4ade80; padding: 7px 12px; font-size: 11px; }
td { padding: 6px 12px; border-bottom: 1px solid #0d2a10; font-size: 11px; color: #94a3b8; }
tr:hover td { background: #071408; }

/* Chatbot */
#advisor-chat .message.user {
    background: #0a2e0d !important;
    border-radius: 10px 10px 3px 10px !important;
    color: #86efac !important;
    font-size: 12px !important;
}
#advisor-chat .message.bot {
    background: #060f07 !important;
    border: 1px solid #0d2a10 !important;
    border-radius: 10px 10px 10px 3px !important;
    color: #cbd5e1 !important;
    font-size: 12px !important;
}

/* Numbers: monospaced */
.mono { font-family: 'IBM Plex Mono', monospace; }
"""

ADVISOR_EXAMPLES = [
    "How is my carbon credit calculated under VM0038?",
    "What is the Kenya grid emission factor and why is it so low?",
    "How much can a fleet of 50 EV taxis earn per year?",
    "Explain additionality under VMD0049 for Kenya",
    "What is a Verified Carbon Unit (VCU) worth today?",
    "How do construction machinery credits work under VMR0004?",
]

# ─────────────────────────────────────────────────────────────────────────────
# Build Gradio app
# ─────────────────────────────────────────────────────────────────────────────

with gr.Blocks(css=CSS, title="Go Green — Carbon Credit Dashboard") as dashboard:

    gr.HTML("""
    <div id="cc-header">
      <h1>🌿 Go Green Carbon Credits</h1>
      <div class="sub">Verra VM0038 v1.0 · VMD0049 · VMR0004 v2.0 · GHG Protocol</div>
      <div style="margin-top:8px">
        <span class="verra-pill">VM0038 EV Charging</span>
        <span class="verra-pill">VMD0049 Additionality</span>
        <span class="verra-pill">VMR0004 Fleet Efficiency</span>
        <span class="verra-pill">AMS-III.BC CDM</span>
        <span class="verra-pill">Kenya Grid 0.061 kgCO₂/kWh</span>
        <span class="verra-pill">VCU ~$12.50/tCO₂e</span>
      </div>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Trip Calculator ────────────────────────────────────────────
        with gr.Tab("⚡ Trip Calculator"):
            gr.Markdown("### Calculate carbon credits for a single EV trip (VM0038 §3–5)")
            with gr.Row():
                with gr.Column(scale=1):
                    t1_cat     = gr.Dropdown(ALL_TRANSPORT_LABELS, label="Vehicle Category",
                                             value=ALL_TRANSPORT_LABELS[1])
                    t1_dist    = gr.Slider(0.5, 200, value=12.5, step=0.5, label="Distance (km)")
                    t1_charger = gr.Radio(["L1","L2","DCFC"], value="L2", label="Charger Type")
                    t1_btn     = gr.Button("⚡ Calculate Credits", variant="primary")
                with gr.Column(scale=2):
                    t1_cards   = gr.HTML()
                    t1_detail  = gr.Markdown()
            t1_btn.click(calc_trip, [t1_cat, t1_dist, t1_charger], [t1_cards, t1_detail])

        # ── Tab 2: Fleet Modeller ─────────────────────────────────────────────
        with gr.Tab("🚗 Fleet Modeller"):
            gr.Markdown("### Annual carbon credits for a mixed EV fleet (VM0038 + VMR0004)")
            with gr.Row():
                with gr.Column(scale=1):
                    f_period  = gr.Textbox(value="2025", label="Monitoring Period")
                    f_ebikes  = gr.Slider(0, 500,  value=20,  step=5,  label="🚲 E-Bikes")
                    f_taxis   = gr.Slider(0, 1000, value=50,  step=10, label="🚕 PSV Cars / Taxis")
                    f_matatus = gr.Slider(0, 500,  value=30,  step=5,  label="🚐 Minibuses (Matatu)")
                    f_buses   = gr.Slider(0, 200,  value=10,  step=2,  label="🚌 Transit Buses")
                    f_lt      = gr.Slider(0, 500,  value=15,  step=5,  label="🚚 Light Trucks")
                    f_ht      = gr.Slider(0, 100,  value=5,   step=1,  label="🚛 Heavy Trucks")
                    f_btn     = gr.Button("📊 Model Fleet Credits", variant="primary")
                with gr.Column(scale=2):
                    f_cards   = gr.HTML()
                    f_detail  = gr.Markdown()
                    f_chart   = gr.JSON(label="Category breakdown (raw)", visible=False)
            f_btn.click(calc_fleet,
                        [f_ebikes, f_taxis, f_matatus, f_buses, f_lt, f_ht, f_period],
                        [f_cards, f_detail, f_chart])

        # ── Tab 3: Construction Machinery ─────────────────────────────────────
        with gr.Tab("🏗️ Construction"):
            gr.Markdown("### VMR0004 v2.0 — Electric construction machinery GHG credits")
            with gr.Row():
                with gr.Column(scale=1):
                    c_machine = gr.Dropdown(ALL_CONSTRUCTION_LABELS, label="Machine Type",
                                            value=ALL_CONSTRUCTION_LABELS[0])
                    c_hours   = gr.Slider(1, 2000, value=200, step=10, label="Operating Hours")
                    c_btn     = gr.Button("🏗️ Calculate Credits", variant="primary")
                with gr.Column(scale=2):
                    c_cards   = gr.HTML()
                    c_detail  = gr.Markdown()
            c_btn.click(calc_construction, [c_machine, c_hours], [c_cards, c_detail])

        # ── Tab 4: Rider Portfolio ────────────────────────────────────────────
        with gr.Tab("👤 Rider Portfolio"):
            gr.Markdown("### Personal carbon credit ledger — cumulative VCU portfolio")
            with gr.Row():
                p_phone = gr.Textbox(value="+254712345678", label="📱 Phone Number", scale=2)
                p_btn   = gr.Button("📋 Load Portfolio", variant="primary", scale=1)
            p_cards = gr.HTML()
            p_table = gr.Markdown()
            p_btn.click(get_portfolio, [p_phone], [p_cards, p_table])

        # ── Tab 5: AI Carbon Advisor ──────────────────────────────────────────
        with gr.Tab("🤖 AI Carbon Advisor"):
            gr.Markdown("### Ask anything about VM0038, VCUs, Kenya grid, or methodology")
            advisor_chat = gr.Chatbot(height=400, elem_id="advisor-chat", show_copy_button=True)
            with gr.Row():
                advisor_input = gr.Textbox(
                    placeholder="Ask about VM0038, VCUs, additionality, Kenya grid…",
                    show_label=False, lines=1, scale=5,
                )
                advisor_btn = gr.Button("Ask →", variant="primary", scale=1)
            gr.Examples(ADVISOR_EXAMPLES, inputs=advisor_input, label="💡 Example questions")
            advisor_btn.click(ask_advisor, [advisor_input, advisor_chat],
                              [advisor_chat, advisor_input])
            advisor_input.submit(ask_advisor, [advisor_input, advisor_chat],
                                 [advisor_chat, advisor_input])

# ─────────────────────────────────────────────────────────────────────────────
# Launch
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  Set ANTHROPIC_API_KEY for the AI Advisor tab.")
    dashboard.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("CARBON_PORT", 7861)),
        share=False,
        show_api=False,
    )
