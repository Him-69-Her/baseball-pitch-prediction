/* =============================================================
   TINY-HUB · LIVE MAP
   Page placeholder + side rail. Numbers come from the data
   adapter (assets/sim.js). When that adapter has no backend
   wired, all metrics render as em-dashes — no fabricated data.

   ─── How to drop the real map in ────────────────────────────
   Find the <div className="map-stage"> block in App below.
   Replace the <div className="map-placeholder">…</div> inside it
   with one of:

     1. Maps Embed API (simplest):
        <iframe
          src="https://www.google.com/maps/embed/v1/view?key=YOUR_KEY&center=42.31,-88.40&zoom=10"
          style={{ position:'absolute', inset:0, width:'100%', height:'100%', border:0 }}
          loading="lazy"
        />

     2. Maps JavaScript API:
        - Add the Maps JS script tag to live-map.html
        - const mapRef = useRef(null);
        - render: <div ref={mapRef} style={{position:'absolute', inset:0}} />
        - in useEffect, new google.maps.Map(mapRef.current, {...})
   ============================================================= */

const { useState, useEffect } = React;
const { TweaksPanel, TweakSection, TweakSlider, useTweaks } = window.Tweaks;

// Display helpers — keep null/undefined out of the DOM
const dash = '—';
const fmt = {
  num: (v, d = 0) => v == null ? dash : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }),
  fixed: (v, d = 2) => v == null ? dash : Number(v).toFixed(d),
  money: v => v == null ? dash : '$' + Number(v).toLocaleString()
};

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

function SideRail({ snap, active, onSelect }) {
  const districts = snap.districts || [];
  const live = districts.filter(d => d.status === 'live');
  const queued = districts.filter(d => d.status === 'queued');
  const noStatus = districts.filter(d => !d.status);

  return (
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
                className={`district-chip ${active === d.id ? 'is-active' : ''}`}
                onClick={() => onSelect(d.id)}
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
              <div key={d.id} className="district-chip" style={{ opacity: 0.55 }}>
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
                className={`district-chip ${active === d.id ? 'is-active' : ''}`}
                onClick={() => onSelect(d.id)}
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
  );
}

function App() {
  const [snap, setSnap] = useState(() => window.TinyHubSim.snapshot());
  const [active, setActive] = useState(null);
  const [tweaks, setTweak] = useTweaks('livemap', { tickRateMs: 1000 });

  useEffect(() => {
    const id = setInterval(() => {
      window.TinyHubSim.tick();
      setSnap(window.TinyHubSim.snapshot());
    }, tweaks.tickRateMs);
    return () => clearInterval(id);
  }, [tweaks.tickRateMs]);

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
          {/* ─────────────── REPLACE THIS PLACEHOLDER WITH THE GOOGLE MAPS EMBED ─────────────── */}
          <div className="map-placeholder">
            <div className="map-placeholder__center">
              <div className="map-placeholder__eyebrow">// MAP RENDERING</div>
              <div className="map-placeholder__title">Google Maps Platform</div>
              <div className="map-placeholder__sub">
                Cloud Build pending · <span className="cyan">McHenry County</span>
              </div>
            </div>
            <div className="map-placeholder__hud">
              <span>MCHENRY COUNTY · IL</span>
              <span className="right">DATA FEED · PENDING</span>
            </div>
          </div>
          {/* ────────────────────────────────────────────────────────────────────────────────── */}
        </div>

        <SideRail snap={snap} active={active} onSelect={setActive} />
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
