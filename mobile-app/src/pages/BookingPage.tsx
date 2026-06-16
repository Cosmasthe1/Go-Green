import React, { useState, useEffect } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle,
  IonButtons, IonBackButton, IonButton, IonIcon, IonCard,
  IonCardContent, IonSpinner, IonAlert, IonProgressBar,
  useIonRouter,
} from '@ionic/react';
import { checkmarkCircleOutline, closeCircleOutline, cardOutline, leafOutline } from 'ionicons/icons';
import { Haptics, ImpactStyle, NotificationType } from '@capacitor/haptics';
import { LocalNotifications } from '@capacitor/local-notifications';
import { api, RideOffer, BookingResult, CarbonResult } from '../services/api';
import './BookingPage.css';

type Stage = 'confirm' | 'paying' | 'booked' | 'tracking';

const BookingPage: React.FC = () => {
  const router  = useIonRouter();
  const phone   = localStorage.getItem('gg_phone') || '+254712345678';
  const offer   = JSON.parse(localStorage.getItem('gg_chosen_offer') || '{}') as RideOffer;
  const pickup  = localStorage.getItem('gg_pickup')  || 'Pickup';
  const dest    = localStorage.getItem('gg_dest')    || 'Destination';

  const [stage,    setStage]    = useState<Stage>('confirm');
  const [booking,  setBooking]  = useState<BookingResult | null>(null);
  const [carbon,   setCarbon]   = useState<CarbonResult | null>(null);
  const [showCancel, setShowCancel] = useState(false);
  const [etaCount, setEtaCount] = useState(offer.eta_min || 5);

  // Countdown timer once booked
  useEffect(() => {
    if (stage !== 'tracking') return;
    if (etaCount <= 0) return;
    const t = setInterval(() => setEtaCount(n => Math.max(0, n - 1)), 60_000);
    return () => clearInterval(t);
  }, [stage, etaCount]);

  const handleConfirm = async () => {
    await Haptics.impact({ style: ImpactStyle.Medium });
    setStage('paying');
    try {
      const result = await api.bookRide(phone, offer.provider, offer);
      setBooking(result);
      if (result.carbon_result) setCarbon(result.carbon_result);

      if (result.success) {
        await Haptics.notification({ type: NotificationType.Success });
        setStage('booked');

        // Schedule local push notification
        if (await LocalNotifications.checkPermissions().then(p => p.display === 'granted')) {
          await LocalNotifications.schedule({
            notifications: [{
              id:    1,
              title: '🚗 Driver on the way!',
              body:  `${result.ev_model || offer.ev_model} · ETA ${offer.eta_min} min`,
              schedule: { at: new Date(Date.now() + 2000) },
            }],
          });
        }

        setTimeout(() => setStage('tracking'), 3000);
      } else {
        await Haptics.notification({ type: NotificationType.Error });
        setStage('confirm');
        alert(result.error || 'Booking failed. Please try again.');
      }
    } catch (err) {
      // Demo fallback
      await Haptics.notification({ type: NotificationType.Success });
      const demoResult: BookingResult = {
        success:      true,
        trip_id:      `GG-${Date.now().toString().slice(-6)}`,
        request_id:   `demo-${Date.now()}`,
        status:       'processing',
        customer_msg: 'Demo booking confirmed!',
        driver_name:  offer.driver_name || 'James K.',
        driver_phone: offer.driver_phone || '+254712345678',
        plate:        offer.plate || 'KDA 302 A',
        ev_model:     offer.ev_model || 'BYD Atto 3',
      };
      setBooking(demoResult);
      // Demo carbon
      const dist  = offer.distance_km || 9.4;
      const be    = dist * 0.09 * 2.296 * 1.19;
      const pe    = (dist * 0.18 / 0.9) * 0.061;
      const net   = Math.max(be - pe, 0) * 0.97;
      const vcu   = (net / 1000) * 0.9;
      setCarbon({
        distance_km: dist, baseline_emissions_kg: be, project_emissions_kg: pe,
        net_reduction_kg: net, net_vcu: vcu, vcu_value_kes: vcu * 1625,
        trees_equivalent: vcu * 45, petrol_saved_litres: dist * 0.09,
        methodology: 'Verra VM0038 v1.0',
      });
      setStage('booked');
      setTimeout(() => setStage('tracking'), 3000);
    }
  };

  const handleCancel = async () => {
    if (booking?.request_id) await api.cancelTrip(booking.request_id).catch(() => {});
    await Haptics.notification({ type: NotificationType.Warning });
    router.goBack();
  };

  return (
    <IonPage>
      <IonHeader translucent>
        <IonToolbar>
          <IonButtons slot="start">
            {stage === 'confirm' && <IonBackButton defaultHref="/search" />}
          </IonButtons>
          <IonTitle>
            {stage === 'confirm'  ? 'Confirm Ride'      :
             stage === 'paying'   ? 'Processing…'       :
             stage === 'booked'   ? 'Booking Confirmed' : 'Driver En Route'}
          </IonTitle>
          {stage === 'tracking' && (
            <IonButtons slot="end">
              <IonButton onClick={() => setShowCancel(true)} color="danger">Cancel</IonButton>
            </IonButtons>
          )}
        </IonToolbar>
        {stage === 'paying' && <IonProgressBar type="indeterminate" color="primary" />}
      </IonHeader>

      <IonContent fullscreen className="gg-booking">

        {/* ── Provider header ────────────────────────────────────── */}
        <div className="gg-booking__provider" style={{ borderColor: offer.color + '44' }}>
          <span
            className="gg-booking__provider-logo"
            style={{ background: offer.color, color: offer.color === '#FECC00' ? '#000' : '#fff' }}
          >
            {offer.provider?.toUpperCase()}
          </span>
          <div>
            <div className="gg-booking__provider-type">{offer.ride_type}</div>
            <div className="gg-booking__provider-model">{offer.ev_model}</div>
          </div>
          <div className="gg-booking__provider-price" style={{ color: offer.color }}>
            KSh {(offer.price_kes || 0).toLocaleString()}
          </div>
        </div>

        {/* ── Route ─────────────────────────────────────────────── */}
        <div className="gg-booking__route">
          <div className="gg-booking__route-row">
            <span className="gg-booking__dot gg-booking__dot--green" />
            <span>{pickup}</span>
          </div>
          <div className="gg-booking__route-line" />
          <div className="gg-booking__route-row">
            <span className="gg-booking__dot gg-booking__dot--red" />
            <span>{dest}</span>
          </div>
        </div>

        {/* ── Trip details ──────────────────────────────────────── */}
        <div className="gg-booking__details">
          {[
            { label: 'Distance',   value: `${offer.distance_km?.toFixed(1)} km` },
            { label: 'ETA',        value: `${offer.eta_min} min` },
            { label: 'Duration',   value: `~${offer.duration_min} min ride` },
            { label: 'Driver',     value: `${offer.driver_name}  ⭐${offer.driver_rating}` },
            { label: 'Plate',      value: offer.plate },
          ].map(d => (
            <div key={d.label} className="gg-booking__detail-row">
              <span className="gg-booking__detail-label">{d.label}</span>
              <span className="gg-booking__detail-value">{d.value}</span>
            </div>
          ))}
        </div>

        {/* ── Carbon preview ────────────────────────────────────── */}
        <div className="gg-booking__carbon">
          <IonIcon icon={leafOutline} color="primary" />
          <span>
            Riding EV saves ~<b style={{ color: '#00e87a' }}>{offer.co2_saved_g}g CO₂</b> vs petrol
            · certified under <b>Verra VM0038</b>
          </span>
        </div>

        {/* ── M-Pesa block (after booking) ─────────────────────── */}
        {(stage === 'paying' || stage === 'booked' || stage === 'tracking') && (
          <IonCard className="gg-booking__mpesa">
            <IonCardContent>
              <div className="gg-booking__mpesa-label">💳 M-PESA STK PUSH</div>
              <div className="gg-booking__mpesa-amount" style={{ color: '#00e87a' }}>
                KSh {(offer.price_kes || 0).toLocaleString()}
              </div>
              {stage === 'paying' ? (
                <div className="gg-booking__mpesa-status">
                  <IonSpinner name="dots" color="primary" />
                  <span>Sending to <b>{phone}</b>…</span>
                </div>
              ) : (
                <div className="gg-booking__mpesa-status">
                  <IonIcon icon={checkmarkCircleOutline} color="primary" />
                  <span>
                    {stage === 'booked' ? `Check your phone ${phone} — enter PIN` : 'Payment sent ✓'}
                  </span>
                </div>
              )}
              {booking?.trip_id && (
                <div className="gg-booking__trip-id">
                  Trip ID: <code>{booking.trip_id}</code>
                </div>
              )}
            </IonCardContent>
          </IonCard>
        )}

        {/* ── Carbon earned (after booking) ────────────────────── */}
        {carbon && stage !== 'confirm' && stage !== 'paying' && (
          <IonCard className="gg-booking__carbon-card">
            <IonCardContent>
              <div className="gg-booking__carbon-label">🌿 CARBON CREDITS EARNED</div>
              <div className="gg-booking__carbon-grid">
                <div>
                  <div className="gg-booking__carbon-val" style={{ color: '#00e87a' }}>
                    {(carbon.net_reduction_kg * 1000).toFixed(0)}g
                  </div>
                  <div className="gg-booking__carbon-sub">CO₂ Saved</div>
                </div>
                <div>
                  <div className="gg-booking__carbon-val" style={{ color: '#b87bff' }}>
                    {carbon.net_vcu.toFixed(8)}
                  </div>
                  <div className="gg-booking__carbon-sub">VCUs Earned</div>
                </div>
                <div>
                  <div className="gg-booking__carbon-val" style={{ color: '#ffb827' }}>
                    KSh {carbon.vcu_value_kes.toFixed(4)}
                  </div>
                  <div className="gg-booking__carbon-sub">VCU Value</div>
                </div>
                <div>
                  <div className="gg-booking__carbon-val" style={{ color: '#c8ff6b' }}>
                    {carbon.trees_equivalent.toFixed(3)}
                  </div>
                  <div className="gg-booking__carbon-sub">Trees/yr</div>
                </div>
              </div>
              <div className="gg-booking__carbon-method">Verra VM0038 v1.0 · VMD0049 ✅</div>
            </IonCardContent>
          </IonCard>
        )}

        {/* ── Driver tracking ───────────────────────────────────── */}
        {stage === 'tracking' && (
          <IonCard className="gg-booking__tracking">
            <IonCardContent>
              <div className="gg-booking__tracking-eta">
                <div className="gg-booking__tracking-min">{etaCount}</div>
                <div className="gg-booking__tracking-label">MIN AWAY</div>
              </div>
              <div className="gg-booking__tracking-driver">
                <b>{booking?.driver_name || offer.driver_name}</b>
                <span> is heading to <b>{pickup}</b></span>
              </div>
              <div className="gg-booking__tracking-plate">
                🚘 {booking?.plate || offer.plate} &nbsp;·&nbsp;
                {booking?.ev_model || offer.ev_model}
              </div>
            </IonCardContent>
          </IonCard>
        )}

        {/* ── Action buttons ────────────────────────────────────── */}
        {stage === 'confirm' && (
          <div className="gg-booking__actions">
            <IonButton expand="block" className="gg-booking__confirm-btn" onClick={handleConfirm}>
              <IonIcon slot="start" icon={cardOutline} />
              Confirm & Pay with M-Pesa
            </IonButton>
            <IonButton expand="block" fill="outline" color="medium" onClick={() => router.goBack()}>
              Go Back
            </IonButton>
          </div>
        )}

        {stage === 'tracking' && (
          <div className="gg-booking__actions">
            <IonButton expand="block" fill="outline" color="primary"
              onClick={() => router.push('/carbon')}>
              <IonIcon slot="start" icon={leafOutline} />
              View Carbon Credits
            </IonButton>
          </div>
        )}

      </IonContent>

      <IonAlert
        isOpen={showCancel}
        header="Cancel Ride?"
        message="Are you sure you want to cancel this trip?"
        buttons={[
          { text: 'Keep Ride', role: 'cancel', handler: () => setShowCancel(false) },
          { text: 'Cancel Trip', role: 'destructive', handler: handleCancel },
        ]}
        onDidDismiss={() => setShowCancel(false)}
      />
    </IonPage>
  );
};

export default BookingPage;
