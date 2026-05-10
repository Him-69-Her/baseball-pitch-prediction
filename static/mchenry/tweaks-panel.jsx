/* =============================================================
   TINY-HUB · TWEAKS PANEL
   Collapsible drawer of demo controls. Components are declared
   as plain globals; the host HTML wires them under window.Tweaks.
   ============================================================= */

const { useState, useEffect, useRef, useContext, createContext } = React;

const TweaksContext = createContext(null);

/* ----- useTweaks: state hook + localStorage persistence ----- */
function useTweaks(key, initial) {
  const [state, setState] = useState(() => {
    try {
      const raw = window.localStorage && window.localStorage.getItem('tweaks::' + key);
      if (raw) return { ...initial, ...JSON.parse(raw) };
    } catch (e) { /* ignore */ }
    return initial;
  });

  useEffect(() => {
    try {
      window.localStorage && window.localStorage.setItem('tweaks::' + key, JSON.stringify(state));
    } catch (e) { /* ignore */ }
  }, [key, state]);

  const update = (k, v) => setState(s => ({ ...s, [k]: v }));
  return [state, update, setState];
}

/* ----- TweaksPanel: drawer shell ----- */
function TweaksPanel({ title = 'Tweaks', defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`tweaks ${open ? 'is-open' : ''}`}>
      <button
        className="tweaks__toggle"
        onClick={() => setOpen(o => !o)}
        aria-label="Toggle tweaks"
      >
        <span className="tweaks__toggle-glyph">{open ? '×' : '⚙'}</span>
        <span className="tweaks__toggle-lbl">{title}</span>
      </button>
      <div className="tweaks__body">
        {children}
      </div>
      <style>{`
        .tweaks {
          position: fixed;
          top: 56px; right: 0;
          width: 320px;
          max-height: calc(100vh - 56px);
          z-index: 90;
          font-family: var(--font-mono);
          color: var(--ink-body);
          transform: translateX(calc(100% - 36px));
          transition: transform 0.3s cubic-bezier(0.2, 0.7, 0.3, 1);
        }
        .tweaks.is-open { transform: translateX(0); }

        .tweaks__toggle {
          position: absolute;
          top: 0; left: 0;
          width: 36px; height: 100%;
          background: rgba(5, 8, 14, 0.85);
          border: 1px solid var(--hair-cyan-2);
          border-right: 0;
          color: var(--cyan);
          cursor: pointer;
          font-family: var(--font-mono);
          letter-spacing: 0.18em;
          text-transform: uppercase;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: flex-start;
          padding: 0.6rem 0;
          gap: 0.6rem;
          backdrop-filter: blur(10px);
        }
        .tweaks__toggle:hover { background: rgba(0, 240, 255, 0.06); }
        .tweaks__toggle-glyph {
          font-size: 1.1rem;
          line-height: 1;
          color: var(--sun-1);
          text-shadow: 0 0 4px var(--sun-2);
        }
        .tweaks__toggle-lbl {
          writing-mode: vertical-rl;
          font-size: 0.62rem;
          letter-spacing: 0.25em;
        }

        .tweaks__body {
          margin-left: 36px;
          height: 100%;
          max-height: calc(100vh - 56px);
          overflow-y: auto;
          padding: 1rem 1rem 2rem;
          background: rgba(5, 8, 14, 0.92);
          border: 1px solid var(--hair-cyan-2);
          border-right: 0;
          backdrop-filter: blur(14px);
        }
        .tweaks__body::-webkit-scrollbar { width: 4px; }
        .tweaks__body::-webkit-scrollbar-thumb { background: var(--hair-cyan-2); }

        .tw-section {
          padding-bottom: 0.8rem;
          margin-bottom: 0.8rem;
          border-bottom: 1px dashed rgba(0, 240, 255, 0.1);
        }
        .tw-section:last-child { border-bottom: none; }
        .tw-section__title {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.72rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: var(--sun-1);
          text-shadow: 0 0 4px var(--sun-3);
          margin-bottom: 0.6rem;
        }

        .tw-row {
          display: flex;
          flex-direction: column;
          gap: 0.3rem;
          margin-bottom: 0.7rem;
        }
        .tw-row__lbl {
          display: flex;
          justify-content: space-between;
          font-size: 0.62rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: var(--ink-dim);
        }
        .tw-row__val { color: var(--cyan); }

        .tw-slider {
          -webkit-appearance: none;
          appearance: none;
          width: 100%; height: 4px;
          background: var(--hair-cyan-2);
          outline: none;
        }
        .tw-slider::-webkit-slider-thumb {
          -webkit-appearance: none; appearance: none;
          width: 12px; height: 12px;
          background: var(--cyan);
          box-shadow: 0 0 6px var(--cyan-dim);
          cursor: pointer;
        }
        .tw-slider::-moz-range-thumb {
          width: 12px; height: 12px;
          background: var(--cyan);
          box-shadow: 0 0 6px var(--cyan-dim);
          cursor: pointer;
          border: none;
        }

        .tw-toggle {
          display: flex; align-items: center; justify-content: space-between;
          font-size: 0.7rem;
          padding: 0.3rem 0;
        }
        .tw-toggle__pill {
          width: 32px; height: 16px;
          background: var(--hair-cyan-2);
          position: relative;
          cursor: pointer;
          transition: background 0.18s;
        }
        .tw-toggle__pill::after {
          content: '';
          position: absolute;
          top: 2px; left: 2px;
          width: 12px; height: 12px;
          background: var(--ink-dim);
          transition: all 0.18s;
        }
        .tw-toggle.is-on .tw-toggle__pill { background: rgba(0, 255, 136, 0.3); }
        .tw-toggle.is-on .tw-toggle__pill::after {
          left: 18px;
          background: var(--green-live);
          box-shadow: 0 0 6px var(--green-live);
        }

        .tw-input, .tw-select {
          width: 100%;
          background: rgba(0, 240, 255, 0.04);
          border: 1px solid var(--hair-cyan-2);
          color: var(--ink);
          padding: 0.45rem 0.6rem;
          font-family: var(--font-mono);
          font-size: 0.78rem;
          outline: none;
        }
        .tw-input:focus, .tw-select:focus { border-color: var(--cyan-dim); }

        .tw-radio {
          display: flex;
          gap: 0.3rem;
          flex-wrap: wrap;
        }
        .tw-radio__opt {
          flex: 1;
          padding: 0.4rem 0.5rem;
          font-size: 0.66rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          text-align: center;
          border: 1px solid var(--hair-cyan-2);
          background: rgba(0, 240, 255, 0.02);
          color: var(--ink-dim);
          cursor: pointer;
          transition: all 0.15s;
        }
        .tw-radio__opt:hover { color: var(--cyan); border-color: var(--cyan-dim); }
        .tw-radio__opt.is-on {
          color: var(--sun-1);
          border-color: var(--sun-2);
          background: rgba(255, 149, 0, 0.06);
        }

        .tw-btn {
          width: 100%;
          padding: 0.55rem 0.7rem;
          font-family: var(--font-mono);
          font-size: 0.7rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: var(--cyan);
          background: rgba(0, 240, 255, 0.04);
          border: 1px solid var(--cyan-dim);
          cursor: pointer;
          transition: all 0.15s;
        }
        .tw-btn:hover {
          background: rgba(0, 240, 255, 0.1);
          color: var(--ink);
          box-shadow: inset 0 0 12px rgba(0, 240, 255, 0.08);
        }

        .tw-color {
          width: 32px; height: 24px;
          border: 1px solid var(--hair-cyan-2);
          background: transparent;
          cursor: pointer;
          padding: 0;
        }
      `}</style>
    </div>
  );
}

function TweakSection({ title, children }) {
  return (
    <div className="tw-section">
      {title && <div className="tw-section__title">{title}</div>}
      {children}
    </div>
  );
}

function TweakSlider({ label, value, min = 0, max = 100, step = 1, onChange, fmt }) {
  const display = fmt ? fmt(value) : value;
  return (
    <div className="tw-row">
      <div className="tw-row__lbl">
        <span>{label}</span>
        <span className="tw-row__val">{display}</span>
      </div>
      <input
        type="range"
        className="tw-slider"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange && onChange(+e.target.value)}
      />
    </div>
  );
}

function TweakToggle({ label, value, onChange }) {
  return (
    <div className={`tw-toggle ${value ? 'is-on' : ''}`} onClick={() => onChange && onChange(!value)}>
      <span>{label}</span>
      <span className="tw-toggle__pill" />
    </div>
  );
}

function TweakRadio({ label, value, options, onChange }) {
  return (
    <div className="tw-row">
      {label && <div className="tw-row__lbl"><span>{label}</span></div>}
      <div className="tw-radio">
        {options.map(opt => {
          const v = typeof opt === 'object' ? opt.value : opt;
          const l = typeof opt === 'object' ? opt.label : opt;
          return (
            <div
              key={v}
              className={`tw-radio__opt ${v === value ? 'is-on' : ''}`}
              onClick={() => onChange && onChange(v)}
            >{l}</div>
          );
        })}
      </div>
    </div>
  );
}

function TweakSelect({ label, value, options, onChange }) {
  return (
    <div className="tw-row">
      {label && <div className="tw-row__lbl"><span>{label}</span></div>}
      <select
        className="tw-select"
        value={value}
        onChange={e => onChange && onChange(e.target.value)}
      >
        {options.map(opt => {
          const v = typeof opt === 'object' ? opt.value : opt;
          const l = typeof opt === 'object' ? opt.label : opt;
          return <option key={v} value={v}>{l}</option>;
        })}
      </select>
    </div>
  );
}

function TweakText({ label, value, onChange, placeholder }) {
  return (
    <div className="tw-row">
      {label && <div className="tw-row__lbl"><span>{label}</span></div>}
      <input
        type="text"
        className="tw-input"
        value={value || ''}
        placeholder={placeholder}
        onChange={e => onChange && onChange(e.target.value)}
      />
    </div>
  );
}

function TweakNumber({ label, value, min, max, step, onChange }) {
  return (
    <div className="tw-row">
      {label && <div className="tw-row__lbl"><span>{label}</span><span className="tw-row__val">{value}</span></div>}
      <input
        type="number"
        className="tw-input"
        value={value}
        min={min} max={max} step={step}
        onChange={e => onChange && onChange(+e.target.value)}
      />
    </div>
  );
}

function TweakColor({ label, value, onChange }) {
  return (
    <div className="tw-row" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
      {label && <span className="tw-row__lbl"><span>{label}</span></span>}
      <input
        type="color"
        className="tw-color"
        value={value}
        onChange={e => onChange && onChange(e.target.value)}
      />
    </div>
  );
}

function TweakButton({ label, onClick }) {
  return (
    <button className="tw-btn" onClick={onClick}>{label}</button>
  );
}
