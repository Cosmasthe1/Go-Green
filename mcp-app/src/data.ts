// ─── Go Green shared data layer ─────────────────────────────────────────────
// Used by both the MCP server (Node.js) and the MCP App UI (browser bundle)

export interface Provider {
  name: string;
  slug: string;
  color: string;
  textColor: string;
  rideType: string;
  models: string[];
  baseFare: number;   // KES
  ratePerKm: number;  // KES
  deliveryMin: [number, number];
  priceMult: number;
}

export interface RideOffer {
  provider: string;
  slug: string;
  color: string;
  textColor: string;
  rideType: string;
  evModel: string;
  distanceKm: number;
  etaMin: number;
  durationMin: number;
  priceKes: number;
  surge: number;
  driverName: string;
  driverRating: number;
  driverPhone: string;
  plate: string;
  co2SavedG: number;
  promoCode: string;
  dealScore: number;
  badge: string;
}

export interface CarbonResult {
  distanceKm: number;
  baselineKg: number;
  projectKg: number;
  netKg: number;
  netVcu: number;
  vcuValueKes: number;
  treesEquiv: number;
  petrolSavedL: number;
  methodology: string;
}

export interface TripRecord {
  tripId: string;
  phone: string;
  pickup: string;
  destination: string;
  provider: string;
  priceKes: number;
  distanceKm: number;
  carbon: CarbonResult;
  timestamp: number;
}

// ── Nairobi landmark coordinates ────────────────────────────────────────────
export const NAIROBI_PLACES: Record<string, [number, number]> = {
  "cbd":           [-1.2833, 36.8172],
  "westlands":     [-1.2636, 36.8030],
  "karen":         [-1.3180, 36.7070],
  "kilimani":      [-1.2897, 36.7836],
  "parklands":     [-1.2600, 36.8140],
  "upperhill":     [-1.2998, 36.8197],
  "gigiri":        [-1.2300, 36.8100],
  "lavington":     [-1.2789, 36.7730],
  "langata":       [-1.3600, 36.7340],
  "south b":       [-1.3200, 36.8340],
  "kasarani":      [-1.2180, 36.8970],
  "ruaka":         [-1.2030, 36.7680],
  "jkia":          [-1.3192, 36.9275],
  "airport":       [-1.3192, 36.9275],
  "village market":[-1.2280, 36.8030],
  "two rivers":    [-1.1940, 36.7970],
  "garden city":   [-1.2180, 36.8850],
  "sarit":         [-1.2620, 36.8060],
  "yaya":          [-1.2950, 36.7880],
  "galleria":      [-1.3400, 36.7600],
  "junction":      [-1.3050, 36.7820],
};

// ── EV Providers ─────────────────────────────────────────────────────────────
export const PROVIDERS: Provider[] = [
  { name:"Uber",        slug:"uber",   color:"#1a1a1a", textColor:"#fff",   rideType:"Uber Green",  models:["Tesla Model 3","Nissan Leaf"],         baseFare:120, ratePerKm:55, deliveryMin:[1,5],   priceMult:1.00 },
  { name:"Bolt",        slug:"bolt",   color:"#34D186", textColor:"#000",   rideType:"Bolt EV",     models:["BYD Atto 3","MG ZS EV"],               baseFare:90,  ratePerKm:42, deliveryMin:[2,7],   priceMult:0.88 },
  { name:"Yego",        slug:"yego",   color:"#FF6B00", textColor:"#fff",   rideType:"Yego EV",     models:["Hyundai IONIQ 5","BYD Dolphin"],        baseFare:100, ratePerKm:48, deliveryMin:[2,7],   priceMult:1.00 },
  { name:"Faras",       slug:"faras",  color:"#1A56DB", textColor:"#fff",   rideType:"Faras Green", models:["Volkswagen ID.4","MG4 EV"],             baseFare:85,  ratePerKm:40, deliveryMin:[3,8],   priceMult:0.97 },
  { name:"Little Cabs", slug:"little", color:"#FECC00", textColor:"#1a1a1a",rideType:"Little EV",   models:["Nissan Leaf","BYD e6"],                 baseFare:95,  ratePerKm:45, deliveryMin:[1,4],   priceMult:1.05 },
  { name:"Wasili",      slug:"wasili", color:"#7C3AED", textColor:"#fff",   rideType:"Wasili EV",   models:["BYD Atto 3","Great Wall ORA"],          baseFare:80,  ratePerKm:38, deliveryMin:[1,3],   priceMult:0.75 },
  { name:"Weego",       slug:"weego",  color:"#059669", textColor:"#fff",   rideType:"Weego EV",    models:["BYD Yuan Plus","Geely Geometry C"],     baseFare:88,  ratePerKm:44, deliveryMin:[2,6],   priceMult:1.00 },
];

// ── Verra VM0038 v1.0 constants ───────────────────────────────────────────────
export const VM0038 = {
  EF_GRID_KG_PER_KWH:  0.061,     // Kenya IEA 2024
  EF_PETROL_KG_PER_L:  2.296,
  EF_DIESEL_KG_PER_L:  2.703,
  WTT_PETROL:          1.19,
  ETA_L2:              0.900,
  AFEC_PSV_L_PER_KM:   0.090,     // PSV passenger car baseline
  EV_KWH_PER_KM:       0.180,     // BYD/Tesla city consumption
  LEAKAGE_PCT:         0.03,
  VCS_BUFFER_PCT:      0.10,
  VCU_PRICE_KES:       1625.0,    // ~$12.50 @ 130 KES/USD
  TREES_PER_TCO2:      45,
} as const;

// ── Pure calculation functions (shared browser/node) ─────────────────────────
export function haversineKm(lat1:number,lon1:number,lat2:number,lon2:number):number {
  const R=6371, p1=lat1*Math.PI/180, p2=lat2*Math.PI/180;
  const dp=(lat2-lat1)*Math.PI/180, dl=(lon2-lon1)*Math.PI/180;
  const a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
  return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
}

export function calcVM0038(distKm:number):CarbonResult {
  const { EF_PETROL_KG_PER_L, WTT_PETROL, AFEC_PSV_L_PER_KM, EV_KWH_PER_KM,
          EF_GRID_KG_PER_KWH, ETA_L2, LEAKAGE_PCT, VCS_BUFFER_PCT,
          VCU_PRICE_KES, TREES_PER_TCO2 } = VM0038;
  const be    = distKm * AFEC_PSV_L_PER_KM * EF_PETROL_KG_PER_L * WTT_PETROL;
  const pe    = (distKm * EV_KWH_PER_KM / ETA_L2) * EF_GRID_KG_PER_KWH;
  const gross = Math.max(be - pe, 0);
  const net   = gross * (1 - LEAKAGE_PCT);
  const vcu   = (net / 1000) * (1 - VCS_BUFFER_PCT);
  return {
    distanceKm:    +distKm.toFixed(2),
    baselineKg:    +be.toFixed(4),
    projectKg:     +pe.toFixed(4),
    netKg:         +net.toFixed(4),
    netVcu:        +vcu.toFixed(8),
    vcuValueKes:   +(vcu * VCU_PRICE_KES).toFixed(4),
    treesEquiv:    +(vcu * TREES_PER_TCO2).toFixed(4),
    petrolSavedL:  +(distKm * AFEC_PSV_L_PER_KM).toFixed(3),
    methodology:   "Verra VM0038 v1.0",
  };
}

export function geocode(text:string):[number,number]|null {
  const t=text.toLowerCase().trim();
  for(const [k,v] of Object.entries(NAIROBI_PLACES)){
    if(t.includes(k)||k.includes(t)) return v;
  }
  return null;
}

export function parseRoute(text:string):{pickup:string,dest:string} {
  const t=text.toLowerCase();
  for(const w of ["to","->","→","going to","take me to","head to","drop me at"]){
    const i=t.indexOf(w);
    if(i>-1) return {pickup:text.slice(0,i).trim()||"Current location",dest:text.slice(i+w.length).trim()};
  }
  return {pickup:"Current location",dest:text};
}

export function generateOffers(distKm:number):RideOffer[] {
  const drivers=["James K.","Amina W.","Peter N.","Grace O.","Samuel M.","Brian T.","Lydia C."];
  const plates=["KDA","KDB","KBZ","KCA","KCB"];
  const vary=(v:number,p=0.22)=>v*(1+(Math.random()-.5)*2*p);

  const offers = PROVIDERS.map(p=>{
    const price=Math.round(vary((p.baseFare+p.ratePerKm*distKm)*p.priceMult)/10)*10;
    const surge=Math.random()<.2?[1.2,1.5][Math.floor(Math.random()*2)]:1.0;
    const [dmin,dmax]=p.deliveryMin;
    const eta=dmin+Math.floor(Math.random()*(dmax-dmin+1));
    return {
      provider:p.name, slug:p.slug, color:p.color, textColor:p.textColor,
      rideType:p.rideType,
      evModel:p.models[Math.floor(Math.random()*p.models.length)],
      distanceKm:+distKm.toFixed(2),
      etaMin:eta,
      durationMin:Math.floor(distKm/30*60)+Math.floor(Math.random()*8+2),
      priceKes:Math.round(price*surge/10)*10,
      surge, co2SavedG:Math.round(distKm*120),
      driverName:drivers[Math.floor(Math.random()*drivers.length)],
      driverRating:+(3.5+Math.random()*1.5).toFixed(1),
      driverPhone:`+2547${Math.floor(Math.random()*90000000+10000000)}`,
      plate:`${plates[Math.floor(Math.random()*plates.length)]} ${Math.floor(Math.random()*900+100)} ${String.fromCharCode(65+Math.floor(Math.random()*8))}`,
      promoCode:Math.random()<.2?["GREEN10","EVRIDE5"][Math.floor(Math.random()*2)]:"",
      dealScore:0, badge:"",
    } as RideOffer;
  });

  // Score and rank
  const prices=offers.map(o=>o.priceKes);
  const mn=Math.min(...prices),mx=Math.max(...prices);
  offers.forEach(o=>{
    const ps=mx>mn?100*(mx-o.priceKes)/(mx-mn):50;
    const rs=(o.driverRating/5)*100;
    const ds=Math.max(0,100-o.etaMin*4);
    o.dealScore=Math.round(.45*ps+.30*rs+.25*ds);
  });
  offers.sort((a,b)=>b.dealScore-a.dealScore);

  const biP=offers.indexOf(offers.reduce((a,b)=>a.priceKes<b.priceKes?a:b));
  const biD=offers.indexOf(offers.reduce((a,b)=>a.etaMin<b.etaMin?a:b));
  const biR=offers.indexOf(offers.reduce((a,b)=>a.driverRating>b.driverRating?a:b));
  offers.forEach((o,i)=>{
    if(i===0)                   o.badge="🏆 Best Deal";
    else if(i===biP)            o.badge="💰 Cheapest";
    else if(i===biD)            o.badge="⚡ Fastest";
    else if(i===biR)            o.badge="⭐ Top Rated";
    else if(["Wasili","Faras","Yego","Little Cabs","Weego"].includes(o.provider)) o.badge="🌍 Local Pick";
  });
  return offers;
}
