# Tiny-Hub · McHenry County Demo

Live demo bundle for `mchenry.tinyhub.energy`. Five static pages with an
empty data state — every metric renders `—` until a real backend is wired
into the data adapter.

## Pages
| Route | Purpose |
|---|---|
| `index.html` | Lands on the live map |
| `live-map.html` | Map page · placeholder block awaiting Google Maps Cloud Build · district side rail |
| `analytics-console.html` | KPI strip, sparklines, live trade ticker, district leaderboard |
| `solver.html` | AC-OPF routing engine page (5-step pipeline + corridor table) |
| `final-report.html` | 90-day pilot summary template |
| `glossary.html` | Every term, metric, and label explained |

## Data layer

All metrics flow through `assets/sim.js` — a small adapter that pages call
via `window.TinyHubSim.snapshot()`. By default it returns an empty state
with `null` for every operational metric (matched, mwhDay, savedDay,
convergence, etc.) so nothing is fabricated. The 12 McHenry County districts
are real geographic fixtures (lat/lng), not invented.

When a backend feed is ready, replace the body of `snapshot()` with one of:

- **Polling fetch** to `/api/snapshot`
- **Server-Sent Events** stream
- **Firestore real-time listener**

Wire patterns are documented at the top of `assets/sim.js`. The expected
snapshot shape is also documented there. No page code needs to change —
populating `state` lights up every metric automatically.

## Files

```
.
├── index.html                  # → live-map
├── live-map.html
├── analytics-console.html
├── solver.html
├── final-report.html
├── glossary.html
├── livemap.jsx                 # Live-map app · placeholder + side rail
├── console.jsx                 # Analytics-console app
├── tweaks-panel.jsx            # Shared tweaks drawer
└── assets/
    ├── atmosphere.css          # Design tokens, nav, atmospheric bg
    ├── console.css             # Shared dashboard chrome
    ├── livemap.css             # Map page styles + placeholder block
    └── sim.js                  # Data adapter (empty state by default)
```

## Deploy

Three options. Pick whichever matches your infrastructure.

### Option 1 · Firebase Hosting (current path · already wired)
```bash
firebase deploy --only hosting
```

### Option 2 · GCS + CDN
```bash
./deploy.sh gcs
# defaults: PROJECT_ID=tinyhub-platform-dev · BUCKET=tinyhub-mchenry-demo
```

### Option 3 · Cloud Run + nginx
```bash
./deploy.sh cloudrun
```

## Local preview

```bash
python3 -m http.server 8080
# open http://localhost:8080
```
