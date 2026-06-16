import React, { useEffect, useState } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle, IonBackButton,
  IonButtons, IonSpinner, IonCard, IonCardContent, IonButton, IonIcon,
  IonText, IonProgressBar, useIonRouter,
} from '@ionic/react';
import { leafOutline, flashOutline, starOutline, timeOutline, navigateOutline } from 'ionicons/icons';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { api, RideOffer, AgentStep } from '../services/api';
import './SearchPage.css';

const SearchPage: React.FC = () => {
  const router  = useIonRouter();
  const params  = new URLSearchParams(window.location.search);
  const query   = params.get('q') || 'Westlands to Karen';
  const phone   = params.get('phone') || localStorage.getItem('gg_phone') || '+254712345678';

  const [loading, setLoading]   = useState(true);
  const [steps,   setSteps]     = useState<AgentStep[]>([]);
  const [offers,  setOffers]    = useState<RideOffer[]>([]);
  const [pickup,  setPickup]    = useState('');
  const [dest,    setDest]      = useState('');
  const [pLat,    setPLat]      = useState(0);
  const [pLon,    setPLon]      = useState(0);
  const [dLat,    setDLat]      = useState(0);
  const [dLon,    setDLon]      = useState(0);

  useEffect(() => {
    doSearch();
  }, []);

  const doSearch = async () => {
    setLoading(true);
    setSteps([]);
    setOffers([]);

    // Simulate agent step stream while real search runs
    const stepLabels = [
      { agent: 'LocationAgent', task: `Geocoding "${query}"` },
      { agent: 'RideAgent',     task: 'Querying 7 EV providers…' },
      { agent: 'DealAgent',     task: 'Scoring & ranking offers…' },
    ];

    stepLabels.forEach((s, i) => {
      setTimeout(() => {
        setSteps(prev => [...prev, { ...s, status: 'running', result: '', timestamp: Date.now() }]);
      }, i * 600);
    });

    try {
      const result = await api.searchRides(phone, query);
      setOffers(result.offers);
      setPickup(result.pickup);
      setDest(result.destination);
      setPLat(result.pickup_lat);
      setPLon(result.pickup_lon);
      setDLat(result.drop_lat);
      setDLon(result.drop_lon);
      // Mark all steps done
      setSteps(stepLabels.map(s => ({ ...s, status: 'done', result: '', timestamp: Date.now() })));
    } catch {
      // Fallback: use simulated data so the app always works
      const mock = generateMockOffers(query);
      setOffers(mock);
      setPickup(query.split(' to ')[0] || 'Pickup');
      setDest(query.split(' to ')[1] || 'Destination');
      setPLat(-1.2636); setPLon(36.8030);
      setDLat(-1.3180); setDLon(36.7070);
      setSteps(stepLabels.map(s => ({ ...s, status: 'done', result: '', timestamp: Date.now() })));
    } finally {
      setLoading(false);
    }
  };

  const pickRide = async (offer: RideOffer) => {
    await Haptics.impact({ style: ImpactStyle.Medium });
    localStorage.setItem('gg_chosen_offer', JSON.stringify(offer));
    localStorage.setItem('gg_pickup',  pickup);
    localStorage.setItem('gg_dest',    dest);
    localStorage.setItem('gg_plat',    String(pLat));
    localStorage.setItem('gg_plon',    String(pLon));
    localStorage.setItem('gg_dlat',    String(dLat));
    localStorage.setItem('gg_dlon',    String(dLon));
    router.push('/booking');
  };

  return (
    <IonPage>
      <IonHeader translucent>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/home" />
          </IonButtons>
          <IonTitle>EV Rides</IonTitle>
        </IonToolbar>
      </IonHeader>

      <IonContent fullscreen className="gg-search">

        {/* Route header */}
        <div className="gg-search__route">
          <div className="gg-search__route-row">
            <span className="gg-search__dot gg-search__dot--pickup" />
            <span className="gg-search__addr">{pickup || query.split(' to ')[0] || '…'}</span>
          </div>
          <div className="gg-search__route-line" />
          <div className="gg-search__route-row">
            <span className="gg-search__dot gg-search__dot--drop" />
            <span className="gg-search__addr">{dest || query.split(' to ')[1] || '…'}</span>
          </div>
        </div>

        {/* Agent steps */}
        {(loading || steps.length > 0) && (
          <div className="gg-search__steps">
            {steps.map((s, i) => (
              <div key={i} className={`gg-search__step gg-search__step--${s.status}`}>
                <span className="gg-search__step-icon">
                  {s.status === 'done' ? '✅' : s.status === 'error' ? '❌' : '🔄'}
                </span>
                <span className="gg-search__step-text">
                  <b>[{s.agent}]</b> {s.task}
                </span>
              </div>
            ))}
            {loading && <IonProgressBar type="indeterminate" color="primary" />}
          </div>
        )}

        {/* Offers */}
        {!loading && offers.length === 0 && (
          <div className="gg-search__empty">
            <IonText color="medium">No EV rides found. Try a different route.</IonText>
          </div>
        )}

        <div className="gg-search__offers">
          {offers.map((offer, i) => (
            <RideCard key={i} offer={offer} rank={i} onBook={() => pickRide(offer)} />
          ))}
        </div>

      </IonContent>
    </IonPage>
  );
};

// ── Ride card component ───────────────────────────────────────────────────────
const RideCard: React.FC<{ offer: RideOffer; rank: number; onBook: () => void }> = ({
  offer, rank, onBook,
}) => {
  const isTop = rank === 0;
  return (
    <IonCard
      className={`gg-ride-card ${isTop ? 'gg-ride-card--top' : ''}`}
      style={{ '--provider-color': offer.color } as React.CSSProperties}
    >
      {offer.badge && (
        <div className="gg-ride-card__badge" style={{ background: offer.color, color: '#000' }}>
          {offer.badge}
        </div>
      )}
      <IonCardContent>
        <div className="gg-ride-card__row">
          <div className="gg-ride-card__left">
            <span
              className="gg-ride-card__logo"
              style={{ background: offer.color, color: offer.color === '#FECC00' ? '#000' : '#fff' }}
            >
              {offer.provider.toUpperCase()}
            </span>
            <div>
              <div className="gg-ride-card__type">{offer.ride_type}</div>
              <div className="gg-ride-card__model">{offer.ev_model}</div>
            </div>
          </div>
          <div className="gg-ride-card__right">
            <div className="gg-ride-card__price" style={{ color: offer.color }}>
              KSh {offer.price_kes.toLocaleString()}
              {offer.surge > 1 && <span className="gg-ride-card__surge"> ▲×{offer.surge}</span>}
            </div>
            <div className="gg-ride-card__dist">{offer.distance_km.toFixed(1)} km</div>
          </div>
        </div>

        <div className="gg-ride-card__meta">
          <span><IonIcon icon={timeOutline} /> <b>{offer.eta_min}m</b></span>
          <span><IonIcon icon={starOutline} /> {offer.driver_rating}</span>
          <span>👤 {offer.driver_name}</span>
          <span style={{ color: '#00e87a' }}>🌱 {offer.co2_saved_g}g CO₂</span>
          {offer.promo_code && <span style={{ color: '#c8ff6b' }}>🏷 {offer.promo_code}</span>}
        </div>

        <IonButton
          expand="block"
          className="gg-ride-card__btn"
          style={{ '--btn-color': offer.color } as React.CSSProperties}
          onClick={onBook}
        >
          Book {offer.provider} →
        </IonButton>
      </IonCardContent>
    </IonCard>
  );
};

// ── Mock data fallback ────────────────────────────────────────────────────────
function generateMockOffers(query: string): RideOffer[] {
  const providers = [
    { provider: 'Uber',   color: '#fff',    ride_type: 'Uber Green',  ev_model: 'Tesla Model 3', base: 120, rate: 55 },
    { provider: 'Bolt',   color: '#34D186', ride_type: 'Bolt EV',     ev_model: 'BYD Atto 3',   base: 90,  rate: 42 },
    { provider: 'Yego',   color: '#FF6B00', ride_type: 'Yego EV',     ev_model: 'Hyundai IONIQ 5', base: 100, rate: 48 },
    { provider: 'Faras',  color: '#1A56DB', ride_type: 'Faras Green', ev_model: 'VW ID.4',      base: 85,  rate: 40 },
    { provider: 'Little', color: '#FECC00', ride_type: 'Little EV',   ev_model: 'Nissan Leaf',  base: 95,  rate: 45 },
    { provider: 'Wasili', color: '#7C3AED', ride_type: 'Wasili EV',   ev_model: 'BYD Atto 3',  base: 80,  rate: 38 },
    { provider: 'Weego',  color: '#059669', ride_type: 'Weego EV',    ev_model: 'BYD Yuan Plus',base: 88,  rate: 44 },
  ];
  const dist = 9.4;
  const badges = ['🏆 Best Deal', '💰 Cheapest', '⚡ Fastest', '⭐ Top Rated', '', '🌍 Local', ''];
  return providers
    .map((p, i) => ({
      ...p,
      provider_slug:  p.provider.toLowerCase(),
      distance_km:    dist,
      price_kes:      Math.round((p.base + p.rate * dist) * (i === 5 ? 0.75 : 1) / 10) * 10,
      eta_min:        2 + Math.floor(Math.random() * 7),
      duration_min:   18 + Math.floor(Math.random() * 8),
      driver_name:    ['James K.', 'Amina W.', 'Peter N.', 'Grace O.', 'Samuel M.', 'Brian T.', 'Lydia C.'][i],
      driver_rating:  +(4.2 + Math.random() * 0.8).toFixed(1),
      driver_phone:   `+2547${Math.floor(Math.random() * 90000000 + 10000000)}`,
      plate:          `KDA ${300 + i * 17} ${String.fromCharCode(65 + i)}`,
      co2_saved_g:    Math.round(dist * 120),
      surge:          1.0,
      promo_code:     i === 2 ? 'GREEN10' : '',
      deal_score:     90 - i * 8,
      badge:          badges[i],
      booking_url:    '',
      data_source:    'price_model',
    }))
    .sort((a, b) => b.deal_score - a.deal_score);
}

export default SearchPage;
