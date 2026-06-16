import React, { useState, useEffect } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle,
  IonCard, IonCardContent, IonItem, IonLabel, IonInput,
  IonToggle, IonButton, IonIcon, IonAlert, IonChip,
  IonList, IonListHeader,
} from '@ionic/react';
import {
  phonePortraitOutline, leafOutline, chatbubblesOutline,
  notificationsOutline, shieldCheckmarkOutline, informationCircleOutline,
  logOutOutline, diamondOutline,
} from 'ionicons/icons';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { Network } from '@capacitor/network';
import './ProfilePage.css';

const ProfilePage: React.FC = () => {
  const [phone,     setPhone]    = useState(localStorage.getItem('gg_phone') || '');
  const [waSync,    setWaSync]   = useState(localStorage.getItem('gg_wa_sync') !== 'false');
  const [pushNotif, setPushNotif]= useState(localStorage.getItem('gg_push') !== 'false');
  const [online,    setOnline]   = useState(true);
  const [showSaved, setShowSaved]= useState(false);

  useEffect(() => {
    Network.getStatus().then(s => setOnline(s.connected));
    Network.addListener('networkStatusChange', s => setOnline(s.connected));
  }, []);

  const savePhone = async () => {
    if (!phone.trim()) return;
    const normalised = normalisePhone(phone);
    localStorage.setItem('gg_phone', normalised);
    setPhone(normalised);
    await Haptics.impact({ style: ImpactStyle.Light });
    setShowSaved(true);
  };

  const toggleWaSync = (v: boolean) => {
    setWaSync(v);
    localStorage.setItem('gg_wa_sync', String(v));
  };

  const togglePush = (v: boolean) => {
    setPushNotif(v);
    localStorage.setItem('gg_push', String(v));
  };

  return (
    <IonPage>
      <IonHeader translucent>
        <IonToolbar>
          <IonTitle>Profile</IonTitle>
        </IonToolbar>
      </IonHeader>

      <IonContent fullscreen className="gg-profile">

        {/* Avatar / name block */}
        <div className="gg-profile__hero">
          <div className="gg-profile__avatar">🌿</div>
          <div className="gg-profile__name">Go Green Rider</div>
          <div className="gg-profile__phone-display">
            {phone || 'Set your phone number below'}
          </div>
          <div className="gg-profile__status-row">
            <IonChip
              className="gg-profile__status-chip"
              style={{ '--chip-bg': online ? '#0d2a1e' : '#2a0d0d',
                       '--chip-color': online ? '#00e87a' : '#ff4f4f' } as React.CSSProperties}
            >
              <span style={{ color: 'var(--chip-color)' }}>
                {online ? '● Connected' : '○ Offline'}
              </span>
            </IonChip>
            <IonChip className="gg-profile__status-chip">
              <IonIcon icon={leafOutline} color="primary" />
              <span style={{ color: '#00e87a' }}>VM0038 Active</span>
            </IonChip>
          </div>
        </div>

        {/* Phone number */}
        <IonList className="gg-profile__list">
          <IonListHeader>
            <IonLabel className="gg-profile__list-header">ACCOUNT</IonLabel>
          </IonListHeader>

          <IonCard className="gg-profile__card">
            <IonCardContent>
              <div className="gg-profile__field-label">
                <IonIcon icon={phonePortraitOutline} color="primary" />
                WhatsApp / M-Pesa Number
              </div>
              <div className="gg-profile__phone-row">
                <IonInput
                  className="gg-profile__phone-input"
                  type="tel"
                  placeholder="+254712345678"
                  value={phone}
                  onIonInput={e => setPhone(e.detail.value!)}
                />
                <IonButton
                  size="small"
                  onClick={savePhone}
                  className="gg-profile__save-btn"
                >
                  Save
                </IonButton>
              </div>
              <div className="gg-profile__phone-hint">
                Used for M-Pesa STK push and WhatsApp sync
              </div>
            </IonCardContent>
          </IonCard>
        </IonList>

        {/* WhatsApp sync */}
        <IonList className="gg-profile__list">
          <IonListHeader>
            <IonLabel className="gg-profile__list-header">WHATSAPP CHANNEL</IonLabel>
          </IonListHeader>

          <IonCard className="gg-profile__card">
            <IonCardContent>
              <div className="gg-profile__setting-row">
                <div>
                  <div className="gg-profile__setting-title">
                    <IonIcon icon={chatbubblesOutline} color="primary" />
                    Sync Chat History
                  </div>
                  <div className="gg-profile__setting-sub">
                    Mirror your WhatsApp conversation in the app
                  </div>
                </div>
                <IonToggle
                  checked={waSync}
                  onIonChange={e => toggleWaSync(e.detail.checked)}
                  color="primary"
                />
              </div>

              <div className="gg-profile__wa-info">
                <div className="gg-profile__wa-info-row">
                  <span>WhatsApp channel</span>
                  <span style={{ color: '#00e87a' }}>+254 7XX XXX XXX</span>
                </div>
                <div className="gg-profile__wa-info-row">
                  <span>WebSocket sync</span>
                  <span style={{ color: online ? '#00e87a' : '#ff4f4f' }}>
                    {online ? 'Connected' : 'Offline'}
                  </span>
                </div>
                <div className="gg-profile__wa-info-row">
                  <span>Session state</span>
                  <span style={{ color: '#ffb827' }}>
                    {localStorage.getItem('gg_chosen_offer') ? 'Ride selected' : 'Idle'}
                  </span>
                </div>
              </div>
            </IonCardContent>
          </IonCard>
        </IonList>

        {/* Notifications */}
        <IonList className="gg-profile__list">
          <IonListHeader>
            <IonLabel className="gg-profile__list-header">NOTIFICATIONS</IonLabel>
          </IonListHeader>
          <IonCard className="gg-profile__card">
            <IonCardContent>
              <div className="gg-profile__setting-row">
                <div>
                  <div className="gg-profile__setting-title">
                    <IonIcon icon={notificationsOutline} color="primary" />
                    Push Notifications
                  </div>
                  <div className="gg-profile__setting-sub">Driver arrival, payment, carbon updates</div>
                </div>
                <IonToggle
                  checked={pushNotif}
                  onIonChange={e => togglePush(e.detail.checked)}
                  color="primary"
                />
              </div>
            </IonCardContent>
          </IonCard>
        </IonList>

        {/* Carbon / VCU info */}
        <IonList className="gg-profile__list">
          <IonListHeader>
            <IonLabel className="gg-profile__list-header">CARBON CREDITS</IonLabel>
          </IonListHeader>
          <IonCard className="gg-profile__card">
            <IonCardContent>
              {[
                ['Methodology',    'Verra VM0038 v1.0'],
                ['Additionality',  'VMD0049 positive list ✅'],
                ['Grid EF',        '0.061 kgCO₂e/kWh (IEA 2024)'],
                ['VCU Price',      '≈ $12.50 / tCO₂e'],
                ['Crediting',      '7 years (renewable × 2)'],
              ].map(([k, v]) => (
                <div key={k} className="gg-profile__info-row">
                  <span className="gg-profile__info-key">{k}</span>
                  <span className="gg-profile__info-val">{v}</span>
                </div>
              ))}
            </IonCardContent>
          </IonCard>
        </IonList>

        {/* App info */}
        <div className="gg-profile__app-info">
          <div>Go Green Rider App v1.0.0</div>
          <div>Ionic + Capacitor · iOS & Android</div>
          <div style={{ color: 'var(--gg-muted)', marginTop: 4 }}>
            © 2025 Go Green Limited · Nairobi, Kenya
          </div>
        </div>

        <div style={{ height: 32 }} />
      </IonContent>

      <IonAlert
        isOpen={showSaved}
        header="Saved!"
        message={`Phone number set to ${phone}`}
        buttons={['OK']}
        onDidDismiss={() => setShowSaved(false)}
      />
    </IonPage>
  );
};

function normalisePhone(p: string): string {
  p = p.replace(/[\s\-()]/g, '');
  if (p.startsWith('+'))  return p;
  if (p.startsWith('07')) return '+254' + p.slice(1);
  if (p.startsWith('7'))  return '+254' + p;
  return p;
}

export default ProfilePage;
