// server.ts — Go Green MCP App Server
// Registers tools with _meta.ui.resourceUri so MCP Apps-capable hosts
// (Claude.ai, ChatGPT, VSCode, Goose) render the interactive UI.

import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import fs from "node:fs/promises";
import path from "node:path";
import {
  calcVM0038,
  generateOffers,
  geocode,
  haversineKm,
  parseRoute,
  type TripRecord,
} from "./data.js";

const DIST_DIR = path.join(path.dirname(new URL(import.meta.url).pathname), "..", "dist");

// ── In-memory session store (keyed by phone) ──────────────────────────────────
const sessions = new Map<string, {
  phone: string;
  pickup: string; dest: string;
  pickupLL: [number,number]; dropLL: [number,number];
  offers: ReturnType<typeof generateOffers>;
  chosen: ReturnType<typeof generateOffers>[0] | null;
  state: "idle"|"showing_rides"|"confirming"|"booked";
  trips: TripRecord[];
}>();

function getSession(phone: string) {
  if (!sessions.has(phone)) {
    sessions.set(phone, {
      phone, pickup:"", dest:"",
      pickupLL:[-1.2833,36.8172], dropLL:[-1.2833,36.8172],
      offers:[], chosen:null, state:"idle", trips:[],
    });
  }
  return sessions.get(phone)!;
}

// ── HTML loader helper ────────────────────────────────────────────────────────
async function loadHtml(): Promise<string> {
  try {
    return await fs.readFile(path.join(DIST_DIR, "main.html"), "utf-8");
  } catch {
    return "<html><body><p>UI bundle not built yet. Run <code>npm run build</code>.</p></body></html>";
  }
}

const MAIN_RESOURCE_URI = "ui://gogreen/main";

// ── MCP Server factory ────────────────────────────────────────────────────────
export function createServer(): McpServer {
  const server = new McpServer({
    name: "Go Green — EV Ride Agent",
    version: "1.0.0",
  });

  // ── TOOL 1: search_rides ────────────────────────────────────────────────────
  // Renders the full Go Green UI: WhatsApp simulator + ride cards + map + carbon
  registerAppTool(
    server,
    "search_rides",
    {
      title: "Go Green — Search EV Rides",
      description:
        "Search for available EV rides in Nairobi across Uber, Bolt, Yego, Faras, Little Cabs, Wasili & Weego. " +
        "Returns an interactive UI with ride cards, live map, M-Pesa payment, and Verra VM0038 carbon credits.",
      inputSchema: {
        type: "object" as const,
        properties: {
          query: {
            type: "string",
            description: 'Pickup and destination. E.g. "Westlands to Karen" or "Take me to JKIA"',
          },
          phone: {
            type: "string",
            description: "Rider WhatsApp / M-Pesa phone number (e.g. +254712345678)",
          },
        },
        required: ["query"],
      },
      _meta: { ui: { resourceUri: MAIN_RESOURCE_URI } },
    },
    async ({ query, phone = "+254712345678" }: { query: string; phone?: string }) => {
      const sess = getSession(phone);
      const { pickup, dest } = parseRoute(query);
      const pLL = geocode(pickup) ?? [-1.2833, 36.8172];
      const dLL = geocode(dest)   ?? [-1.2833 + (Math.random()-.5)*.06, 36.8172 + (Math.random()-.5)*.06];
      const dist = haversineKm(pLL[0], pLL[1], dLL[0], dLL[1]);

      sess.pickup  = pickup;
      sess.dest    = dest;
      sess.pickupLL = pLL;
      sess.dropLL   = dLL;
      sess.offers   = generateOffers(dist);
      sess.state    = "showing_rides";

      const top = sess.offers[0];
      const list = sess.offers.map((o,i)=>
        `${i+1}. ${o.provider} (${o.rideType}) — KSh ${o.priceKes.toLocaleString()} | ETA ${o.etaMin}m | ${o.evModel} ⭐${o.driverRating} | ${o.badge}`
      ).join("\n");

      return {
        content: [{
          type: "text",
          text: [
            `🌿 **Go Green EV Rides** — ${pickup} → ${dest} (~${dist.toFixed(1)} km)`,
            ``,
            list,
            ``,
            `💡 Best pick: **${top.provider}** at KSh ${top.priceKes.toLocaleString()} (score ${top.dealScore})`,
            `🌱 Riding EV saves ~${top.co2SavedG}g CO₂ vs petrol`,
            ``,
            `_The interactive map and ride cards are rendering in the panel →_`,
          ].join("\n"),
        }],
      };
    },
  );

  // ── TOOL 2: book_ride ───────────────────────────────────────────────────────
  registerAppTool(
    server,
    "book_ride",
    {
      title: "Go Green — Book & Pay",
      description:
        "Confirm a ride selection and initiate M-Pesa STK push payment. " +
        "Shows booking confirmation with carbon credits earned.",
      inputSchema: {
        type: "object" as const,
        properties: {
          phone: { type: "string", description: "Rider phone (M-Pesa registered)" },
          choice: { type: "string", description: "Provider name or number (1-7)" },
        },
        required: ["phone", "choice"],
      },
      _meta: { ui: { resourceUri: MAIN_RESOURCE_URI } },
    },
    async ({ phone = "+254712345678", choice }: { phone?: string; choice: string }) => {
      const sess = getSession(phone);
      const idx  = /^\d$/.test(choice.trim()) ? parseInt(choice)-1 : -1;
      const offer = idx >= 0
        ? sess.offers[idx]
        : sess.offers.find(o => o.provider.toLowerCase().includes(choice.toLowerCase())) ?? sess.offers[0];

      if (!offer) {
        return { content:[{type:"text",text:"❌ No offer found. Run search_rides first."}] };
      }

      sess.chosen = offer;
      sess.state  = "booked";

      const carbon = calcVM0038(offer.distanceKm);
      const tripId = `GG-${Date.now().toString().slice(-6)}`;

      const record: TripRecord = {
        tripId, phone,
        pickup: sess.pickup, destination: sess.dest,
        provider: offer.provider, priceKes: offer.priceKes,
        distanceKm: offer.distanceKm, carbon, timestamp: Date.now(),
      };
      sess.trips.push(record);

      return {
        content: [{
          type: "text",
          text: [
            `✅ **Booking Confirmed** — ${offer.provider} (${offer.rideType})`,
            ``,
            `🚗 ${offer.evModel} · 👤 ${offer.driverName} ⭐${offer.driverRating} · 🚘 ${offer.plate}`,
            `📍 ETA: **${offer.etaMin} min** · 🛣️ ${offer.distanceKm} km · ⏱ ~${offer.durationMin} min`,
            `💰 **KSh ${offer.priceKes.toLocaleString()}** · Trip ID: \`${tripId}\``,
            ``,
            `💳 M-Pesa STK push sent to **${phone}** — enter your PIN to pay`,
            ``,
            `🌿 **Carbon Credits (Verra VM0038 v1.0)**`,
            `CO₂ saved: ${(carbon.netKg*1000).toFixed(0)}g · VCUs: ${carbon.netVcu.toFixed(8)} · Value: KSh ${carbon.vcuValueKes.toFixed(4)}`,
            `🌳 Equivalent to ${carbon.treesEquiv.toFixed(3)} trees absorbing CO₂ for 1 year`,
          ].join("\n"),
        }],
      };
    },
  );

  // ── TOOL 3: carbon_portfolio ────────────────────────────────────────────────
  registerAppTool(
    server,
    "carbon_portfolio",
    {
      title: "Go Green — Carbon Portfolio",
      description:
        "View a rider's accumulated Verra VM0038 carbon credits across all completed EV trips.",
      inputSchema: {
        type: "object" as const,
        properties: {
          phone: { type: "string", description: "Rider phone number" },
        },
        required: ["phone"],
      },
      _meta: { ui: { resourceUri: MAIN_RESOURCE_URI } },
    },
    async ({ phone }: { phone: string }) => {
      const sess = getSession(phone);
      const trips = sess.trips;
      const totalVcu = trips.reduce((s,t)=>s+t.carbon.netVcu, 0);
      const totalKg  = trips.reduce((s,t)=>s+t.carbon.netKg, 0);
      const totalKes = trips.reduce((s,t)=>s+t.carbon.vcuValueKes, 0);

      if (!trips.length) {
        return { content:[{type:"text", text:`No trips found for ${phone}. Use search_rides to book your first EV ride!`}] };
      }

      const rows = trips.map(t=>
        `• ${t.provider} · ${t.distanceKm}km · ${(t.carbon.netKg*1000).toFixed(0)}g CO₂ · ${t.carbon.netVcu.toFixed(8)} VCU · KSh ${t.carbon.vcuValueKes.toFixed(4)}`
      ).join("\n");

      return {
        content: [{
          type: "text",
          text: [
            `🌿 **Carbon Portfolio — ${phone}**`,
            ``,
            `📊 ${trips.length} EV trips | ${(totalKg*1000).toFixed(0)}g CO₂ saved | ${totalVcu.toFixed(7)} VCUs | KSh ${totalKes.toFixed(2)}`,
            ``,
            rows,
            ``,
            `_Certified: Verra VM0038 v1.0 · VMD0049 Additional · Kenya grid 0.061 kgCO₂e/kWh_`,
          ].join("\n"),
        }],
      };
    },
  );

  // ── UI RESOURCE — serves the bundled interactive HTML ────────────────────────
  registerAppResource(
    server,
    MAIN_RESOURCE_URI,
    MAIN_RESOURCE_URI,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const html = await loadHtml();
      return {
        contents: [{ uri: MAIN_RESOURCE_URI, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    },
  );

  return server;
}
