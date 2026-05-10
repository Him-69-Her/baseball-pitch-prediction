/* =============================================================
   TINY-HUB · LIVE MAP
   Light cartography + Google Maps Platform integration.

   Layers:
   ✓ Maps JS API · light cartography style
   ✓ District markers (12 McHenry County communities)
   ✓ Trade-flow polylines (between all 12 districts)
   ✓ Solar API · per-district on click
   ✓ Solar potential heatmap (county-wide scatter, not stacked at districts)
   ✓ Open-Meteo weather (cloud cover & DNI)
   ✓ Air Quality API tile overlay
   ✓ Photorealistic 3D Tiles (auto at zoom ≥ 16)
   ✓ Distance corridors
   ✓ Potential customers · Places API (Walmart, Jewel-Osco, Amazon, schools)
   ============================================================= */

const { useState, useEffect, useRef, useMemo } = React;
const { TweaksPanel, TweakSection, TweakSlider, TweakToggle, useTweaks } = window.Tweaks;

// ─── Display helpers ──────────────────────────────────────────
const dash = '—';
const fmt = {
  num: (v, d = 0) => v == null ? dash : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }),
  fixed: (v, d = 2) => v == null ? dash : Number(v).toFixed(d),
  money: v => v == null ? dash : '$' + Number(v).toLocaleString(),
  kwh: v => v == null ? dash : Number(v).toLocaleString() + ' kWh'
};

// ─── McHenry County rough bounds for sample / scatter points ──
const COUNTY = {
  center: { lat: 42.30, lng: -88.40 },
  // approx bounding box for county
  north: 42.50, south: 42.10, east: -88.10, west: -88.65
};

// ─── Customer categories (potential prospects) ────────────────
const CUSTOMER_CATEGORIES = {
  walmart: {
    label: 'Walmart',
    color: '#0071ce',
    darkColor: '#003478',
    letter: 'W',
    estKwhPerDay: 28000,
    type: 'big-box retail',
    searchQuery: 'Walmart in McHenry County, Illinois'
  },
  jewel: {
    label: 'Jewel-Osco',
    color: '#d6001c',
    darkColor: '#7a0011',
    letter: 'J',
    estKwhPerDay: 4500,
    type: 'grocery / supermarket',
    searchQuery: 'Jewel-Osco in McHenry County, Illinois'
  },
  amazon: {
    label: 'Amazon',
    color: '#ff9900',
    darkColor: '#b86b00',
    letter: 'A',
    estKwhPerDay: 95000,
    type: 'logistics / fulfillment',
    searchQuery: 'Amazon warehouse in McHenry County, Illinois'
  },
  schools: {
    label: 'Schools',
    color: '#2e7d32',
    darkColor: '#1b5e20',
    letter: 'S',
    estKwhPerDay: 3500,
    type: 'K-12 / public',
    searchQuery: 'school in McHenry County, Illinois',
    pageSize: 20
  }
};

// ─── Wait for Maps SDK ────────────────────────────────────────
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
// Cream background, soft grays, subtle blue water — high contrast
// with the dark page chrome surrounding it.
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

// ─── Marker icon factories ────────────────────────────────────
// District marker — solid filled circle with dark outline, visible on light bg
function makeDistrictMarker(size = 32, color = '#ff9500', outline = '#7a3f00') {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 3}" fill="${color}" stroke="${outline}" stroke-width="2.5"/>
      <circle cx="${size/2}" cy="${size/2}" r="${size/5}" fill="#fff" opacity="0.9"/>
    </svg>`;
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
}

// Customer marker — colored circle with letter
function makeCustomerMarker(size = 26, color = '#0071ce', outline = '#003478', letter = 'W') {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${size/2}" cy="${size/2}" r="${size/2 - 2}" fill="${color}" stroke="${outline}" stroke-width="2"/>
      <text x="${size/2}" y="${size/2 + 4}"
            font-family="Inter, system-ui, Arial Black, sans-serif"
            font-size="${size * 0.42}"
            font-weight="900"
            fill="#fff"
            text-anchor="middle">${letter}</text>
    </svg>`;
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
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

function CustomerSubRow({ category, on, onToggle, count, loading }) {
  const cat = CUSTOMER_CATEGORIES[category];
  return (
    <div className={`cust-sub ${on ? 'is-on' : ''}`} onClick={() => onToggle(!on)}>
      <div className="cust-sub__chip" style={{ background: cat.color, borderColor: cat.darkColor }}>
        {cat.letter}
      </div>
      <div className="cust-sub__name">{cat.label}</div>
      <div className="cust-sub__count">
        {loading ? '…' : count != null ? count : ''}
      </div>
      <div className="layer-toggle" />
    </div>
  );
}

function LayerDrawer({ layers, onToggle, zoom, custEnabled, onCustToggle, custCounts, custLoading }) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`layer-drawer ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="layer-drawer__head" onClick={() => setCollapsed(c => !c)}>
        <div className="layer-drawer__title">Map Layers</div>
        <div className="layer-drawer__caret">▾</div>
      </div>
      <div className="layer-drawer__body">
        <LayerRow name="Trade flows" sub="P2P routes · animated"
          on={layers.flows} onToggle={v => onToggle('flows', v)} />
        <LayerRow name="Solar potential" sub="Google Solar API · heatmap"
          on={layers.solar} onToggle={v => onToggle('solar', v)} />
        <LayerRow name="Air Quality" sub="Google AQ tiles"
          on={layers.airQuality} onToggle={v => onToggle('airQuality', v)} />
        <LayerRow name="Photorealistic 3D"
          sub={zoom < 16 ? `Zoom ≥ 16 to enable (now ${zoom})` : 'Map Tiles API'}
          on={layers.tiles3d} onToggle={v => onToggle('tiles3d', v)}
          disabled={zoom < 16} />
        <LayerRow name="Distance corridors" sub="Geometric · between districts"
          on={layers.corridors} onToggle={v => onToggle('corridors', v)} />

        {/* Customer category sub-section */}
        <div className="layer-drawer__section">
          <div className="layer-drawer__section-head">Potential customers</div>
          {Object.keys(CUSTOMER_CATEGORIES).map(key => (
            <CustomerSubRow
              key={key}
              category={key}
              on={custEnabled[key]}
              onToggle={v => onCustToggle(key, v)}
              count={custCounts[key]}
              loading={custLoading[key]}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Info panels ──────────────────────────────────────────────
function DistrictInfoPanel({ district, snap, solar, solarLoading, solarError, weather, onClose }) {
  if (!district) return null;
  const districtSnap = (snap.districts || []).find(d => d.id === district.id);
  return (
    <div className="info-panel info-panel--district is-open">
      <div className="info-panel__head">
        <div>
          <div className="info-panel__id">
            {district.id} · {weather?.cloudCover != null ? `${Math.round(weather.cloudCover)}% cloud` : 'weather pending'}
          </div>
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

        <div className="info-panel__solar">
          <h4>☀ Solar Potential · Google Solar API</h4>
          {solarLoading && <div className="solar-loading">Querying solar dataset…</div>}
          {solarError && <div className="solar-error">{solarError}</div>}
          {!solarLoading && !solarError && solar && (
            <>
              <div className="solar-row"><span className="solar-row__k">Annual kWh potential</span><span className="solar-row__v">{fmt.kwh(solar.maxKwh)}</span></div>
              <div className="solar-row"><span className="solar-row__k">Max panel count</span><span className="solar-row__v">{fmt.num(solar.maxPanels)}</span></div>
              <div className="solar-row"><span className="solar-row__k">Sunshine hrs / yr</span><span className="solar-row__v">{fmt.num(solar.sunshineHours)}</span></div>
              <div className="solar-row"><span className="solar-row__k">Roof area</span><span className="solar-row__v">{fmt.num(solar.roofAreaM2)} m²</span></div>
              <div className="solar-row"><span className="solar-row__k">Carbon offset</span><span className="solar-row__v">{fmt.num(solar.carbonOffsetKg)} kg CO₂/MWh</span></div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CustomerInfoPanel({ customer, onClose }) {
  if (!customer) return null;
  const cat = CUSTOMER_CATEGORIES[customer.category];
  return (
    <div className="info-panel info-panel--customer is-open">
      <div className="info-panel__head">
        <div>
          <div className="info-panel__id">
            <span className="cust-badge" style={{ background: cat.color }}>{cat.letter}</span>
            {' '}{cat.label.toUpperCase()} · POTENTIAL CUSTOMER
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
          <div className="info-metric">
            <div className="info-metric__lbl">Peak shaving · monthly</div>
            <div className="info-metric__val good">~{Math.round(cat.estKwhPerDay * 30 * 0.18 / 1000)} MWh</div>
          </div>
          <div className="info-metric">
            <div className="info-metric__lbl">Onboarding</div>
            <div className="info-metric__val" style={{ fontSize: '0.78rem' }}>QUEUED</div>
          </div>
        </div>
        <button className="cust-cta">▸ ADD TO ONBOARDING QUEUE</button>
        <div className="cust-disclaimer">
          Estimates based on category benchmarks. Real demand requires meter data.
        </div>
      </div>
    </div>
  );
}

// ─── External API helpers ─────────────────────────────────────
async function fetchSolar(lat, lng) {
  const key = window.TINYHUB_CONFIG?.mapsApiKey;
  if (!key) throw new Error('Missing API key');
  const url = `https://solar.googleapis.com/v1/buildingInsights:findClosest`
    + `?location.latitude=${lat}&location.longitude=${lng}&requiredQuality=HIGH&key=${key}`;
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(r.status === 404 ? 'No detailed solar data for this point yet' : `Solar API: ${r.status}`);
  }
  const data = await r.json();
  const sp = data?.solarPotential;
  if (!sp) throw new Error('No solar potential data');
  const configs = sp.solarPanelConfigs || [];
  const best = configs[configs.length - 1];
  return {
    maxKwh: Math.round(best?.yearlyEnergyDcKwh || sp.maxArrayPanelsCount * 400),
    maxPanels: sp.maxArrayPanelsCount,
    sunshineHours: Math.round(sp.maxSunshineHoursPerYear || 0),
    roofAreaM2: Math.round(sp.wholeRoofStats?.areaMeters2 || 0),
    carbonOffsetKg: Math.round(sp.carbonOffsetFactorKgPerMwh || 0)
  };
}

async function fetchWeather(lat, lng) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}`
    + `&current=cloud_cover,direct_normal_irradiance,temperature_2m&forecast_days=1`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo: ${r.status}`);
  const j = await r.json();
  return {
    cloudCover: j.current?.cloud_cover,
    dni: j.current?.direct_normal_irradiance,
    tempC: j.current?.temperature_2m
  };
}

// Places API (New) · Text Search
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
        circle: {
          center: COUNTY.center,
          radius: 30000  // 30km — county is ~50km wide
        }
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

// ─── Main App ─────────────────────────────────────────────────
function App() {
  const mapsReady = useMapsReady();
  const mapDivRef = useRef(null);
  const mapRef = useRef(null);
  const districtMarkersRef = useRef([]);
  const customerMarkersRef = useRef({}); // keyed by category
  const flowsRef = useRef([]);
  const corridorsRef = useRef([]);
  const aqLayerRef = useRef(null);
  const solarHeatmapRef = useRef(null);

  const [snap, setSnap] = useState(() => window.TinyHubSim.snapshot());
  const [activeDistrict, setActiveDistrict] = useState(null);
  const [activeCustomer, setActiveCustomer] = useState(null);
  const [solar, setSolar] = useState(null);
  const [solarLoading, setSolarLoading] = useState(false);
  const [solarError, setSolarError] = useState(null);
  const [weather, setWeather] = useState(null);
  const [zoom, setZoom] = useState(11);
  const [layers, setLayers] = useState({
    flows: true, solar: false, airQuality: false, tiles3d: false, corridors: false
  });

  const [custEnabled, setCustEnabled] = useState({
    walmart: false, jewel: false, amazon: false, schools: false
  });
  const [custData, setCustData] = useState({}); // {walmart: [{id,name,...}], ...}
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

  // District markers · always on top
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    districtMarkersRef.current.forEach(m => m.setMap(null));
    districtMarkersRef.current = [];

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
        zIndex: 1000
      });
      marker.addListener('click', () => {
        setActiveCustomer(null);
        setActiveDistrict(d);
        setSolar(null); setSolarError(null); setSolarLoading(true);
        fetchSolar(d.lat, d.lng)
          .then(s => { setSolar(s); setSolarLoading(false); })
          .catch(err => { setSolarError(err.message); setSolarLoading(false); });
        setWeather(null);
        fetchWeather(d.lat, d.lng).then(setWeather).catch(() => {});
        map.panTo({ lat: d.lat, lng: d.lng });
        if (map.getZoom() < 13) map.setZoom(13);
      });
      districtMarkersRef.current.push(marker);
    });
  }, [mapsReady, snap.districts]);

  // Trade flows · between ALL 12 districts (closest 2 to each)
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

  // Distance corridors · ALL pairs
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

  // Solar heatmap · scatter ACROSS county, not stacked at districts
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    if (solarHeatmapRef.current) {
      solarHeatmapRef.current.setMap(null);
      solarHeatmapRef.current = null;
    }
    if (!layers.solar) return;
    if (!google.maps.visualization) return;

    // Generate a deterministic-ish scatter across the county bounds
    const points = [];
    const rng = (seed) => {
      let s = seed;
      return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    };
    const r = rng(42);
    const pointCount = 800;
    for (let i = 0; i < pointCount; i++) {
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
  }, [mapsReady, layers.solar]);

  // Air Quality tiles
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

  // 3D toggle
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

  // Customer markers · fetch on first toggle, cache, render based on `custEnabled`
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;

    Object.keys(CUSTOMER_CATEGORIES).forEach(category => {
      const enabled = custEnabled[category];

      // Lazy fetch · only if enabled and not yet fetched
      if (enabled && !custData[category] && !custLoading[category] && !custErrors[category]) {
        setCustLoading(s => ({ ...s, [category]: true }));
        const cat = CUSTOMER_CATEGORIES[category];
        fetchPlaces(cat.searchQuery, cat.pageSize || 10)
          .then(places => {
            setCustData(s => ({ ...s, [category]: places }));
            setCustLoading(s => ({ ...s, [category]: false }));
          })
          .catch(err => {
            console.error('Places fetch failed:', category, err);
            setCustErrors(s => ({ ...s, [category]: err.message }));
            setCustLoading(s => ({ ...s, [category]: false }));
          });
      }

      // Clear existing markers for this category
      const existing = customerMarkersRef.current[category] || [];
      existing.forEach(m => m.setMap(null));
      customerMarkersRef.current[category] = [];

      if (!enabled) return;
      const places = custData[category];
      if (!places || places.length === 0) return;

      const cat = CUSTOMER_CATEGORIES[category];
      const newMarkers = places.map(place => {
        const marker = new google.maps.Marker({
          position: { lat: place.lat, lng: place.lng },
          map: mapRef.current,
          icon: {
            url: makeCustomerMarker(26, cat.color, cat.darkColor, cat.letter),
            scaledSize: new google.maps.Size(26, 26),
            anchor: new google.maps.Point(13, 13)
          },
          title: place.name,
          zIndex: 500
        });
        marker.addListener('click', () => {
          setActiveDistrict(null);
          setActiveCustomer({ ...place, category });
          mapRef.current.panTo({ lat: place.lat, lng: place.lng });
        });
        return marker;
      });
      customerMarkersRef.current[category] = newMarkers;
    });
  }, [mapsReady, custEnabled, custData]);

  const setCustomerLayer = (category, val) => {
    setCustEnabled(s => ({ ...s, [category]: val }));
  };

  const custCounts = Object.fromEntries(
    Object.keys(CUSTOMER_CATEGORIES).map(k => [k, custData[k]?.length])
  );

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
          />

          <div className="zoom-hud">
            ZOOM <span className="cyan">{zoom}</span> · {layers.tiles3d ? '3D' : '2D'}
          </div>

          <DistrictInfoPanel
            district={activeDistrict}
            snap={snap}
            solar={solar}
            solarLoading={solarLoading}
            solarError={solarError}
            weather={weather}
            onClose={() => setActiveDistrict(null)}
          />
          <CustomerInfoPanel
            customer={activeCustomer}
            onClose={() => setActiveCustomer(null)}
          />
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
              <div className="live-stat__lbl">today · 12 districts</div>
            </div>
            <div className="live-stat">
              <div className="live-stat__num" style={{ color: 'var(--green-live)' }}>
                {fmt.money(snap.savedDay)}
              </div>
              <div className="live-stat__lbl">saved vs ComEd</div>
            </div>
            <div style={{ marginTop: '0.6rem' }}>
              <span className="pill" style={{ borderColor: 'var(--hair-cyan-2)', color: 'var(--ink-dim)' }}>
                DATA FEED · PENDING
              </span>
            </div>
          </div>

          <div className="map-rail__section">
            <div className="eyebrow">// DISTRICTS · ALL 12</div>
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
                    setSolar(null); setSolarError(null); setSolarLoading(true);
                    fetchSolar(d.lat, d.lng)
                      .then(s => { setSolar(s); setSolarLoading(false); })
                      .catch(err => { setSolarError(err.message); setSolarLoading(false); });
                    setWeather(null);
                    fetchWeather(d.lat, d.lng).then(setWeather).catch(() => {});
                  }}
                >
                  <span className="district-chip__id">{d.id}</span>
                  <span className="district-chip__name">{d.name}</span>
                  <span className="district-chip__stat">{fmt.num(d.houses)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Customer prospects summary */}
          {Object.values(custEnabled).some(v => v) && (
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
                Est. combined demand:&nbsp;
                <span className="cyan">
                  {fmt.kwh(
                    Object.entries(CUSTOMER_CATEGORIES).reduce((acc, [k, c]) =>
                      acc + (custEnabled[k] ? (custData[k]?.length || 0) * c.estKwhPerDay : 0), 0)
                  )}/day
                </span>
              </div>
            </div>
          )}

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
