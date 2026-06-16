import React, { useState, useEffect } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle,
  IonCard, IonCardContent, IonIcon, IonRefresher,
  IonRefresherContent, IonSkeletonText, IonChip, IonButton,
} from '@ionic/react';
import { leafOutline, diamondOutline, cashOutline, treeOutline, informationCircleOutline } from 'ionicons/icons';
import { api, PortfolioSummary, CarbonLedgerEntry } from '../services/api';
import './CarbonPage.css';

const VM0038_PARAMS = {
  EF_GRID:  0.061, EF_PETROL: 2.296, WTT_PETROL: 1.19,
  AFEC:     0.090, EV_KWH_KM: 0.180, ETA_L2:     0.900,
  LEAKAGE:  0.03,  VCS_BUFFER: 0.10, VCU_PRICE_KES: 1625,
};

const CarbonPage: React.FC = () => {
  const phone = localStorage.getItem('gg_phone') || '+254712345678';
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [showFormula, setShowFormula] = useState(false);

  useEffect(() => { loadPortfolio(); }, []);

  const loadPortfolio = async () => {
    setLoading(true);
    try {
      const data = await api.getPortfolio(phone);
      setPortfolio(data);
    } catch {
      // Demo portfolio
      setPortfolio(generateDemoPortfolio(phone));
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async (e: CustomEvent) => {
    await loadPortfolio();
    (e.target as HTMLIonRefresherElement).complete();
  };

  const totalCo2G = portfolio ? portfolio.total_co2_kg * 1000 : 0;

  return (
    <IonPage>
      <IonHeader translucent>
        <IonToolbar>
          <IonTitle>🌿 Carbon Credits</IonTitle>
          <IonButton
            slot="end" fill="clear" size="small"
            onClick={() => setShowFormula(f => !f)}
          >
            <IonIcon icon={informationCircleOutline} />
          </IonButton>
        </IonToolbar>
      </IonHeader>

      <IonContent fullscreen className="gg-carbon">
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent />
        </IonRefresher>

        {/* Verra methodology badge */}
        <div className="gg-carbon__method-bar">
          <span className="gg-carbon__method-pill">VM0038 v1.0</span>
          <span className="gg-carbon__method-pill">VMD0049</span>
          <span className="gg-carbon__method-pill">Kenya Grid 0.061 kgCO₂/kWh</span>
          <span className="gg-carbon__method-pill">VCU ≈$12.50/t</span>
        </div>

        {/* Top metrics */}
        <div className="gg-carbon__metrics">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <IonCard key={i} className="gg-carbon__metric-card">
                <IonCardContent>
                  <IonSkeletonText animated style={{ width: '60%' }} />
                  <IonSkeletonText animated style={{ width: '40%', marginTop: 6 }} />
                </IonCardContent>
              </IonCard>
            ))
          ) : (
            <>
              <MetricCard icon={leafOutline}    color="#00e87a"
                title="CO₂ SAVED"
                value={totalCo2G >= 1000 ? `${(totalCo2G/1000).toFixed(2)} kg` : `${totalCo2G.toFixed(0)} g`}
                sub={`${portfolio?.total_co2_kg.toFixed(4)} tCO₂e`} />
              <MetricCard icon={diamondOutline} color="#b87bff"
                title="VCUs EARNED"
                value={portfolio?.total_vcu.toFixed(6) || '0.000000'}
                sub="Verra Verified" />
              <MetricCard icon={cashOutline}    color="#ffb827"
                title="PORTFOLIO"
                value={`KSh ${portfolio?.total_value_kes.toFixed(2) || '0.00'}`}
                sub={`≈ USD ${((portfolio?.total_value_kes || 0) / 130).toFixed(3)}`} />
              <MetricCard icon={treeOutline}    color="#c8ff6b"
                title="EV TRIPS"
                value={String(portfolio?.total_trips || 0)}
                sub="Go Green rides" />
            </>
          )}
        </div>

        {/* VM0038 formula box */}
        {showFormula && (
          <IonCard className="gg-carbon__formula-card">
            <IonCardContent>
              <div className="gg-carbon__formula-title">VM0038 FORMULA</div>
              <div className="gg-carbon__formula">
                <div><b>BE</b> = VKT × {VM0038_PARAMS.AFEC} × {VM0038_PARAMS.EF_PETROL} × {VM0038_PARAMS.WTT_PETROL}</div>
                <div><b>PE</b> = (kWh ÷ {VM0038_PARAMS.ETA_L2}) × {VM0038_PARAMS.EF_GRID}</div>
                <div><b>ER</b> = BE − PE − {VM0038_PARAMS.LEAKAGE * 100}% leakage</div>
                <div><b>VCU</b> = ER × {(1-VM0038_PARAMS.VCS_BUFFER).toFixed(1)} ÷ 1000</div>
                <div className="gg-carbon__formula-note">
                  Kenya grid EF = <b>0.061 kgCO₂/kWh</b> · IEA 2024 · &gt;90% renewable<br/>
                  Additionality: VMD0049 positive list ✅ · Kenya EV &lt;5%
                </div>
              </div>
            </IonCardContent>
          </IonCard>
        )}

        {/* CO₂ saved bar */}
        {portfolio && portfolio.total_co2_kg > 0 && (
          <IonCard className="gg-carbon__progress-card">
            <IonCardContent>
              <div className="gg-carbon__progress-row">
                <span>Towards next VCU (1 tCO₂e)</span>
                <span className="gg-carbon__progress-pct">
                  {Math.min(100, (portfolio.total_co2_kg / 1000 * 100)).toFixed(2)}%
                </span>
              </div>
              <div className="gg-carbon__progress-track">
                <div
                  className="gg-carbon__progress-fill"
                  style={{ width: `${Math.min(100, portfolio.total_co2_kg / 1000 * 100)}%` }}
                />
              </div>
              <div className="gg-carbon__progress-sub">
                {portfolio.total_co2_kg.toFixed(4)} / 1.0000 tCO₂e accumulated
              </div>
            </IonCardContent>
          </IonCard>
        )}

        {/* Trip ledger */}
        <div className="gg-carbon__section-label">TRIP LEDGER</div>
        {loading ? (
          <div style={{ padding: '0 16px' }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <IonCard key={i}>
                <IonCardContent>
                  <IonSkeletonText animated style={{ width: '80%' }} />
                  <IonSkeletonText animated style={{ width: '50%', marginTop: 6 }} />
                </IonCardContent>
              </IonCard>
            ))}
          </div>
        ) : (
          <div className="gg-carbon__ledger">
            {(portfolio?.entries || []).slice().reverse().map(entry => (
              <TripLedgerRow key={entry.entry_id} entry={entry} />
            ))}
            {(!portfolio?.entries?.length) && (
              <div className="gg-carbon__empty">
                <IonIcon icon={leafOutline} style={{ fontSize: 40, color: 'var(--gg-dim)' }} />
                <p>No trips yet. Take your first EV ride to start earning VCUs!</p>
              </div>
            )}
          </div>
        )}

        <div style={{ height: 24 }} />
      </IonContent>
    </IonPage>
  );
};

// ── Metric card ───────────────────────────────────────────────────────────────
const MetricCard: React.FC<{
  icon: string; color: string; title: string; value: string; sub: string;
}> = ({ icon, color, title, value, sub }) => (
  <IonCard className="gg-carbon__metric-card">
    <IonCardContent>
      <IonIcon icon={icon} style={{ color, fontSize: 22 }} />
      <div className="gg-carbon__metric-title">{title}</div>
      <div className="gg-carbon__metric-value" style={{ color }}>{value}</div>
      <div className="gg-carbon__metric-sub">{sub}</div>
    </IonCardContent>
  </IonCard>
);

// ── Trip ledger row ───────────────────────────────────────────────────────────
const TripLedgerRow: React.FC<{ entry: CarbonLedgerEntry }> = ({ entry }) => (
  <div className="gg-carbon__ledger-row">
    <div className="gg-carbon__ledger-icon">🚗</div>
    <div className="gg-carbon__ledger-body">
      <div className="gg-carbon__ledger-title">
        {entry.distance_km.toFixed(1)} km EV Ride
      </div>
      <div className="gg-carbon__ledger-sub">
        {new Date(entry.timestamp * 1000).toLocaleDateString()} · {entry.charger_type} charger
      </div>
    </div>
    <div className="gg-carbon__ledger-right">
      <div className="gg-carbon__ledger-vcu">{entry.net_vcu.toFixed(8)}</div>
      <div className="gg-carbon__ledger-kes">KSh {entry.vcu_value_kes.toFixed(4)}</div>
    </div>
  </div>
);

// ── Demo portfolio ────────────────────────────────────────────────────────────
function generateDemoPortfolio(phone: string): PortfolioSummary {
  const trips = [8.4, 12.1, 5.7, 18.6, 9.4];
  const entries: CarbonLedgerEntry[] = trips.map((km, i) => {
    const be  = km * 0.09 * 2.296 * 1.19;
    const pe  = (km * 0.18 / 0.9) * 0.061;
    const net = Math.max(be - pe, 0) * 0.97;
    const vcu = (net / 1000) * 0.9;
    return {
      entry_id:         `demo-${i}`,
      trip_id:          `GG-${1000 + i}`,
      distance_km:      km,
      net_vcu:          vcu,
      vcu_value_kes:    vcu * 1625,
      net_reduction_kg: net,
      timestamp:        (Date.now() / 1000) - (i * 86400),
      vehicle_category: 'psv_passenger_car',
      charger_type:     'L2',
    };
  });
  const totalVcu = entries.reduce((s, e) => s + e.net_vcu, 0);
  const totalKg  = entries.reduce((s, e) => s + e.net_reduction_kg, 0);
  return {
    phone,
    total_trips:     entries.length,
    total_vcu:       totalVcu,
    total_co2_kg:    totalKg,
    total_value_kes: totalVcu * 1625,
    entries,
  };
}

export default CarbonPage;
