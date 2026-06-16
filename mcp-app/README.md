# 🌿 Go Green — MCP App

> **EV ride ordering agent built as a first-class MCP App.**
> Renders a rich interactive UI directly inside Claude.ai, ChatGPT, VS Code, and Goose — no separate web server needed.

---

## What Is This?

Go Green is an **MCP App** — a Model Context Protocol server that returns interactive UI resources alongside its tool results. When you ask Claude to "book an EV ride", the agent doesn't just reply with text. It renders a full interface: a WhatsApp-style conversation panel, live ride cards from 7 providers, a Leaflet map of the route, an M-Pesa payment flow, and a real-time Verra VM0038 carbon credit dashboard.

This follows the official [MCP Apps extension](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) (`@modelcontextprotocol/ext-apps`), which is supported in Claude.ai, ChatGPT, VS Code Insiders, and Goose.

---

## Quick Start

```bash
# 1. Install
npm install

# 2. Build the UI bundle (Vite → single HTML file)
npm run build

# 3. Start the MCP server
npm start
# → MCP server: http://localhost:3001/mcp
```

**Connect to Claude.ai:** Settings → Integrations → Add MCP Server → `http://localhost:3001/mcp`

**Connect to Claude Desktop:** add to `claude_desktop_config.json` (see file in repo).

---

## File Structure

```
gogreen-mcp/
├── src/
│   ├── data.ts          # Shared data layer: providers, VM0038 constants, pure calculations
│   ├── server.ts        # MCP server: tools + UI resource registration
│   ├── main.ts          # Entry point: HTTP (Streamable) + stdio transports
│   └── views/
│       └── main.html    # Full interactive MCP App UI (WhatsApp + rides + map + carbon)
├── dist/                # Built output (after npm run build)
│   └── main.html        # Vite-bundled single-file UI
├── package.json
├── tsconfig.json
├── tsconfig.server.json
├── vite.config.ts
└── claude_desktop_config.json
```

---

## MCP Tools

### `search_rides`
Search for EV rides across all 7 providers. Triggers the interactive UI.

```
"Find me an EV ride from Westlands to Karen"
"Book a green cab to JKIA"
```

### `book_ride`
Confirm a provider and initiate M-Pesa STK Push payment.

```
"Book the Bolt option"
"Confirm ride number 2"
```

### `carbon_portfolio`
View accumulated Verra VM0038 carbon credits.

```
"Show my carbon credits"
"What's my Go Green carbon portfolio?"
```

---

## The Interactive UI

The MCP App UI renders in a sandboxed iframe inside the host client. It has three columns:

**Left — WhatsApp Simulator**
Full conversation interface with message bubbles, quick-reply chips, and real-time typing indicators. Mirrors the WhatsApp UX riders actually use.

**Centre — Rides / Map / Payment (tabbed)**
- **Rides tab:** branded provider cards with deal score bar, ETA, EV model, driver rating, promo codes, and a one-tap Book button
- **Map tab:** dark-themed Leaflet.js map (CartoDB Dark Matter tiles) with pickup/drop markers and a dashed green route line
- **Payment tab:** M-Pesa STK Push status flow — booking confirmation → phone prompt → payment receipt

**Right — Carbon Credits**
Live Verra VM0038 calculation panel:
- Per-trip metrics: CO₂ saved, VCUs earned, KES value, trees equivalent
- VM0038 formula breakdown (BE / PE / Net ER)
- Cumulative portfolio across all trips
- Verra certification badge

---

## EV Provider Network

| Provider | Region | EV Models | Rate |
|---|---|---|---|
| Uber Green | Global | Tesla Model 3, Nissan Leaf | KSh 55/km |
| Bolt EV | Global | BYD Atto 3, MG ZS EV | KSh 42/km |
| Yego EV | Africa | Hyundai IONIQ 5, BYD Dolphin | KSh 48/km |
| Faras Green | Africa | VW ID.4, MG4 EV | KSh 40/km |
| Little Cabs EV | Africa | Nissan Leaf, BYD e6 | KSh 45/km |
| Wasili EV | Africa | BYD Atto 3, Great Wall ORA | KSh 38/km |
| Weego EV | Africa | BYD Yuan Plus, Geely C | KSh 44/km |

---

## Carbon Credit Methodology

Every trip runs the **Verra VM0038 v1.0** formula automatically:

```
BE  = distance × AFEC × EF_petrol × WTT        (ICE baseline)
PE  = (kWh / η_L2) × EF_grid                   (EV project)
ER  = BE − PE − 3% leakage                      (net reduction)
VCU = ER × 0.90 / 1000                          (after VCS buffer)
```

Kenya grid EF = **0.061 kgCO₂e/kWh** (IEA 2024, >90% renewable).
Additionality confirmed under **VMD0049** (Kenya EV penetration ~0.3% < 5%).

---

## Connecting to Clients

### Claude.ai
1. Settings → Integrations → Add custom integration
2. Server URL: `http://localhost:3001/mcp`
3. Ask: *"Book me an EV ride from Westlands to Karen"*

### Claude Desktop
Copy `claude_desktop_config.json` contents into:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Update `PATH_TO` to point to your project directory, then restart Claude Desktop.

### VS Code Insiders
Add to `.vscode/mcp.json`:
```json
{
  "servers": {
    "gogreen": {
      "type": "http",
      "url": "http://localhost:3001/mcp"
    }
  }
}
```

### Goose
```yaml
extensions:
  gogreen:
    type: streamable_http
    uri: http://localhost:3001/mcp
```

---

## Development

```bash
# Watch mode (rebuilds UI + restarts server on changes)
npm start

# Production build
npm run build:prod

# stdio mode (for Claude Desktop)
node dist/main.js --stdio
```

The Vite build bundles `src/views/main.html` into a single self-contained `dist/main.html` with all JS/CSS inlined — no CDN dependencies at runtime (except Leaflet loaded from unpkg).

---

## References

- [MCP Apps specification](https://modelcontextprotocol.io/docs/extensions/apps)
- [ext-apps SDK](https://github.com/modelcontextprotocol/ext-apps)
- [Verra VM0038 v1.0](https://verra.org/methodologies/vm0038-methodology-for-electric-vehicle-charging-systems-v1-0/)
- [VMD0049 Additionality](https://verra.org/wp-content/uploads/2022/06/VMD0049-v1.0.pdf)
- [IEA Emission Factors 2024](https://www.iea.org/data-and-statistics/data-product/emissions-factors-2024)
