import React, { useState, useRef } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle,
  IonSearchbar, IonCard, IonCardContent, IonButton, IonIcon,
  IonText, IonChip, IonLabel, IonSkeletonText, IonRippleEffect,
  useIonRouter,
} from '@ionic/react';
import {
  locationOutline, navigateOutline, leafOutline,
  flashOutline, starOutline, timeOutline, carOutline,
} from 'ionicons/icons';
import { Geolocation } from '@capacitor/geolocation';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { api, RideOffer } from '../services/api';
import './HomePage.css';

const QUICK_DESTINATIONS = [
  { label: 'JKIA', icon: '✈️', query: 'airport' },
  { label: 'CBD',  icon: '🏙️', query: 'nairobi cbd' },
  { label: 'Westlands', icon: '🛍️', query: 'westlands' },
  { label: 'Karen', icon: '🌿', query: 'karen' },
  { label: 'Gigiri', icon: '🏛️', query: 'gigiri' },
];

const PROVIDERS = [
  { name: 'Uber',   color: '#fff',    bg: '#111' },
  { name: 'Bolt',   color: '#34D186', bg: '#0d2a1e' },
  { name: 'Yego',   color: '#FF6B00', bg: '#2a1600' },
  { name: 'Faras',  color: '#1A56DB', bg: '#0d1a33' },
  { name: 'Little', color: '#FECC00', bg: '#2a2500' },
  { name: 'Wasili', color: '#7C3AED', bg: '#1a0d33' },
  { name: 'Weego',  color: '#059669', bg: '#0d2a1e' },
];

const HomePage: React.FC = () => {
  const router    = useIonRouter();
  const [query,   setQuery]   = useState('');
  const [loading, setLoading] = useState(false);
  const phone = localStorage.getItem('gg_phone') || '+254712345678';

  const handleSearch = async (q: string) => {
    if (!q.trim()) return;
    await Haptics.impact({ style: ImpactStyle.Light });
    router.push(`/search?q=${encodeURIComponent(q)}&phone=${encodeURIComponent(phone)}`);
  };

  const handleQuickDest = async (dest: typeof QUICK_DESTINATIONS[0]) => {
    await Haptics.impact({ style: ImpactStyle.Light });
    handleSearch(`Take me to ${dest.query}`);
  };

  const handleGPS = async () => {
    try {
      await Haptics.impact({ style: ImpactStyle.Medium });
      const pos = await Geolocation.getCurrentPosition({ enableHighAccuracy: true });
      const { latitude: lat, longitude: lon } = pos.coords;
      router.push(`/search?lat=${lat}&lon=${lon}&phone=${encodeURIComponent(phone)}`);
    } catch {
      handleSearch('current location to CBD');
    }
  };

  return (
    <IonPage className="gg-home">
      <IonContent fullscreen scrollY={false}>

        {/* ── Hero header ─────────────────────────────────────────── */}
        <div className="gg-home__hero">
          <div className="gg-home__glow" />
          <div className="gg-home__logo">
            <span className="gg-home__logo-icon">🌿</span>
            <div>
              <div className="gg-home__logo-name">Go Green</div>
              <div className="gg-home__logo-sub">EV RIDES · NAIROBI</div>
            </div>
          </div>

          {/* Search bar */}
          <div className="gg-home__search-wrap">
            <IonSearchbar
              className="gg-home__searchbar"
              placeholder="Where are you going?"
              value={query}
              onIonInput={e => setQuery(e.detail.value!)}
              onIonChange={e => setQuery(e.detail.value!)}
              onKeyDown={e => e.key === 'Enter' && handleSearch(query)}
              debounce={0}
              animated={false}
            />
            <IonButton
              className="gg-home__gps-btn"
              onClick={handleGPS}
              fill="clear"
            >
              <IonIcon icon={navigateOutline} />
            </IonButton>
          </div>

          {/* Quick destinations */}
          <div className="gg-home__quick">
            {QUICK_DESTINATIONS.map(d => (
              <button
                key={d.label}
                className="gg-home__quick-chip ion-activatable"
                onClick={() => handleQuickDest(d)}
              >
                <IonRippleEffect />
                <span className="gg-home__quick-icon">{d.icon}</span>
                <span>{d.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Provider strip ───────────────────────────────────────── */}
        <div className="gg-home__section-label">⚡ EV PROVIDERS</div>
        <div className="gg-home__providers">
          {PROVIDERS.map(p => (
            <div
              key={p.name}
              className="gg-home__provider-badge"
              style={{ background: p.bg, border: `1px solid ${p.color}33` }}
            >
              <span style={{ color: p.color, fontWeight: 800, fontSize: 11 }}>
                {p.name.toUpperCase()}
              </span>
            </div>
          ))}
        </div>

        {/* ── Stats row ────────────────────────────────────────────── */}
        <div className="gg-home__stats">
          {[
            { icon: leafOutline,  label: 'CO₂ Saved',   value: '0 g',  color: '#00e87a' },
            { icon: flashOutline, label: 'VCUs Earned',  value: '0.000', color: '#b87bff' },
            { icon: carOutline,   label: 'EV Trips',     value: '0',    color: '#ffb827' },
          ].map(s => (
            <IonCard key={s.label} className="gg-home__stat-card">
              <IonCardContent>
                <IonIcon icon={s.icon} style={{ color: s.color, fontSize: 20 }} />
                <div className="gg-home__stat-val" style={{ color: s.color }}>{s.value}</div>
                <div className="gg-home__stat-lbl">{s.label}</div>
              </IonCardContent>
            </IonCard>
          ))}
        </div>

        {/* ── CTA ──────────────────────────────────────────────────── */}
        <div className="gg-home__cta">
          <IonButton
            expand="block"
            className="gg-home__cta-btn"
            onClick={() => handleSearch(query || 'Westlands to Karen')}
          >
            <IonIcon slot="start" icon={carOutline} />
            Find EV Rides
          </IonButton>
        </div>

      </IonContent>
    </IonPage>
  );
};

export default HomePage;
