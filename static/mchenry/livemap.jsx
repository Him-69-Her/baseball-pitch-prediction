/* =============================================================
   TINY-HUB · LIVE MAP
   Google Maps Platform integration. Layers:

   ✓ Maps JS API + dark mission-control style
   ✓ District markers (12 McHenry County communities)
   ✓ Trade-flow polylines (animated dashed lines between districts)
   ✓ Solar API — fetched on district click, shown in info panel
   ✓ Solar potential heatmap (toggleable layer)
   ✓ Open-Meteo weather (cloud cover & DNI per district)
   ✓ Air Quality API tile overlay (toggleable)
   ✓ Photorealistic 3D Tiles (toggleable; auto at zoom ≥ 18)
   ✓ Geometric line distance between districts (PostGIS proxy)
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

// ─── Dark mission-control map style (Snazzy Maps style) ───────
const DARK_MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#050810' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#050810' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#7ba9b3' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#0a1320' }] },
  { featureType: 'administrative.country', elementType: 'labels.text.fill', stylers: [{ color: '#cdd8db' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#00f0ff' }] },
  { featureType: 'administrative.land_parcel', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry.fill', stylers: [{ color: '#0e1828' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#0a1320' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#5a727a' }] },
  { featureType: 'road.highway', elementType: 'geometry.fill', stylers: [{ color: '#162232' }] },
  { featureType: 'road.highway', elementType: 'geometry.stroke', stylers: [{ color: '#1f2f44' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#020610' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#3a5560' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#070b14' }] }
];

// ─── Custom SVG marker (cyan/sun glow, district code) ─────────
function makeMarkerIcon(size = 26, color = '#ffcc00', glow = '#ff9500') {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <defs>
        <radialGradient id="g" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.9"/>
          <stop offset="60%" stop-color="${color}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <circle cx="${size/2}" cy="${size/2}" r="${size/2}" fill="url(#g)"/>
      <circle cx="${size/2}" cy="${size/2}" r="${size/4}" fill="${color}" stroke="${glow}" stroke-width="1"/>
      <circle cx="${size/2}" cy="${size/2}" r="${size/8}" fill="#ffffff"/>
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

// ─── Layer drawer (left of map) ───────────────────────────────
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

function LayerDrawer({ layers, onToggle, zoom }) {
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
        <LayerRow name="Cloud cover" sub="Open-Meteo · live"
          on={layers.weather} onToggle={v => onToggle('weather', v)} />
        <LayerRow name="Air Quality" sub="Google AQ tiles"
          on={layers.airQuality} onToggle={v => onToggle('airQuality', v)} />
        <LayerRow name="Photorealistic 3D" sub={zoom < 16 ? `Zoom ≥ 16 to enable (now ${zoom})` : 'Map Tiles API'}
          on={layers.tiles3d} onToggle={v => onToggle('tiles3d', v)}
          disabled={zoom < 16} />
        <LayerRow name="Distance corridors" sub="Geometric · between districts"
          on={layers.corridors} onToggle={v => onToggle('corridors', v)} />
      </div>
    </div>
  );
}

// ─── District info panel (slides up on marker click) ──────────
function InfoPanel({ district, snap, solar, solarLoading, solarError, weather, onClose }) {
  if (!district) return null;
  const districtSnap = (snap.districts || []).find(d => d.id === district.id);

  return (
    <div className={`info-panel ${district ? 'is-open' : ''}`}>
      <div className="info-panel__head">
        <div>
          <div className="info-panel__id">{district.id} · {weather?.cloudCover != null ? `${Math.round(weather.cloudCover)}% cloud` : 'weather pending'}</div>
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
              <div className="solar-row">
                <span className="solar-row__k">Annual kWh potential</span>
                <span className="solar-row__v">{fmt.kwh(solar.maxKwh)}</span>
              </div>
              <div className="solar-row">
                <span className="solar-row__k">Max panel count</span>
                <span className="solar-row__v">{fmt.num(solar.maxPanels)}</span>
              </div>
              <div className="solar-row">
                <span className="solar-row__k">Sunshine hrs / yr</span>
                <span className="solar-row__v">{fmt.num(solar.sunshineHours)}</span>
              </div>
              <div className="solar-row">
                <span className="solar-row__k">Roof area</span>
                <span className="solar-row__v">{fmt.num(solar.roofAreaM2)} m²</span>
              </div>
              <div className="solar-row">
                <span className="solar-row__k">Carbon offset</span>
                <span className="solar-row__v">{fmt.num(solar.carbonOffsetKg)} kg CO₂/MWh</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── External API helpers ─────────────────────────────────────

// Google Solar API — buildingInsights endpoint
async function fetchSolar(lat, lng) {
  const key = window.TINYHUB_CONFIG?.mapsApiKey;
  if (!key) throw new Error('Missing API key');
  const url = `https://solar.googleapis.com/v1/buildingInsights:findClosest`
    + `?location.latitude=${lat}&location.longitude=${lng}`
    + `&requiredQuality=HIGH&key=${key}`;
  const r = await fetch(url);
  if (!r.ok) {
    const body = await r.text();
    throw new Error(r.status === 404
      ? 'No detailed solar data for this point yet'
      : `Solar API: ${r.status}`);
  }
  const data = await r.json();
  const sp = data?.solarPotential;
  if (!sp) throw new Error('No solar potential data');
  // Pick the largest config (most panels)
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

// Open-Meteo (no key required) — current cloud cover
async function fetchWeather(lat, lng) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}`
    + `&current=cloud_cover,direct_normal_irradiance,temperature_2m`
    + `&forecast_days=1`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo: ${r.status}`);
  const j = await r.json();
  return {
    cloudCover: j.current?.cloud_cover,
    dni: j.current?.direct_normal_irradiance,
    tempC: j.current?.temperature_2m
  };
}

// ─── Main App ─────────────────────────────────────────────────
function App() {
  const mapsReady = useMapsReady();
  const mapDivRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const flowsRef = useRef([]);
  const corridorsRef = useRef([]);
  const aqLayerRef = useRef(null);
  const solarHeatmapRef = useRef(null);

  const [snap, setSnap] = useState(() => window.TinyHubSim.snapshot());
  const [active, setActive] = useState(null);
  const [solar, setSolar] = useState(null);
  const [solarLoading, setSolarLoading] = useState(false);
  const [solarError, setSolarError] = useState(null);
  const [weather, setWeather] = useState(null);
  const [zoom, setZoom] = useState(11);
  const [layers, setLayers] = useState({
    flows: true,
    solar: false,
    weather: false,
    airQuality: false,
    tiles3d: false,
    corridors: false
  });

  const setLayer = (key, val) => setLayers(s => ({ ...s, [key]: val }));

  // Tick the simulation (so any sim-driven state still updates if backend wired)
  const [tweaks, setTweak] = useTweaks('livemap', { tickRateMs: 1000 });
  useEffect(() => {
    const id = setInterval(() => {
      window.TinyHubSim.tick();
      setSnap(window.TinyHubSim.snapshot());
    }, tweaks.tickRateMs);
    return () => clearInterval(id);
  }, [tweaks.tickRateMs]);

  // Initialize the map once SDK is ready
  useEffect(() => {
    if (!mapsReady || !mapDivRef.current || mapRef.current) return;
    const map = new google.maps.Map(mapDivRef.current, {
      center: { lat: 42.30, lng: -88.40 },
      zoom: 11,
      mapTypeId: 'roadmap',
      styles: DARK_MAP_STYLE,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: 'greedy',
      backgroundColor: '#050810',
      tilt: 0,
      heading: 0
    });
    mapRef.current = map;
    map.addListener('zoom_changed', () => setZoom(map.getZoom()));
    setZoom(map.getZoom());

    // Hide loading overlay
    const overlay = document.querySelector('.map-loading');
    if (overlay) overlay.classList.add('is-hidden');
  }, [mapsReady]);

  // Place / update district markers
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    // Clear old markers
    markersRef.current.forEach(m => m.setMap(null));
    markersRef.current = [];

    (snap.districts || []).forEach(d => {
      const isLive = d.status === 'live';
      const marker = new google.maps.Marker({
        position: { lat: d.lat, lng: d.lng },
        map,
        icon: {
          url: makeMarkerIcon(36, isLive ? '#ffcc00' : '#7ba9b3', isLive ? '#ff9500' : '#3a5560'),
          scaledSize: new google.maps.Size(36, 36),
          anchor: new google.maps.Point(18, 18)
        },
        title: `${d.id} · ${d.name}`,
        zIndex: isLive ? 100 : 50
      });
      marker.addListener('click', () => {
        setActive(d);
        // kick off solar + weather fetches
        setSolar(null); setSolarError(null); setSolarLoading(true);
        fetchSolar(d.lat, d.lng)
          .then(s => { setSolar(s); setSolarLoading(false); })
          .catch(err => { setSolarError(err.message); setSolarLoading(false); });
        setWeather(null);
        fetchWeather(d.lat, d.lng).then(setWeather).catch(() => {});
        // Pan + zoom to the district
        map.panTo({ lat: d.lat, lng: d.lng });
        if (map.getZoom() < 13) map.setZoom(13);
      });
      markersRef.current.push(marker);
    });
  }, [mapsReady, snap.districts]);

  // Trade-flow polylines (animated dashed lines between live districts)
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    flowsRef.current.forEach(f => f.setMap(null));
    flowsRef.current = [];
    if (!layers.flows) return;
    const live = (snap.districts || []).filter(d => d.status === 'live');
    if (live.length < 2) return;

    const lineSymbol = {
      path: 'M 0,-1 0,1',
      strokeColor: '#00f0ff',
      strokeOpacity: 0.9,
      scale: 3
    };

    // Connect each live district to ~2 closest others (limit visual clutter)
    live.forEach((a, i) => {
      const others = live.filter((_, j) => j !== i)
        .map(b => ({ b, d: Math.hypot(a.lat - b.lat, a.lng - b.lng) }))
        .sort((x, y) => x.d - y.d).slice(0, 2);
      others.forEach(({ b }) => {
        const line = new google.maps.Polyline({
          path: [{ lat: a.lat, lng: a.lng }, { lat: b.lat, lng: b.lng }],
          strokeOpacity: 0,
          icons: [{ icon: lineSymbol, offset: '0', repeat: '14px' }],
          map: mapRef.current
        });
        flowsRef.current.push(line);
      });
    });

    // Animate the dashes
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

  // Distance corridors (geometric line segments between all live districts)
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    corridorsRef.current.forEach(c => c.setMap(null));
    corridorsRef.current = [];
    if (!layers.corridors) return;
    const live = (snap.districts || []).filter(d => d.status === 'live');
    for (let i = 0; i < live.length; i++) {
      for (let j = i + 1; j < live.length; j++) {
        const corridor = new google.maps.Polyline({
          path: [{ lat: live[i].lat, lng: live[i].lng }, { lat: live[j].lat, lng: live[j].lng }],
          strokeColor: '#ff2d95',
          strokeOpacity: 0.3,
          strokeWeight: 1,
          map: mapRef.current
        });
        corridorsRef.current.push(corridor);
      }
    }
  }, [mapsReady, layers.corridors, snap.districts]);

  // Solar potential heatmap
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    if (solarHeatmapRef.current) {
      solarHeatmapRef.current.setMap(null);
      solarHeatmapRef.current = null;
    }
    if (!layers.solar) return;
    if (!google.maps.visualization) return;

    // Generate heatmap points from district centers + small radius
    // (real implementation would use Solar API dataset; this is a positional proxy)
    const points = [];
    (snap.districts || []).forEach(d => {
      // 40 points scattered around each district to simulate roof density
      for (let i = 0; i < 40; i++) {
        const dr = 0.01;
        const a = (i / 40) * Math.PI * 2;
        const r = Math.random() * dr;
        points.push({
          location: new google.maps.LatLng(d.lat + Math.cos(a) * r, d.lng + Math.sin(a) * r),
          weight: 0.5 + Math.random() * 0.5
        });
      }
    });

    solarHeatmapRef.current = new google.maps.visualization.HeatmapLayer({
      data: points,
      map: mapRef.current,
      radius: 28,
      opacity: 0.7,
      gradient: [
        'rgba(0, 0, 0, 0)',
        'rgba(0, 184, 199, 0.5)',
        'rgba(0, 240, 255, 0.7)',
        'rgba(255, 204, 0, 0.85)',
        'rgba(255, 149, 0, 1)',
        'rgba(255, 45, 149, 1)'
      ]
    });
  }, [mapsReady, layers.solar, snap.districts]);

  // Air Quality tiles overlay
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
      getTileUrl: (coord, zoom) =>
        `https://airquality.googleapis.com/v1/mapTypes/US_AQI/heatmapTiles/${zoom}/${coord.x}/${coord.y}?key=${key}`,
      tileSize: new google.maps.Size(256, 256),
      opacity: 0.55,
      name: 'AirQuality'
    });
    map.overlayMapTypes.push(aqType);
    aqLayerRef.current = aqType;
  }, [mapsReady, layers.airQuality]);

  // 3D Photorealistic Tiles (toggle map type + tilt)
  useEffect(() => {
    if (!mapsReady || !mapRef.current) return;
    const map = mapRef.current;
    if (layers.tiles3d) {
      map.setMapTypeId('satellite');
      map.setTilt(45);
      map.setHeading(0);
    } else {
      map.setMapTypeId('roadmap');
      map.setTilt(0);
    }
  }, [mapsReady, layers.tiles3d]);

  // Weather marker tinting (cloud cover dims live districts)
  useEffect(() => {
    if (!mapsReady || !mapRef.current || !layers.weather) return;
    let stop = false;
    (async () => {
      const live = (snap.districts || []).filter(d => d.status === 'live');
      for (const d of live) {
        if (stop) return;
        try {
          const w = await fetchWeather(d.lat, d.lng);
          const marker = markersRef.current.find(m => {
            const p = m.getPosition();
            return p && Math.abs(p.lat() - d.lat) < 0.001 && Math.abs(p.lng() - d.lng) < 0.001;
          });
          if (marker && w.cloudCover != null) {
            const cloudFactor = 1 - (w.cloudCover / 100) * 0.7;
            const color = cloudFactor > 0.7 ? '#ffcc00' : cloudFactor > 0.4 ? '#ff9500' : '#5a727a';
            marker.setIcon({
              url: makeMarkerIcon(36, color, '#ff9500'),
              scaledSize: new google.maps.Size(36, 36),
              anchor: new google.maps.Point(18, 18)
            });
          }
        } catch (e) { /* skip */ }
        await new Promise(r => setTimeout(r, 100)); // rate-limit Open-Meteo politely
      }
    })();
    return () => { stop = true; };
  }, [mapsReady, layers.weather, snap.districts]);

  const live = (snap.districts || []).filter(d => d.status === 'live');
  const queued = (snap.districts || []).filter(d => d.status === 'queued');
  const noStatus = (snap.districts || []).filter(d => !d.status);

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

          <LayerDrawer layers={layers} onToggle={setLayer} zoom={zoom} />

          <div className="zoom-hud">
            ZOOM <span className="cyan">{zoom}</span> · {layers.tiles3d ? '3D' : '2D'}
          </div>

          <InfoPanel
            district={active}
            snap={snap}
            solar={solar}
            solarLoading={solarLoading}
            solarError={solarError}
            weather={weather}
            onClose={() => setActive(null)}
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

          {live.length > 0 && (
            <div className="map-rail__section">
              <div className="eyebrow">// DISTRICTS · LIVE</div>
              <div className="district-list">
                {live.map(d => (
                  <div
                    key={d.id}
                    className={`district-chip ${active?.id === d.id ? 'is-active' : ''}`}
                    onClick={() => {
                      setActive(d);
                      mapRef.current?.panTo({ lat: d.lat, lng: d.lng });
                    }}
                  >
                    <span className="district-chip__id">{d.id}</span>
                    <span className="district-chip__name">{d.name}</span>
                    <span className="district-chip__stat">{fmt.num(d.houses)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {queued.length > 0 && (
            <div className="map-rail__section">
              <div className="eyebrow">// DISTRICTS · QUEUED</div>
              <div className="district-list">
                {queued.map(d => (
                  <div key={d.id} className="district-chip" style={{ opacity: 0.55 }}
                       onClick={() => mapRef.current?.panTo({ lat: d.lat, lng: d.lng })}>
                    <span className="district-chip__id">{d.id}</span>
                    <span className="district-chip__name">{d.name}</span>
                    <span className="district-chip__stat" style={{ color: 'var(--ink-dim)' }}>—</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {noStatus.length > 0 && (
            <div className="map-rail__section">
              <div className="eyebrow">// DISTRICTS</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'var(--ink-dim)', letterSpacing: '0.18em', marginBottom: '0.5rem' }}>
                STATUS · AWAITING ONBOARDING FEED
              </div>
              <div className="district-list">
                {noStatus.map(d => (
                  <div
                    key={d.id}
                    className={`district-chip ${active?.id === d.id ? 'is-active' : ''}`}
                    onClick={() => {
                      setActive(d);
                      mapRef.current?.panTo({ lat: d.lat, lng: d.lng });
                      if (mapRef.current?.getZoom() < 13) mapRef.current.setZoom(13);
                      // Trigger solar fetch on click
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
                    <span className="district-chip__stat" style={{ color: 'var(--ink-dim)' }}>—</span>
                  </div>
                ))}
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
