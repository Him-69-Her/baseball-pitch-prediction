/* =============================================================
   TINY-HUB · LIVE MAP
   Light cartography. All features as togglable layers.

   NETWORK
   ✓ Districts (12 McHenry communities — real geographic)
   ✓ Trade flows (animated polylines — synthetic)
   ✓ Distance corridors (between district pairs — geometric)
   ✓ Solar heatmap (county scatter — decorative)

   OVERLAYS
   ✓ Air Quality (Google AQ tiles — real)
   ✓ Photorealistic 3D (Map Tiles API — real)

   REGISTERED PROSPECTS
   ✓ Walmart / Jewel-Osco / Amazon / Schools
     - Places API · location lookup
     - Solar API · per-building roof analysis
     - Footprints rendered as gold polygons
     - Click → full info panel · Hover → tooltip
   ============================================================= */

const { useState, useEffect, useRef, useMemo } = React;
const { TweaksPanel, TweakSection, TweakSlider, useTweaks } = window.Tweaks;

// ─── Display helpers ──────────────────────────────────────────
const dash = '—';
const fmt = {
  num: (v, d = 0) => v == null ? dash : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }),
  fixed: (v, d = 2) => v == null ? dash : Number(v).toFixed(d),
  money: v => v == null ? dash : '$' + Number(v).toLocaleString(),
  kwh: v => v == null ? dash : Number(v).toLocaleString() + ' kWh',
  relativeTime: iso => {
    if (!iso) return dash;
    const ago = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (ago < 60) return ago + 's ago';
    if (ago < 3600) return Math.floor(ago / 60) + 'm ago';
    if (ago < 86400) return Math.floor(ago / 3600) + 'h ago';
    return Math.floor(ago / 86400) + 'd ago';
  }
};

// ─── McHenry County rough bounds ──────────────────────────────
const COUNTY = {
  center: { lat: 42.30, lng: -88.40 },
  north: 42.50, south: 42.10, east: -88.10, west: -88.65
};

// ─── Customer categories ──────────────────────────────────────
const CUSTOMER_CATEGORIES = {
  walmart: {
    label: 'Walmart',
    color: '#0071ce', darkColor: '#003478',
    letter: 'W',
    estKwhPerDay: 28000,
    type: 'big-box retail',
    searchQuery: 'Walmart in McHenry County, Illinois'
  },
  jewel: {
    label: 'Jewel-Osco',
    color: '#d6001c', darkColor: '#7a0011',
    letter: 'J',
    estKwhPerDay: 4500,
    type: 'grocery / supermarket',
    searchQuery: 'Jewel-Osco in McHenry County, Illinois'
  },
  amazon: {
    label: 'Amazon',
    color: '#ff9900', darkColor: '#b86b00',
    letter: 'A',
    estKwhPerDay: 95000,
    type: 'logistics / fulfillment',
    searchQuery: 'Amazon warehouse in McHenry County, Illinois'
  },
  schools: {
    label: 'Schools',
    color: '#2e7d32', darkColor: '#1b5e20',
    letter: 'S',
    estKwhPerDay: 3500,
    type: 'K-12 / public',
    searchQuery: 'public school in McHenry County, Illinois',
    pageSize: 20
  }
};

// ─── Concurrency limiter (Solar API) ──────────────────────────
async function batchFetch(items, fn, concurrency = 6) {
  const results = new Array(items.length);
  let idx = 0;
  async function worker() {
    while (idx < items.length) {
      const i = idx++;
      try { results[i] = await fn(items[i]); }
      catch (e) {
        console.warn('batchFetch item failed:', items[i], e);
        results[i] = null;
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}

function useMapsReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (window.__MAPS_READY && window.google && window.google.maps) {
      setReady(true);
      return;
    }
    const id = setInterval(() => {
      if (window.__MAPS_READY && window.google && window.google.maps) {
        setReady(true);
        clearInterval(id);
      }
    }, 80);
    return () => clearInterval(id);
  }, []);
  return ready;
}

// ─── Light cartography style ──────────────────────────────────
const LIGHT_MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#f4f1ea' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#f4f1ea' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#5a6068' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#dcd6c4' }] },
  { featureType: 'administrative.country', elementType: 'labels.text.fill', stylers: [{ color: '#3a3f47' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#234e6c' }] },
  { featureType: 'administrative.land_parcel', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry.fill', stylers: [{ color: '#ece8de' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#d4cfc1' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#76808b' }] },
  { featureType: 'road.highway', elementType: 'geometry.fill', stylers: [{ color: '#e6dfc8' }] },
  { featureType: 'road.highway', elementType: 'geometry.stroke', stylers: [{ color: '#d6cfa8' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cee0eb' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#5a8aa6' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f4f1ea' }] }
];

// ─── Marker icons ─────────────────────────────────────────────
function makeDistrictMarker(size = 32, color = '#ff9500', outline = '#7a3f00') {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 3}" fill="${color}" stroke="${outline}" stroke-width="2.5"/>
      <circle cx="${size/2}" cy="${size/2}" r="${size/5}" fill="#fff" opacity="0.9"/>
    </svg>`;
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
}

function makeCustomerMarker(size = 28, color = '#0071ce', outline = '#003478', letter = 'W') {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 2}" fill="${color}" stroke="${outline}" stroke-width="2"/>
      <text x="${size/2}" y="${size/2 + 4}"
            font-family="Inter, system-ui, Arial Black, sans-serif"
            font-size="${size * 0.42}" font-weight="900" fill="#fff" text-anchor="middle">${letter}</text>
    </svg>`;
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
}

// ─── Pilot state hook · poll /mchenry/api/pilot every 5s ──────
function usePilotState() {
  const [pilot, setPilot] = useState({ running: false, startedAt: null, stoppedAt: null, lastActor: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const fetchState = async () => {
    try {
      const r = await fetch('/mchenry/api/pilot');
      if (r.ok) setPilot(await r.json());
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, 5000);
    return () => clearInterval(id);
  }, []);

  const toggle = async (action) => {
    setBusy(true); setError(null);
    try {
      const r = await fetch('/mchenry/api/pilot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setPilot(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return { pilot, busy, error, start: () => toggle('start'), stop: () => toggle('stop') };
}

// ─── Pilot Control · top-right floating button ────────────────
function PilotControl({ pilot, busy, error, onStart, onStop }) {
  const [confirming, setConfirming] = useState(false);
  useEffect(() => { if (!pilot.running) setConfirming(false); }, [pilot.running]);

  if (confirming && pilot.running) {
    return (
      <div className="pilot pilot--confirm">
        <div className="pilot__head">
          <div className="pilot__title">Stop pilot?</div>
          <div className="pilot__sub">Halts trade routing across all 12 districts</div>
        </div>
        <div className="pilot__btns">
          <button className="pilot__btn pilot__btn--ghost" onClick={() => setConfirming(false)}>Cancel</button>
          <button className="pilot__btn pilot__btn--danger" disabled={busy}
                  onClick={() => { onStop(); setConfirming(false); }}>
            {busy ? 'Stopping…' : '■ STOP'}
          </button>
        </div>
      </div>
    );
  }

  if (pilot.running) {
    return (
      <div className="pilot pilot--running">
        <div className="pilot__status">
          <span className="pilot__dot" />
          <div>
            <div className="pilot__state">LIVE</div>
            <div className="pilot__since">started {fmt.relativeTime(pilot.startedAt)}</div>
          </div>
        </div>
        <button className="pilot__btn pilot__btn--stop" onClick={() => setConfirming(true)} disabled={busy}>
          ■ STOP PILOT
        </button>
      </div>
    );
  }

  return (
    <div className="pilot pilot--stopped">
      <div className="pilot__status">
        <span className="pilot__dot" />
        <div>
          <div className="pilot__state">STANDBY</div>
          <div className="pilot__since">
            {pilot.stoppedAt ? `stopped ${fmt.relativeTime(pilot.stoppedAt)}` : 'never started'}
          </div>
        </div>
      </div>
      <button className="pilot__btn pilot__btn--start" onClick={onStart} disabled={busy}>
        {busy ? 'Starting…' : '▶ START PILOT'}
      </button>
      {error && <div className="pilot__error">{error}</div>}
    </div>
  );
}

// ─── Nav ──────────────────────────────────────────────────────
function NavBar() {
  return (
    <nav className="nav">
      <div className="nav__brand flicker">Tiny Hub: <span style={{ color: '#fff' }}>McHenry County</span></div>
      <div className="nav__links">
        <a className="nav__link is-active" href="live-map.html">Map</a>
        <a className="nav__link" href="analytics-console.html">Console</a>
        <a className="nav__link" href="solver.html">Solver</a>
        <a className="nav__link" href="final-report.html">Final Report</a>
        <a className="nav__link" href="glossary.html">Glossary</a>
      </div>
      <div className="nav__spacer" />
    </nav>
  );
}

// ─── Layer drawer ─────────────────────────────────────────────
function LayerRow({ name, sub, on, onToggle, disabled }) {
  return (
    <div
      className={`layer-row ${on ? 'is-on' : ''} ${disabled ? 'is-disabled' : ''}`}
      onClick={() => !disabled && onToggle(!on)}
    >
      <div>
        <div className="layer-row__name">{name}</div>
        {sub && <div className="layer-row__sub">{sub}</div>}
      </div>
      <div className="layer-toggle" />
    </div>
  );
}

function CustomerSubRow({ category, on, onToggle, count, loading, error }) {
  const cat = CUSTOMER_CATEGORIES[category];
  return (
    <div className={`cust-sub ${on ? 'is-on' : ''}`} onClick={() => onToggle(!on)}>
      <div className="cust-sub__chip" style={{ background: cat.color, borderColor: cat.darkColor }}>
        {cat.letter}
      </div>
      <div className="cust-sub__name">
        {cat.label}
        {error && <div className="cust-sub__err">{error.substring(0, 30)}</div>}
      </div>
      <div className="cust-sub__count">
        {loading ? '…' : count != null ? count : ''}
      </div>
      <div className="layer-toggle" />
    </div>
  );
}

function LayerDrawer({ layers, onToggle, zoom, custEnabled, onCustToggle, custCounts, custLoading, custErrors }) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`layer-drawer ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="layer-drawer__head" onClick={() => setCollapsed(c => !c)}>
        <div className="layer-drawer__title">Map Layers</div>
        <div className="layer-drawer__caret">▾</div>
      </div>
      <div className="layer-drawer__body">

        <div className="layer-drawer__section">
          <div className="layer-drawer__section-head">Network</div>
          <LayerRow name="Districts" sub="real · 12 communities"
            on={layers.districts} onToggle={v => onToggle('districts', v)} />
          <LayerRow name="Trade flows" sub="synthetic · animated"
            on={layers.flows} onToggle={v => onToggle('flows', v)} />
          <LayerRow name="Distance corridors" sub="geometric · between districts"
            on={layers.corridors} onToggle={v => onToggle('corridors', v)} />
          <LayerRow name="Solar heatmap" sub="decorative · ambient scatter"
            on={layers.solarHeatmap} onToggle={v => onToggle('solarHeatmap', v)} />
        </div>

        <div className="layer-drawer__section">
          <div className="layer-drawer__section-head">Overlays</div>
          <LayerRow name="Air Quality" sub="real · Google AQ tiles"
            on={layers.airQuality} onToggle={v => onToggle('airQuality', v)} />
          <LayerRow name="Photorealistic 3D"
            sub={zoom < 16 ? `real · zoom ≥ 16 (now ${zoom})` : 'real · Map Tiles API'}
            on={layers.tiles3d} onToggle={v => onToggle('tiles3d', v)}
            disabled={zoom < 16} />
        </div>

        <div className="layer-drawer__section">
          <div className="layer-drawer__section-head">Registered prospects</div>
          <div className="layer-drawer__section-sub">Footprints + per-building Solar API</div>
          {Object.keys(CUSTOMER_CATEGORIES).map(key => (
            <CustomerSubRow
              key={key}
              category={key}
              on={custEnabled[key]}
              onToggle={v => onCustToggle(key, v)}
              count={custCounts[key]}
              loading={custLoading[key]}
              error={custErrors[key]}
            />
          ))}
        </div>

      </div>
    </div>
  );
}

// ─── District info panel (no solar — that's per-building) ────
function DistrictInfoPanel({ district, snap, onClose }) {
  if (!district) return null;
  const districtSnap = (snap.districts || []).find(d => d.id === district.id);
  return (
    <div className="info-panel info-panel--district is-open">
      <div className="info-panel__head">
        <div>
          <div className="info-panel__id">{district.id} · DISTRICT</div>
          <div className="info-panel__name">{district.name}</div>
        </div>
        <button className="info-panel__close" onClick={onClose}>×</button>
      </div>
      <div className="info-panel__body">
        <div className="info-panel__metrics">
          <div className="info-metric">
            <div className="info-metric__lbl">Houses</div>
            <div className="info-metric__val">{fmt.num(districtSnap?.houses)}</div>
          </div>
          <div className="info-metric">
            <div className="info-metric__lbl">MWh / day</div>
            <div className="info-metric__val cyan">{fmt.fixed(districtSnap?.mwhDay, 1)}</div>
          </div>
          <div className="info-metric">
            <div className="info-metric__lbl">Saved · today</div>
            <div className="info-metric__val good">{fmt.money(districtSnap?.savedDay)}</div>
          </div>
          <div className="info-metric">
            <div className="info-metric__lbl">Status</div>
            <div className="info-metric__val">{districtSnap?.status?.toUpperCase() || dash}</div>
          </div>
        </div>
        <div className="info-hint">
          For per-building solar potential, toggle a Registered Prospects category.
        </div>
      </div>
    </div>
  );
}

function CustomerInfoPanel({ customer, onClose }) {
  if (!customer) return null;
  const cat = CUSTOMER_CATEGORIES[customer.category];
  const b = customer.building;
  return (
    <div className="info-panel info-panel--customer is-open">
      <div className="info-panel__head">
        <div style={{ minWidth: 0 }}>
          <div className="info-panel__id">
            <span className="cust-badge" style={{ background: cat.color }}>{cat.letter}</span>
            {' '}{cat.label.toUpperCase()} · <span style={{ color: 'var(--sun-1)' }}>REGISTERED</span>
          </div>
          <div className="info-panel__name">{customer.name}</div>
          <div className="info-panel__addr">{customer.address}</div>
        </div>
        <button className="info-panel__close" onClick={onClose}>×</button>
      </div>
      <div className="info-panel__body">
        <div className="info-panel__metrics">
          <div className="info-metric">
            <div className="info-metric__lbl">Type</div>
            <div className="info-metric__val" style={{ fontSize: '0.78rem' }}>{cat.type}</div>
          </div>
          <div className="info-metric">
            <div className="info-metric__lbl">Est. demand · daily</div>
            <div className="info-metric__val cyan">{fmt.kwh(cat.estKwhPerDay)}</div>
          </div>
        </div>

        {b ? (
          <div className="info-panel__solar">
            <h4>☀ Solar Potential · Google · per building</h4>
            <div className="solar-row"><span className="solar-row__k">Annual kWh potential</span><span className="solar-row__v">{fmt.kwh(b.maxKwh)}</span></div>
            <div className="solar-row"><span className="solar-row__k">Max panel count</span><span className="solar-row__v">{fmt.num(b.maxPanels)}</span></div>
            <div className="solar-row"><span className="solar-row__k">Sunshine hrs / yr</span><span className="solar-row__v">{fmt.num(b.sunshineHours)}</span></div>
            <div className="solar-row"><span className="solar-row__k">Roof area</span><span className="solar-row__v">{fmt.num(b.roofAreaM2)} m²</span></div>
            <div className="solar-row"><span className="solar-row__k">Carbon offset</span><span className="solar-row__v">{fmt.num(b.carbonOffsetKg)} kg CO₂/MWh</span></div>
            <div className="solar-row"><span className="solar-row__k">Peak shaving · monthly</span><span className="solar-row__v">~{Math.round(cat.estKwhPerDay * 30 * 0.18 / 1000)} MWh</span></div>
          </div>
        ) : (
          <div className="info-panel__solar">
            <h4>☀ Solar Potential</h4>
            <div className="solar-error">No detailed building data available for this location.</div>
          </div>
        )}

        <button className="cust-cta">▸ ADD TO ONBOARDING QUEUE</button>
        <div className="cust-disclaimer">
          Registered prospect · solar data via Google Building Insights API.
        </div>
      </div>
    </div>
  );
}

function HoverTooltip({ hover }) {
  if (!hover) return null;
  const cat = CUSTOMER_CATEGORIES[hover.category];
  const b = hover.building;
  return (
    <div className="map-tooltip" style={{ left: hover.x + 16, top: hover.y + 14 }}>
      <div className="map-tooltip__head">
        <span className="map-tooltip__chip" style={{ background: cat.color }}>{cat.letter}</span>
        <span className="map-tooltip__cat">{cat.label}</span>
      </div>
      <div className="map-tooltip__name">{hover.name}</div>
      {b && (
        <div className="map-tooltip__solar">
          <span>☀ {fmt.kwh(b.maxKwh)} / yr</span>
          <span>·</span>
          <span>{fmt.num(b.maxPanels)} panels</span>
        </div>
      )}
      <div className="map-tooltip__hint">click for details</div>
    </div>
  );
}

// ─── External API helpers ─────────────────────────────────────
async function fetchPlaces(query, pageSize = 10) {
  const key = window.TINYHUB_CONFIG?.mapsApiKey;
  if (!key) throw new Error('Missing API key');
  const r = await fetch('https://places.googleapis.com/v1/places:searchText', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': key,
      'X-Goog-FieldMask': 'places.displayName,places.location,places.formattedAddress,places.types,places.id'
    },
    body: JSON.stringify({
      textQuery: query,
      pageSize,
      locationBias: {
        circle: { center: COUNTY.center, radius: 30000 }
      }
    })
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Places API ${r.status}: ${text.substring(0, 100)}`);
  }
  const data = await r.json();
  return (data.places || []).map(p => ({
    id: p.id,
    name: p.displayName?.text || 'Unknown',
    address: p.formattedAddress || '',
    lat: p.location?.latitude,
    lng: p.location?.longitude,
    types: p.types || []
  })).filter(p => p.lat != null && p.lng != null);
}

async function fetchBuildingInsights(lat, lng) {
  const key = window.TINYHUB_CONFIG?.mapsApiKey;
  if (!key) throw new Error('Missing API key');
  const url = `https://solar.googleapis.com/v1/buildingInsights:findClosest`
    + `?location.latitude=${lat}&location.longitude=${lng}&requiredQuality=HIGH&key=${key}`;
  const r = await fetch(url);
  if (!r.ok) {
    if (r.status === 404) return null;
    throw new Error(`Solar API: ${r.status}`);
  }
  const data = await r.json();
  const sp = data?.solarPotential;
  if (!sp) return null;
  const configs = sp.solarPanelConfigs || [];
  const best = configs[configs.length - 1];
  return {
    boundingBox: data.boundingBox,
    roofSegments: sp.roofSegmentStats || [],
    maxKwh: Math.round(best?.yearlyEnergyDcKwh || (sp.maxArrayPanelsCount || 0) * 400),
    maxPanels: sp.maxArrayPanelsCount,
    sunshineHours: Math.round(sp.maxSunshineHoursPerYear || 0),
    roofAreaM2: Math.round(sp.wholeRoofStats?.areaMeters2 || 0),
    carbonOffsetKg: Math.round(sp.carbonOffsetFactorKgPerMwh || 0),
    postalCode: data.postalCode || ''
  };
}

// ─── Main App ─────────────────────────────────────────────────
function App() {
  const mapsReady = useMapsReady();
  const { pilot, busy: pilotBusy, error: pilotError, start: startPilot, stop: stopPilot } = usePilotState();
  const mapDivRef = useRef(null);
  const mapRef = useRef(null);

  const districtMarkersRef = useRef([]);
  const flowsRef = useRef([]);
  const corridorsRef = useRef([]);
  const solarHeatmapRef = useRef(null);
  const aqLayerRef = useRef(null);
  const customerMarkersRef = useRef({});
  const customerPolygonsRef = useRef({});

  const [snap, setSnap] = useState(() => window.TinyHubSim.snapshot());
  const [activeDistrict, setActiveDistrict] = useState(null);
  const [activeCustomer, setActiveCustomer] = useState(null);
  const [hover, setHover] = useState(null);
  const [zoom, setZoom] = useState(11);

  // Layers · districts + flows ON by default so map isn't empty
  const [layers, setLayers] = useState({
    districts: true,
    flows: true,
    corridors: false,
    solarHeatmap: false,
    airQuality: false,
    tiles3d: false
  });

  const [custEnabled, setCustEnabled] = useState({
    walmart: false, jewel: false, amazon: false, schools: false
  });
  const [custData, setCustData] = useState({});
  const [custLoading, setCustLoading] = useState({});
  const [custErrors, setCustErrors] = useState({});

  const setLayer = (key, val) => setLayers(s => ({ ...s, [key]: val }));

  const [tweaks, setTweak] = useTweaks('livemap', { tickRateMs: 1000 });
  useEffect(() => {
    const id = setInterval(() => {
      window.TinyHubSim.tick();
      setSnap(window.TinyHubSim.snapshot());
    }, tweaks.tickRateMs);
    return () => clearInterval(id);
  }, [tweaks.tickRateMs]);

  // Init map
  useEffect(() => {
    if (!mapsReady || !mapDivRef.current || mapRef.current) return;
    const map = new google.maps.Map(mapDivRef.current, {
      center: COUNTY.center, zoom: 11,
      mapTypeId: 'roadmap',
      styles: LIGHT_MAP_STYLE,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: 'greedy',
      backgroundColor: '#f4f1ea'
    });
    mapRef.current = map;
    map.addListener('zoom_changed', () => setZoom(map.getZoom()));
    setZoom(map.getZoom());
    document.querySelector('.map-loading')?.classList.add('is-hidden');
  }, [mapsReady]);

  // ─── District markers ────────────────────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    districtMarkersRef.current.forEach(m => m.setMap(null));
    districtMarkersRef.current = [];
    if (!layers.districts) return;

    (snap.districts || []).forEach(d => {
      const marker = new google.maps.Marker({
        position: { lat: d.lat, lng: d.lng },
        map,
        icon: {
          url: makeDistrictMarker(34, '#ff9500', '#7a3f00'),
          scaledSize: new google.maps.Size(34, 34),
          anchor: new google.maps.Point(17, 17)
        },
        title: `${d.id} · ${d.name}`,
        zIndex: 800
      });
      marker.addListener('click', () => {
        setActiveCustomer(null);
        setActiveDistrict(d);
        map.panTo({ lat: d.lat, lng: d.lng });
      });
      districtMarkersRef.current.push(marker);
    });
  }, [mapsReady, layers.districts, snap.districts]);

  // ─── Trade flows ─────────────────────────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    flowsRef.current.forEach(f => f.setMap(null));
    flowsRef.current = [];
    if (!layers.flows) return;
    const all = snap.districts || [];
    if (all.length < 2) return;

    const lineSymbol = {
      path: 'M 0,-1 0,1',
      strokeColor: '#0091a8',
      strokeOpacity: 0.85,
      scale: 3
    };

    all.forEach((a, i) => {
      const others = all.filter((_, j) => j !== i)
        .map(b => ({ b, d: Math.hypot(a.lat - b.lat, a.lng - b.lng) }))
        .sort((x, y) => x.d - y.d).slice(0, 2);
      others.forEach(({ b }) => {
        const line = new google.maps.Polyline({
          path: [{ lat: a.lat, lng: a.lng }, { lat: b.lat, lng: b.lng }],
          strokeOpacity: 0,
          icons: [{ icon: lineSymbol, offset: '0', repeat: '14px' }],
          map: mapRef.current,
          zIndex: 100
        });
        flowsRef.current.push(line);
      });
    });

    let count = 0;
    const id = window.setInterval(() => {
      count = (count + 2) % 200;
      flowsRef.current.forEach(line => {
        const icons = line.get('icons');
        if (icons && icons[0]) {
          icons[0].offset = count + '%';
          line.set('icons', icons);
        }
      });
    }, 60);
    return () => window.clearInterval(id);
  }, [mapsReady, layers.flows, snap.districts]);

  // ─── Distance corridors ─────────────────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    corridorsRef.current.forEach(c => c.setMap(null));
    corridorsRef.current = [];
    if (!layers.corridors) return;
    const all = snap.districts || [];
    for (let i = 0; i < all.length; i++) {
      for (let j = i + 1; j < all.length; j++) {
        const corridor = new google.maps.Polyline({
          path: [{ lat: all[i].lat, lng: all[i].lng }, { lat: all[j].lat, lng: all[j].lng }],
          strokeColor: '#a51c64',
          strokeOpacity: 0.18,
          strokeWeight: 1,
          map: mapRef.current,
          zIndex: 50
        });
        corridorsRef.current.push(corridor);
      }
    }
  }, [mapsReady, layers.corridors, snap.districts]);

  // ─── Solar heatmap (decorative scatter) ─────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    if (solarHeatmapRef.current) {
      solarHeatmapRef.current.setMap(null);
      solarHeatmapRef.current = null;
    }
    if (!layers.solarHeatmap) return;
    if (!google.maps.visualization) return;

    const points = [];
    const rng = (seed) => {
      let s = seed;
      return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    };
    const r = rng(42);
    for (let i = 0; i < 800; i++) {
      const lat = COUNTY.south + r() * (COUNTY.north - COUNTY.south);
      const lng = COUNTY.west + r() * (COUNTY.east - COUNTY.west);
      points.push({
        location: new google.maps.LatLng(lat, lng),
        weight: 0.3 + r() * 0.7
      });
    }

    solarHeatmapRef.current = new google.maps.visualization.HeatmapLayer({
      data: points,
      map: mapRef.current,
      radius: 22,
      opacity: 0.4,
      gradient: [
        'rgba(255, 255, 255, 0)',
        'rgba(255, 232, 156, 0.5)',
        'rgba(255, 195, 88, 0.7)',
        'rgba(255, 149, 0, 0.85)',
        'rgba(232, 90, 30, 0.95)',
        'rgba(180, 30, 60, 1)'
      ]
    });
  }, [mapsReady, layers.solarHeatmap]);

  // ─── Air Quality tiles ──────────────────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    if (aqLayerRef.current) {
      const idx = map.overlayMapTypes.getArray().indexOf(aqLayerRef.current);
      if (idx >= 0) map.overlayMapTypes.removeAt(idx);
      aqLayerRef.current = null;
    }
    if (!layers.airQuality) return;
    const key = window.TINYHUB_CONFIG?.mapsApiKey;
    if (!key) return;
    const aqType = new google.maps.ImageMapType({
      getTileUrl: (coord, z) =>
        `https://airquality.googleapis.com/v1/mapTypes/US_AQI/heatmapTiles/${z}/${coord.x}/${coord.y}?key=${key}`,
      tileSize: new google.maps.Size(256, 256),
      opacity: 0.55, name: 'AirQuality'
    });
    map.overlayMapTypes.push(aqType);
    aqLayerRef.current = aqType;
  }, [mapsReady, layers.airQuality]);

  // ─── 3D toggle ──────────────────────────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    if (layers.tiles3d) {
      map.setMapTypeId('satellite');
      map.setTilt(45);
    } else {
      map.setMapTypeId('roadmap');
      map.setTilt(0);
    }
  }, [mapsReady, layers.tiles3d]);

  // ─── Customer markers + footprints ──────────────────────────
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;

    Object.keys(CUSTOMER_CATEGORIES).forEach(category => {
      const enabled = custEnabled[category];

      // Lazy fetch
      if (enabled && !custData[category] && !custLoading[category] && !custErrors[category]) {
        setCustLoading(s => ({ ...s, [category]: true }));
        const cat = CUSTOMER_CATEGORIES[category];

        (async () => {
          try {
            const places = await fetchPlaces(cat.searchQuery, cat.pageSize || 10);
            const buildings = await batchFetch(places, p =>
              fetchBuildingInsights(p.lat, p.lng).catch(() => null), 6);
            const enriched = places.map((p, i) => ({ ...p, building: buildings[i] }));
            setCustData(s => ({ ...s, [category]: enriched }));
            setCustLoading(s => ({ ...s, [category]: false }));
          } catch (err) {
            console.error('Customer fetch failed:', category, err);
            setCustErrors(s => ({ ...s, [category]: err.message }));
            setCustLoading(s => ({ ...s, [category]: false }));
          }
        })();
      }

      (customerMarkersRef.current[category] || []).forEach(m => m.setMap(null));
      (customerPolygonsRef.current[category] || []).forEach(p => p.setMap(null));
      customerMarkersRef.current[category] = [];
      customerPolygonsRef.current[category] = [];

      if (!enabled) return;
      const items = custData[category];
      if (!items || items.length === 0) return;
      const cat = CUSTOMER_CATEGORIES[category];

      // Footprints first (under markers)
      items.forEach(item => {
        if (!item.building) return;
        const segments = item.building.roofSegments;
        const bbox = item.building.boundingBox;

        const handleClick = () => {
          setActiveDistrict(null);
          setActiveCustomer({ ...item, category });
          map.panTo({ lat: item.lat, lng: item.lng });
          if (map.getZoom() < 16) map.setZoom(17);
        };
        const handleMouseOver = (e) => {
          const dom = e?.domEvent;
          if (!dom) return;
          setHover({ ...item, category, x: dom.clientX, y: dom.clientY });
        };
        const handleMouseOut = () => setHover(null);

        if (segments && segments.length > 0) {
          segments.forEach(seg => {
            if (!seg.boundingBox?.sw || !seg.boundingBox?.ne) return;
            const rect = new google.maps.Rectangle({
              bounds: {
                south: seg.boundingBox.sw.latitude,
                west: seg.boundingBox.sw.longitude,
                north: seg.boundingBox.ne.latitude,
                east: seg.boundingBox.ne.longitude
              },
              fillColor: '#ffcc00',
              fillOpacity: 0.4,
              strokeColor: '#ff9500',
              strokeOpacity: 0.95,
              strokeWeight: 1.5,
              map, clickable: true, zIndex: 200
            });
            rect.addListener('click', handleClick);
            rect.addListener('mouseover', handleMouseOver);
            rect.addListener('mouseout', handleMouseOut);
            customerPolygonsRef.current[category].push(rect);
          });
        } else if (bbox?.sw && bbox?.ne) {
          const rect = new google.maps.Rectangle({
            bounds: {
              south: bbox.sw.latitude, west: bbox.sw.longitude,
              north: bbox.ne.latitude, east: bbox.ne.longitude
            },
            fillColor: '#ffcc00',
            fillOpacity: 0.35,
            strokeColor: '#ff9500',
            strokeOpacity: 0.9,
            strokeWeight: 2,
            map, clickable: true, zIndex: 200
          });
          rect.addListener('click', handleClick);
          rect.addListener('mouseover', handleMouseOver);
          rect.addListener('mouseout', handleMouseOut);
          customerPolygonsRef.current[category].push(rect);
        }
      });

      // Markers on top
      items.forEach(item => {
        const marker = new google.maps.Marker({
          position: { lat: item.lat, lng: item.lng },
          map,
          icon: {
            url: makeCustomerMarker(28, cat.color, cat.darkColor, cat.letter),
            scaledSize: new google.maps.Size(28, 28),
            anchor: new google.maps.Point(14, 14)
          },
          title: item.name,
          zIndex: 1000
        });
        marker.addListener('click', () => {
          setActiveDistrict(null);
          setActiveCustomer({ ...item, category });
          map.panTo({ lat: item.lat, lng: item.lng });
          if (map.getZoom() < 16) map.setZoom(17);
        });
        marker.addListener('mouseover', (e) => {
          const dom = e?.domEvent;
          if (!dom) return;
          setHover({ ...item, category, x: dom.clientX, y: dom.clientY });
        });
        marker.addListener('mouseout', () => setHover(null));
        customerMarkersRef.current[category].push(marker);
      });
    });
  }, [mapsReady, custEnabled, custData]);

  const setCustomerLayer = (category, val) => {
    setCustEnabled(s => ({ ...s, [category]: val }));
    if (!val && activeCustomer?.category === category) setActiveCustomer(null);
  };

  const custCounts = Object.fromEntries(
    Object.keys(CUSTOMER_CATEGORIES).map(k => [k, custData[k]?.length])
  );

  const totalDailyDemand = Object.entries(CUSTOMER_CATEGORIES).reduce((acc, [k, c]) =>
    acc + (custEnabled[k] ? (custData[k]?.length || 0) * c.estKwhPerDay : 0), 0);

  const totalAnnualSolar = Object.entries(CUSTOMER_CATEGORIES).reduce((acc, [k]) => {
    if (!custEnabled[k]) return acc;
    const items = custData[k] || [];
    return acc + items.reduce((s, it) => s + (it.building?.maxKwh || 0), 0);
  }, 0);

  const anyCustomer = Object.values(custEnabled).some(v => v);

  return (
    <>
      <div className="atmos" aria-hidden="true">
        <div className="atmos__stars" />
        <div className="atmos__horizon" />
        <div className="atmos__grid" />
      </div>
      <NavBar />
      <div className="map-shell">
        <div className="map-stage">
          <div ref={mapDivRef} id="map-canvas" />

          <div className="map-loading">
            <div className="map-loading__title">Initializing Map</div>
            <div className="map-loading__bar" />
            <div className="map-loading__sub">Maps Platform · McHenry County</div>
          </div>

          <LayerDrawer
            layers={layers}
            onToggle={setLayer}
            zoom={zoom}
            custEnabled={custEnabled}
            onCustToggle={setCustomerLayer}
            custCounts={custCounts}
            custLoading={custLoading}
            custErrors={custErrors}
          />

          <div className="map-controls">
            <PilotControl
              pilot={pilot}
              busy={pilotBusy}
              error={pilotError}
              onStart={startPilot}
              onStop={stopPilot}
            />
            <div className="zoom-hud">
              ZOOM <span className="cyan">{zoom}</span> · {layers.tiles3d ? '3D' : '2D'}
            </div>
          </div>

          <DistrictInfoPanel
            district={activeDistrict}
            snap={snap}
            onClose={() => setActiveDistrict(null)}
          />

          <CustomerInfoPanel
            customer={activeCustomer}
            onClose={() => setActiveCustomer(null)}
          />

          <HoverTooltip hover={hover} />
        </div>

        <aside className="map-rail">
          <div className="map-rail__section">
            <div className="eyebrow">// LIVE STATE</div>
            <h2>McHenry County</h2>
            <div className="live-stat">
              <div className="live-stat__num">{fmt.num(snap.matched)}</div>
              <div className="live-stat__lbl">matched · current batch</div>
            </div>
            <div className="live-stat">
              <div className="live-stat__num" style={{ color: 'var(--cyan)' }}>
                {fmt.fixed(snap.mwhDay, 1)} <span style={{ fontSize: '0.7rem', color: 'var(--ink-dim)' }}>MWh</span>
              </div>
              <div className="live-stat__lbl">today · network</div>
            </div>
            <div className="live-stat">
              <div className="live-stat__num" style={{ color: 'var(--green-live)' }}>
                {fmt.money(snap.savedDay)}
              </div>
              <div className="live-stat__lbl">saved vs ComEd</div>
            </div>
            <div style={{ marginTop: '0.6rem' }}>
              {pilot.running
                ? <span className="pill pill--live">PILOT · LIVE</span>
                : <span className="pill" style={{ borderColor: 'var(--hair-cyan-2)', color: 'var(--ink-dim)' }}>
                    PILOT · STANDBY
                  </span>
              }
            </div>
          </div>

          {anyCustomer && (
            <div className="map-rail__section">
              <div className="eyebrow">// PROSPECTS · LOADED</div>
              {Object.entries(CUSTOMER_CATEGORIES).map(([key, cat]) => {
                if (!custEnabled[key]) return null;
                const list = custData[key] || [];
                return (
                  <div key={key} className="prospect-row">
                    <span className="prospect-row__chip" style={{ background: cat.color }}>{cat.letter}</span>
                    <span className="prospect-row__name">{cat.label}</span>
                    <span className="prospect-row__count">
                      {custLoading[key] ? '…' : list.length}
                    </span>
                  </div>
                );
              })}
              <div className="prospect-total">
                <div className="prospect-total__row">
                  <span>Est. demand · daily</span>
                  <span className="cyan">{fmt.kwh(totalDailyDemand)}</span>
                </div>
                <div className="prospect-total__row">
                  <span>Solar potential · annual</span>
                  <span className="sun">{fmt.kwh(totalAnnualSolar)}</span>
                </div>
              </div>
            </div>
          )}

          <div className="map-rail__section">
            <div className="eyebrow">// 12 DISTRICTS · NETWORK</div>
            <div className="district-list">
              {(snap.districts || []).map(d => (
                <div
                  key={d.id}
                  className={`district-chip ${activeDistrict?.id === d.id ? 'is-active' : ''}`}
                  onClick={() => {
                    setActiveCustomer(null);
                    setActiveDistrict(d);
                    mapRef.current?.panTo({ lat: d.lat, lng: d.lng });
                    if (mapRef.current?.getZoom() < 13) mapRef.current.setZoom(13);
                  }}
                >
                  <span className="district-chip__id">{d.id}</span>
                  <span className="district-chip__name">{d.name}</span>
                  <span className="district-chip__stat">{fmt.num(d.houses)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="map-rail__section">
            <div className="eyebrow">// SOLVER</div>
            <div className="kv">
              <span className="kv__k">CONVERGENCE</span>
              <span className="kv__v cyan">{fmt.fixed(snap.convergence, 3)}</span>
            </div>
            <div className="kv">
              <span className="kv__k">FEASIBILITY</span>
              <span className="kv__v">{fmt.fixed(snap.feasibility, 3)}</span>
            </div>
            <div className="kv">
              <span className="kv__k">SETTLED · TOTAL</span>
              <span className="kv__v">{fmt.num(snap.settled)}</span>
            </div>
            <div className="kv">
              <span className="kv__k">SURGE × </span>
              <span className="kv__v">{fmt.fixed(snap.surge, 2)}</span>
            </div>
          </div>
        </aside>
      </div>

      <TweaksPanel title="Demo Controls">
        <TweakSection title="Refresh">
          <TweakSlider
            label="Tick rate"
            value={tweaks.tickRateMs}
            min={250} max={3000} step={250}
            fmt={v => v + 'ms'}
            onChange={v => setTweak('tickRateMs', v)}
          />
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('app')).render(<App />);
