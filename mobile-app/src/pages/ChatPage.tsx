import React, { useState, useEffect, useRef } from 'react';
import {
  IonPage, IonContent, IonHeader, IonToolbar, IonTitle,
  IonFooter, IonButton, IonIcon, IonSpinner, IonChip,
  IonText, IonRippleEffect,
} from '@ionic/react';
import { sendOutline, refreshOutline } from 'ionicons/icons';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { api, WhatsAppMessage, RideOffer, socket, WSEvent } from '../services/api';
import './ChatPage.css';

const QUICK_REPLIES = [
  'Hi', 'Westlands to Karen', 'CBD to JKIA',
  'Kilimani to Gigiri', '1', 'YES', 'NO', 'MENU',
];

const ChatPage: React.FC = () => {
  const phone    = localStorage.getItem('gg_phone') || '+254712345678';
  const [msgs,   setMsgs]   = useState<WhatsAppMessage[]>([]);
  const [input,  setInput]  = useState('');
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [offers,  setOffers]  = useState<RideOffer[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  // ── Initial load ────────────────────────────────────────────────────────────
  useEffect(() => {
    loadHistory();

    // WebSocket: sync real-time updates from backend session
    socket.connect(phone);
    const unsub = socket.on((evt: WSEvent) => {
      if (evt.type === 'message') {
        const m = evt.payload as WhatsAppMessage;
        setMsgs(prev => [...prev, m]);
        if ((m as any).offers?.length) setOffers((m as any).offers);
        scrollDown();
      }
    });
    return () => {
      unsub();
      socket.disconnect();
    };
  }, []);

  useEffect(() => { scrollDown(); }, [msgs]);

  const scrollDown = () =>
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 80);

  const loadHistory = async () => {
    setSyncing(true);
    try {
      const history = await api.getWhatsAppHistory(phone);
      if (history.length) setMsgs(history);
      else addGreeting();
    } catch {
      addGreeting();
    } finally {
      setSyncing(false);
    }
  };

  const addGreeting = () => {
    setMsgs([{
      id: 'greet',
      role: 'bot',
      text: '🌿 *Welcome to Go Green!*\n\nI\'ll book you a clean ⚡ EV ride.\n\nJust tell me where you\'re going:\n_e.g. "Westlands to Karen" or "Take me to JKIA"_',
      timestamp: Date.now(),
    }]);
  };

  const sendMessage = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg) return;

    await Haptics.impact({ style: ImpactStyle.Light });
    setInput('');

    // Optimistic user bubble
    const userMsg: WhatsAppMessage = {
      id: `u-${Date.now()}`, role: 'user', text: msg, timestamp: Date.now(),
    };
    setMsgs(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await api.sendWhatsAppMessage(phone, msg);
      const botMsg: WhatsAppMessage = {
        id: `b-${Date.now()}`, role: 'bot',
        text: res.reply, timestamp: Date.now(),
        offers: res.offers,
      };
      setMsgs(prev => [...prev, botMsg]);
      if (res.offers?.length) setOffers(res.offers);
    } catch {
      // Fallback: simple local router
      const reply = localRouter(msg);
      setMsgs(prev => [...prev, {
        id: `b-${Date.now()}`, role: 'bot', text: reply, timestamp: Date.now(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <IonPage className="gg-chat-page">
      <IonHeader translucent>
        <IonToolbar>
          <div className="gg-chat-header">
            <div className="gg-chat-avatar">🌿</div>
            <div>
              <div className="gg-chat-name">Go Green</div>
              <div className="gg-chat-status">
                {syncing ? 'Syncing…' : '● Online · EV Agent'}
              </div>
            </div>
            <IonButton fill="clear" onClick={loadHistory} slot="end" size="small">
              <IonIcon icon={refreshOutline} />
            </IonButton>
          </div>
        </IonToolbar>
      </IonHeader>

      <IonContent fullscreen className="gg-chat-content">
        <div className="gg-chat-msgs">
          {msgs.map(m => (
            <MessageBubble key={m.id} msg={m} onPickRide={pickRide} />
          ))}
          {loading && (
            <div className="gg-chat-typing">
              <div className="gg-chat-typing-dot" />
              <div className="gg-chat-typing-dot" />
              <div className="gg-chat-typing-dot" />
            </div>
          )}
          <div ref={endRef} />
        </div>
      </IonContent>

      {/* Quick replies */}
      <div className="gg-chat-qr-row">
        {QUICK_REPLIES.map(q => (
          <button
            key={q}
            className="gg-chat-qr ion-activatable"
            onClick={() => sendMessage(q)}
          >
            <IonRippleEffect />
            {q}
          </button>
        ))}
      </div>

      <IonFooter className="gg-chat-footer">
        <div className="gg-chat-input-row">
          <input
            className="gg-chat-input"
            placeholder="Type a message…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
          />
          <button
            className="gg-chat-send"
            onClick={() => sendMessage()}
            disabled={loading}
          >
            {loading ? <IonSpinner name="dots" /> : <IonIcon icon={sendOutline} />}
          </button>
        </div>
      </IonFooter>
    </IonPage>
  );

  function pickRide(offer: RideOffer) {
    localStorage.setItem('gg_chosen_offer', JSON.stringify(offer));
    window.location.href = '/booking';
  }
};

// ── Message bubble ────────────────────────────────────────────────────────────
const MessageBubble: React.FC<{
  msg: WhatsAppMessage;
  onPickRide: (o: RideOffer) => void;
}> = ({ msg, onPickRide }) => {
  const isUser = msg.role === 'user';
  const formatted = msg.text
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\*([^*]+)\*/g,     '<b>$1</b>')
    .replace(/_([^_]+)_/g,       '<em>$1</em>');

  return (
    <div className={`gg-msg gg-msg--${isUser ? 'user' : 'bot'}`}>
      <div
        className="gg-msg__bubble"
        dangerouslySetInnerHTML={{ __html: formatted }}
      />
      {msg.offers && msg.offers.length > 0 && (
        <div className="gg-msg__offers">
          {msg.offers.slice(0, 3).map((o, i) => (
            <button
              key={i}
              className="gg-msg__offer-chip ion-activatable"
              style={{ borderColor: o.color + '55' }}
              onClick={() => onPickRide(o)}
            >
              <IonRippleEffect />
              <span
                className="gg-msg__offer-logo"
                style={{ background: o.color, color: o.color === '#FECC00' ? '#000' : '#fff' }}
              >
                {o.provider}
              </span>
              <span className="gg-msg__offer-price" style={{ color: o.color }}>
                KSh {o.price_kes.toLocaleString()}
              </span>
              <span className="gg-msg__offer-eta">⏱ {o.eta_min}m</span>
            </button>
          ))}
        </div>
      )}
      <div className="gg-msg__time">
        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
};

// ── Local fallback router (no backend) ───────────────────────────────────────
function localRouter(text: string): string {
  const t = text.toLowerCase().trim();
  if (['hi','hello','hey','menu','start'].includes(t))
    return '🌿 *Welcome to Go Green!*\n\nTell me where you\'re going:\n_e.g. "Westlands to Karen"_';
  if (t.includes(' to ') || t.startsWith('take me') || t.startsWith('drop me'))
    return `🔍 Searching EV rides for:\n*"${text}"*\n\nOpening ride results → tap the ⚡ Rides tab`;
  if (['yes','y','confirm'].includes(t))
    return '💳 Sending M-Pesa STK push to your phone…\nEnter your PIN to pay.';
  if (['no','cancel'].includes(t))
    return 'No problem! Send a new destination when ready 🌿';
  return `I received: *"${text}"*\n\nUse the search bar above for fastest results, or I can help you via WhatsApp.`;
}

export default ChatPage;
