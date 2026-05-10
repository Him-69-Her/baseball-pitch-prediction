/* =============================================================
   TINY-HUB · ANALYTICS CONSOLE
   Operator surface. All metrics flow from the data adapter
   (assets/sim.js). Empty by default — when real backend is
   wired, every panel lights up automatically.
   ============================================================= */
const { useState, useEffect, useMemo } = React;
const { TweaksPanel, TweakSection, TweakSlider, useTweaks } = window.Tweaks;

// Display helpers
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
        <a className="nav__link" href="live-map.html">Map</a>
        <a className="nav__link is-active" href="analytics-console.html">Console</a>
        <a className="nav__link" href="solver.html">Solver</a>
        <a className="nav__link" href="final-report.html">Final Report</a>
        <a className="nav__link" href="glossary.html">Glossary</a>
      </div>
      <div className="nav__spacer" />
    </nav>
  );
}

/* ----- Empty-state card body ----- */
function EmptyState({ label = 'AWAITING DATA FEED' }) {
  return (
    <div style={{
      padding: '3rem 1rem',
      textAlign: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: '0.7rem',
      letterSpacing: '0.22em',
      color: 'var(--ink-dim)',
      textTransform: 'uppercase'
    }}>
      <div style={{ fontSize: '0.62rem', color: 'var(--magenta)', marginBottom: '0.4rem' }}>// PENDING</div>
      <div>{label}</div>
    </div>
  );
}

/* ----- District list (no metrics — just IDs and names) ----- */
function DistrictBoard({ districts }) {
  if (!districts || districts.length === 0) return <EmptyState label="DISTRICT FEED PENDING" />;
  return (
    <div className="panel-body">
      {districts.map((d, i) => (
        <div key={d.id} style={{
          display: 'grid',
          gridTemplateColumns: '24px 1fr 1fr 80px',
          gap: '0.6rem',
          padding: '0.5rem 0',
          borderBottom: '1px dashed rgba(0,240,255,0.08)',
          alignItems: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.78rem'
        }}>
          <span style={{ color: 'var(--sun-1)', fontWeight: 700, textAlign: 'right' }}>{(i + 1).toString().padStart(2, '0')}</span>
          <span style={{ fontFamily: 'var(--font-display)', color: 'var(--ink)', letterSpacing: '0.04em', fontSize: '0.85rem' }}>{d.name}</span>
          <div style={{ position: 'relative', height: '6px', background: 'rgba(0,240,255,0.05)' }} />
          <span style={{ color: 'var(--ink-dim)', textAlign: 'right' }}>{dash} <span style={{ fontSize: '0.6rem' }}>MWh</span></span>
        </div>
      ))}
    </div>
  );
}

/* ----- App ----- */
function App() {
  const [snap, setSnap] = useState(() => window.TinyHubSim.snapshot());
  const [tweaks, setTweak] = useTweaks('console', { tickRateMs: 1000 });

  useEffect(() => {
    const id = setInterval(() => {
      window.TinyHubSim.tick();
      setSnap(window.TinyHubSim.snapshot());
    }, tweaks.tickRateMs);
    return () => clearInterval(id);
  }, [tweaks.tickRateMs]);

  const hasTrades = snap.trades && snap.trades.length > 0;

  return (
    <>
      <div className="atmos" aria-hidden="true">
        <div className="atmos__stars" />
        <div className="atmos__horizon" />
        <div className="atmos__grid" />
      </div>
      <NavBar />
      <main className="console-shell">
        <div className="eyebrow">// TINYHUB ENERGY · ANALYTICS</div>
        <h1 className="console-h1">Analytics Console</h1>
        <p className="console-sub">
          Operator's view of the live network. Every panel will fill in once the
          backend data feed is wired — until then, the layout shows where each
          metric will land in the <em>5-minute batch</em> cycle.
        </p>

        <div className="kpi-strip">
          <div className="ms">
            <span className="ms__lbl">MWh · today</span>
            <span className="ms__val">{fmt.fixed(snap.mwhDay, 1)}<span className="ms__unit">MWh</span></span>
          </div>
          <div className="ms">
            <span className="ms__lbl">Saved vs Utility</span>
            <span className="ms__val">{fmt.money(snap.savedDay)}</span>
          </div>
          <div className="ms">
            <span className="ms__lbl">Matched · batch</span>
            <span className="ms__val">{fmt.num(snap.matched)}</span>
          </div>
          <div className="ms">
            <span className="ms__lbl">Pending</span>
            <span className="ms__val">{fmt.num(snap.pending)}</span>
          </div>
          <div className="ms">
            <span className="ms__lbl">Convergence</span>
            <span className="ms__val">{fmt.fixed(snap.convergence, 3)}</span>
          </div>
          <div className="ms">
            <span className="ms__lbl">Settled · total</span>
            <span className="ms__val">{fmt.num(snap.settled)}</span>
          </div>
        </div>

        <div className="console-grid console-grid--3">
          <div className="card">
            <div className="card__head">
              <div>
                <div className="card__title">kWh / hour · last 12h</div>
                <div className="card__sub">network throughput · solar curve</div>
              </div>
            </div>
            <EmptyState label="ENERGY THROUGHPUT FEED PENDING" />
          </div>
          <div className="card">
            <div className="card__head">
              <div>
                <div className="card__title cyan">MISO LMP · $/MWh</div>
                <div className="card__sub">wholesale price · 12h</div>
              </div>
            </div>
            <EmptyState label="MISO LMP FEED PENDING" />
          </div>
          <div className="card">
            <div className="card__head">
              <div>
                <div className="card__title mag">Surge multiplier · 12h</div>
                <div className="card__sub">demand vs. supply pressure</div>
              </div>
            </div>
            <EmptyState label="DISPATCH FEED PENDING" />
          </div>
        </div>

        <div className="console-grid console-grid--2">
          <div className="card">
            <div className="card__head">
              <div>
                <div className="card__title">▸ Match Queue · live</div>
                <div className="card__sub">5-min batch · settlement events</div>
              </div>
              <span className="pill" style={{ borderColor: 'var(--hair-cyan-2)', color: 'var(--ink-dim)' }}>PENDING</span>
            </div>
            {hasTrades ? (
              <div className="ticker">
                {snap.trades.slice(0, 20).map(t => (
                  <div key={t.id + t.time} className="ticker__row">
                    <span className="ticker__time">T+{String(t.time).padStart(4, '0')}</span>
                    <span className="ticker__addr">{t.seller}</span>
                    <span className="ticker__addr" style={{ color: 'var(--sun-1)' }}>{t.buyer}</span>
                    <span className="ticker__qty">{Number(t.qty).toFixed(2)} <span style={{ color: 'var(--ink-dim)', fontSize: '0.6rem' }}>kWh</span></span>
                    <span className={`ticker__status ${t.status}`}>{t.status === 'matched' ? 'MATCHED' : 'PENDING'}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState label="SETTLEMENT FEED PENDING" />
            )}
          </div>
          <div className="card">
            <div className="card__head">
              <div>
                <div className="card__title cyan">▸ Districts · MWh today</div>
                <div className="card__sub">12 communities · ranked by volume</div>
              </div>
            </div>
            <DistrictBoard districts={snap.districts} />
          </div>
        </div>
      </main>

      <TweaksPanel title="Console Controls">
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
