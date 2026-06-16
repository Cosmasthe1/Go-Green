# 🌿 Go Green — Rider Mobile App

> **Ionic + Capacitor · React · TypeScript · iOS & Android**

Native mobile companion to the Go Green EV ride ordering platform. Runs alongside the WhatsApp channel — both share the same backend session state via HTTP + WebSocket.

---

## Screens

| Tab | Screen | Description |
|-----|--------|-------------|
| 🚗 Rides | `HomePage` | GPS search, quick destinations, provider strip, stats |
| 🚗 Rides | `SearchPage` | Live ride results with agent steps + branded ride cards |
| 🚗 Rides | `BookingPage` | Confirm → M-Pesa STK push → driver tracking + carbon earned |
| 💬 Chat | `ChatPage` | WhatsApp simulator synced to backend session via WebSocket |
| 🌿 Carbon | `CarbonPage` | Verra VM0038 portfolio: VCUs, CO₂ saved, trip ledger, formula |
| 👤 Profile | `ProfilePage` | Phone setup, WhatsApp sync toggle, push notifications, app info |

---

## WhatsApp Channel Sync

The app and the WhatsApp channel share one orchestrator session per phone number:

```
WhatsApp Message                   App Chat Tab
      │                                 │
      ▼                                 ▼
Flask webhook ──► GoGreenOrchestrator ◄── POST /api/whatsapp/send
                        │
                   Session store
                   (phone → state)
                        │
                    WebSocket ──► push to app in real-time
```

When a rider sends "Westlands to Karen" on WhatsApp:
- The Flask webhook routes it to the orchestrator
- The orchestrator responds via WhatsApp
- The same reply is pushed to the app via WebSocket
- Ride offers appear as tappable chips in the Chat tab

When a rider taps a ride card in the app:
- The app calls `POST /api/rides/book`
- The orchestrator processes the booking
- M-Pesa STK push fires to the WhatsApp-registered number
- Carbon credits are calculated and shown in both the app and WhatsApp

---

## File Structure

```
gogreen-app/
├── src/
│   ├── App.tsx                    Root router + Capacitor plugin setup
│   ├── main.tsx                   React entry point
│   ├── services/
│   │   └── api.ts                 HTTP client + WebSocket (GoGreenSocket)
│   ├── theme/
│   │   └── variables.css          Go Green Ionic design system tokens
│   └── pages/
│       ├── HomePage.tsx / .css    Home with GPS search + quick destinations
│       ├── SearchPage.tsx / .css  Ride results + branded provider cards
│       ├── BookingPage.tsx / .css Confirm → M-Pesa → tracking + carbon
│       ├── ChatPage.tsx / .css    WhatsApp-synced chat with inline offer chips
│       ├── CarbonPage.tsx / .css  VM0038 VCU portfolio dashboard
│       └── ProfilePage.tsx / .css Phone, WA sync, notifications, settings
├── ws_server.py                   Flask WebSocket + REST API endpoints
├── index.html
├── vite.config.ts
├── tsconfig.json
├── capacitor.config.ts
├── package.json
└── .env.example
```

---

## Setup

### 1. Install dependencies

```bash
cd gogreen-app
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Set VITE_API_BASE_URL to your Go Green backend URL
```

### 3. Add WebSocket + REST API to your Go Green backend

In your existing `app.py`:

```python
from ws_server import register_ws_and_api

# After creating flask_app and wa_agent:
register_ws_and_api(flask_app, wa_agent)
```

Install flask-sock:
```bash
pip install flask-sock
```

### 4. Run in browser (dev)

```bash
npm start
# → http://localhost:8100
```

The Vite proxy forwards `/api/*` → `localhost:5000` and `/ws` → `ws://localhost:5000/ws`.

### 5. Build for native

```bash
npm run build              # compile TypeScript + Vite bundle → dist/

# Android
npm run android            # syncs Capacitor + opens Android Studio

# iOS (macOS only)
npm run ios                # syncs Capacitor + opens Xcode
```

---

## Native Features (Capacitor plugins)

| Plugin | Usage |
|--------|-------|
| `@capacitor/geolocation` | GPS pickup on home screen |
| `@capacitor/haptics` | Tap feedback on buttons and ride selection |
| `@capacitor/push-notifications` | Driver arrival, payment confirmed |
| `@capacitor/local-notifications` | Scheduled ride reminders |
| `@capacitor/network` | Online/offline status in profile |
| `@capacitor/status-bar` | Dark status bar (#03080a) |
| `@capacitor/app` | Android back button handling |

---

## Design System

All tokens in `src/theme/variables.css`:

| Token | Value | Use |
|-------|-------|-----|
| `--gg-green` | `#00e87a` | Primary accent, CTA buttons |
| `--gg-lime` | `#c8ff6b` | Secondary accent, promo chips |
| `--gg-amber` | `#ffb827` | Money/payment values |
| `--gg-purple` | `#b87bff` | VCU/carbon values |
| `--gg-surface` | `#060f0c` | Card backgrounds |
| `--gg-border` | `#0d2a1e` | Card borders |
| `--gg-mono` | `'Azeret Mono'` | Numbers, data, code |
| `--ion-font-family` | `'Bricolage Grotesque'` | All body text |

---

## Production Checklist

- [ ] Set `VITE_API_BASE_URL` to production backend HTTPS URL
- [ ] Set `VITE_WS_URL` to production WSS URL
- [ ] Replace `ws_server.py` CORS config for production domain
- [ ] Configure FCM (Android) and APNs (iOS) for push notifications
- [ ] Set `appId` in `capacitor.config.ts` to your App Store / Play Store ID
- [ ] Add app icons and splash screens (`npx @capacitor/assets generate`)
- [ ] Sign APK/IPA for store submission
