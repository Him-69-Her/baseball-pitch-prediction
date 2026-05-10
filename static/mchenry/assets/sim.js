/* =============================================================
   TINY-HUB · DATA LAYER (adapter)

   This file used to be a simulation engine that fabricated demo
   numbers. It now returns an empty state until a real backend is
   wired in. Pages call window.TinyHubSim.snapshot() and expect
   the shape below — replace the body of snapshot() (or feed
   `state` from a fetch / SSE / Firestore listener) when ready.

   ─── HOW TO WIRE REAL DATA ────────────────────────────────────

   Option A · Polling (simplest)
     async function pull() {
       const r = await fetch('https://api.tinyhub.energy/v1/snapshot');
       state = await r.json();
     }
     setInterval(pull, 5000);

   Option B · Server-Sent Events
     const sse = new EventSource('https://api.tinyhub.energy/v1/stream');
     sse.onmessage = e => { state = JSON.parse(e.data); };

   Option C · Firestore real-time
     firebase.firestore().collection('snapshots').doc('current')
       .onSnapshot(doc => { state = doc.data(); });

   ─── EXPECTED SNAPSHOT SHAPE ──────────────────────────────────
   {
     t: number,                  // monotonic tick counter (or unix ts)
     convergence: number|null,   // 0..1 AC-OPF score
     feasibility: number|null,   // 0..1
     matched:   number|null,     // count for current 5-min batch
     pending:   number|null,
     settled:   number|null,     // total settled across pilot
     mwhDay:    number|null,     // MWh routed today
     savedDay:  number|null,     // USD saved vs utility today
     surge:     number|null,     // dispatch surge multiplier
     districts: [{ id, name, lat, lng, houses?, status? }],
     trades:    [{ id, time, seller, buyer, qty, kwh,
                   district, districtName, lmp, status }]
   }
   ============================================================= */

(function () {
  'use strict';

  // McHenry County · real geographic fixtures.
  // Lat/lng are factual; everything operational (houses, status,
  // throughput) comes from the backend when wired.
  const DISTRICTS = [
    { id: 'MCH-01', name: 'McHenry',           lat: 42.330, lng: -88.267 },
    { id: 'MCH-02', name: 'Crystal Lake',      lat: 42.241, lng: -88.316 },
    { id: 'MCH-03', name: 'Woodstock',         lat: 42.314, lng: -88.448 },
    { id: 'MCH-04', name: 'Algonquin',         lat: 42.165, lng: -88.294 },
    { id: 'MCH-05', name: 'Huntley',           lat: 42.167, lng: -88.428 },
    { id: 'MCH-06', name: 'Cary',              lat: 42.211, lng: -88.237 },
    { id: 'MCH-07', name: 'Lake in the Hills', lat: 42.184, lng: -88.336 },
    { id: 'MCH-08', name: 'Marengo',           lat: 42.245, lng: -88.608 },
    { id: 'MCH-09', name: 'Harvard',           lat: 42.422, lng: -88.611 },
    { id: 'MCH-10', name: 'Wonder Lake',       lat: 42.388, lng: -88.345 },
    { id: 'MCH-11', name: 'Spring Grove',      lat: 42.443, lng: -88.246 },
    { id: 'MCH-12', name: 'Johnsburg',         lat: 42.380, lng: -88.245 }
  ];

  // Default state: empty. No fabricated metrics.
  let state = {
    t: 0,
    convergence: null,
    feasibility: null,
    matched: null,
    pending: null,
    settled: null,
    mwhDay: null,
    savedDay: null,
    surge: null,
    districts: DISTRICTS,
    trades: []
  };

  // No-op until a real data source replaces this layer.
  function tick() { /* intentionally empty */ }

  function snapshot() { return state; }

  // Sparklines / time-series — empty until real data wired
  function sparkSeries() { return []; }

  window.TinyHubSim = { tick, snapshot, sparkSeries, DISTRICTS };
  window.TinyHubData = window.TinyHubSim; // semantic alias going forward
})();
