/**
 * src/services/api.ts — Go Green Rider App
 * ─────────────────────────────────────────────────────────────────────────────
 * HTTP client for the Go Green backend (Flask server on port 5000)
 * WebSocket client for real-time trip status updates
 * WhatsApp channel sync — mirrors the WhatsApp conversation state into the app
 */

// ── Config ────────────────────────────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
const WS_URL   = import.meta.env.VITE_WS_URL       || 'ws://localhost:5000/ws';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface RideOffer {
  provider:      string;
  provider_slug: string;
  ride_type:     string;
  ev_model:      string;
  color:         string;
  distance_km:   number;
  price_kes:     number;
  eta_min:       number;
  duration_min:  number;
  driver_name:   string;
  driver_rating: number;
  driver_phone:  string;
  plate:         string;
  co2_saved_g:   number;
  surge:         number;
  promo_code:    string;
  deal_score:    number;
  badge:         string;
  booking_url:   string;
  data_source:   string;
}

export interface SearchResult {
  pickup:      string;
  destination: string;
  pickup_lat:  number;
  pickup_lon:  number;
  drop_lat:    number;
  drop_lon:    number;
  offers:      RideOffer[];
  log:         AgentStep[];
}

export interface AgentStep {
  agent:     string;
  task:      string;
  status:    'running' | 'done' | 'error';
  result:    string;
  timestamp: number;
}

export interface CarbonResult {
  distance_km:          number;
  baseline_emissions_kg: number;
  project_emissions_kg:  number;
  net_reduction_kg:      number;
  net_vcu:               number;
  vcu_value_kes:         number;
  trees_equivalent:      number;
  petrol_saved_litres:   number;
  methodology:           string;
}

export interface BookingResult {
  success:         boolean;
  trip_id:         string;
  request_id:      string;
  status:          string;
  customer_msg:    string;
  driver_name:     string;
  driver_phone:    string;
  plate:           string;
  ev_model:        string;
  carbon_result?:  CarbonResult;
  error?:          string;
}

export interface TripStatus {
  request_id:    string;
  status:        string;
  driver_name:   string;
  driver_phone:  string;
  driver_rating: number;
  plate:         string;
  ev_model:      string;
  eta_min:       number;
}

export interface PortfolioSummary {
  phone:        string;
  total_trips:  number;
  total_vcu:    number;
  total_co2_kg: number;
  total_value_kes: number;
  entries:      CarbonLedgerEntry[];
}

export interface CarbonLedgerEntry {
  entry_id:         string;
  trip_id:          string;
  distance_km:      number;
  net_vcu:          number;
  vcu_value_kes:    number;
  net_reduction_kg: number;
  timestamp:        number;
  vehicle_category: string;
  charger_type:     string;
}

export interface WhatsAppMessage {
  id:        string;
  role:      'user' | 'bot';
  text:      string;
  timestamp: number;
  offers?:   RideOffer[];
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

async function post<T>(path: string, body: object): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {

  // Search for EV rides on a route
  searchRides: (phone: string, query: string) =>
    post<SearchResult>('/api/rides/search', { phone, query }),

  // Book a chosen ride + initiate M-Pesa STK push
  bookRide: (phone: string, provider: string, offer: RideOffer) =>
    post<BookingResult>('/api/rides/book', { phone, provider, offer }),

  // Poll trip status (driver assignment)
  getTripStatus: (request_id: string) =>
    get<TripStatus>(`/api/rides/status/${request_id}`),

  // Cancel an active trip
  cancelTrip: (request_id: string) =>
    post<{ success: boolean }>('/api/rides/cancel', { request_id }),

  // Carbon portfolio for a rider
  getPortfolio: (phone: string) =>
    get<PortfolioSummary>(`/api/carbon/portfolio/${encodeURIComponent(phone)}`),

  // WhatsApp message history (sync from backend session)
  getWhatsAppHistory: (phone: string) =>
    get<WhatsAppMessage[]>(`/api/whatsapp/history/${encodeURIComponent(phone)}`),

  // Send a WhatsApp-channel message (routed through the orchestrator)
  sendWhatsAppMessage: (phone: string, text: string) =>
    post<{ reply: string; offers?: RideOffer[]; state: string }>(
      '/api/whatsapp/send',
      { phone, text },
    ),

  // Geocode an address (Nairobi landmarks or Google Maps)
  geocode: (address: string) =>
    post<{ lat: number; lon: number; found: boolean }>(
      '/api/geo/geocode',
      { address },
    ),
};

// ── WebSocket for real-time updates ───────────────────────────────────────────

type WSHandler = (event: WSEvent) => void;

export interface WSEvent {
  type:    'trip_status' | 'agent_step' | 'message' | 'payment_confirmed';
  payload: Record<string, unknown>;
}

class GoGreenSocket {
  private ws:       WebSocket | null = null;
  private handlers: WSHandler[]      = [];
  private phone:    string           = '';
  private retries:  number           = 0;
  private maxRetry: number           = 5;

  connect(phone: string): void {
    this.phone = phone;
    this._open();
  }

  private _open(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(`${WS_URL}?phone=${encodeURIComponent(this.phone)}`);
      this.ws.onmessage = (e) => {
        try {
          const evt: WSEvent = JSON.parse(e.data);
          this.handlers.forEach(h => h(evt));
        } catch { /* ignore malformed */ }
      };
      this.ws.onclose = () => {
        if (this.retries < this.maxRetry) {
          this.retries++;
          setTimeout(() => this._open(), 2000 * this.retries);
        }
      };
      this.ws.onopen = () => { this.retries = 0; };
    } catch (err) {
      console.warn('GoGreen WS connect failed:', err);
    }
  }

  on(handler: WSHandler): () => void {
    this.handlers.push(handler);
    return () => { this.handlers = this.handlers.filter(h => h !== handler); };
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
  }
}

export const socket = new GoGreenSocket();
