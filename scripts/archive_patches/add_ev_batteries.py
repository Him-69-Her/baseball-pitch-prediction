#!/usr/bin/env python3
"""
TINY-HUB — EV Battery Residential Nodes for D91

Changes:
  1. app.py          — mark 15% of residential sellers as ev_battery=True
  2. dashboard.html  — render EV battery homes in cyan with special marker + legend
  3. d91_marketplace_live.py — EV battery homes added to both SELLERS and BUYERS

Run from project root:
    python3 add_ev_batteries.py
"""

from pathlib import Path

# ═══════════════════════════════════════════════════════════
# PATCH 1 — app.py: add ev_battery flag to API response
# ═══════════════════════════════════════════════════════════
APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

OLD_SELLERS_LOOP = '''        sellers = []
        for s in bdata.get("sellers", []):
            osm_id = str(s.get("osm_id", ""))
            ext_name = names.get(osm_id, "")
            label = ext_name if ext_name and ext_name != "Unidentified" else s.get("name", "")
            if not label:
                label = f"{s['category'].title()} ({s['area_sqft']:,} sqft)"
            sellers.append({
                "la": s["lat"], "ln": s["lng"],
                "n": label[:45], "t": s["town"],
                "sq": s["area_sqft"],
                "mwh": s["solar"]["mwh_per_year"],
                "cat": s["category"],
                "ti": "mega" if s["area_sqft"] >= 100000 else "large" if s["area_sqft"] >= 50000 else "medium" if s["area_sqft"] >= 20000 else "small" if s["area_sqft"] >= 10000 else "micro",
            })'''

NEW_SELLERS_LOOP = '''        # Deterministically assign 15% of residential sellers as EV battery homes
        # Uses hash of osm_id so assignment is stable across restarts
        import hashlib
        def _is_ev_battery(osm_id, category):
            if category != "residential":
                return False
            h = int(hashlib.md5(str(osm_id).encode()).hexdigest(), 16)
            return (h % 100) < 15  # 15% of residential

        sellers = []
        for s in bdata.get("sellers", []):
            osm_id = str(s.get("osm_id", ""))
            ext_name = names.get(osm_id, "")
            label = ext_name if ext_name and ext_name != "Unidentified" else s.get("name", "")
            if not label:
                label = f"{s['category'].title()} ({s['area_sqft']:,} sqft)"
            ev = _is_ev_battery(osm_id, s.get("category", ""))
            sellers.append({
                "la": s["lat"], "ln": s["lng"],
                "n": label[:45], "t": s["town"],
                "sq": s["area_sqft"],
                "mwh": s["solar"]["mwh_per_year"],
                "cat": s["category"],
                "ti": "mega" if s["area_sqft"] >= 100000 else "large" if s["area_sqft"] >= 50000 else "medium" if s["area_sqft"] >= 20000 else "small" if s["area_sqft"] >= 10000 else "micro",
                "ev": ev,   # EV battery flag
            })'''

if OLD_SELLERS_LOOP not in src:
    print("  ❌ Patch 1 failed — sellers loop not found in app.py")
    exit(1)

src = src.replace(OLD_SELLERS_LOOP, NEW_SELLERS_LOOP, 1)
APP.write_text(src, encoding="utf-8")
print("  ✅ Patch 1: app.py — ev_battery flag added to API response")


# ═══════════════════════════════════════════════════════════
# PATCH 2 — dashboard.html: EV battery marker + legend
# ═══════════════════════════════════════════════════════════
DASH = Path("templates/dashboard.html")
src = DASH.read_text(encoding="utf-8")

# Patch 2a: Add EV battery color to marker rendering
OLD_MARKER = """            const tierColor = { mega: '#ff3e5f', large: '#ff8c00', medium: '#ffb800', small: '#00ff9d', micro: '#00b4ff' };
            const tierRadius = { mega: 10, large: 7, medium: 5, small: 4, micro: 3 };

            // Plot sellers
            data.sellers.forEach(s => {
                const c = tierColor[s.ti] || '#ffb800';
                const r = tierRadius[s.ti] || 4;
                const m = L.circleMarker([s.la, s.ln], { radius: r, color: c, fillColor: c, fillOpacity: 0.6, weight: 1 })
                    .addTo(mapD91)
                    .bindPopup(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px"><b>${s.n}</b><br>${s.t}<br>${s.sq.toLocaleString()} sqft · ${s.mwh.toLocaleString()} MWh/yr<br>${s.ti} · ${s.cat}</div>`);
                // Index by partial name for flash matching
                d91SellerIndex[s.n.substring(0, 10)] = { la: s.la, ln: s.ln };"""

NEW_MARKER = """            const tierColor = { mega: '#ff3e5f', large: '#ff8c00', medium: '#ffb800', small: '#00ff9d', micro: '#00b4ff' };
            const tierRadius = { mega: 10, large: 7, medium: 5, small: 4, micro: 3 };
            const EV_COLOR = '#00ffff';   // cyan — EV battery residential homes

            // Plot sellers
            data.sellers.forEach(s => {
                const isEV = s.ev === true;
                const c = isEV ? EV_COLOR : (tierColor[s.ti] || '#ffb800');
                const r = isEV ? 5 : (tierRadius[s.ti] || 4);
                const evLabel = isEV ? '<br>⚡ EV Battery — Seller + Buyer' : '';
                const m = L.circleMarker([s.la, s.ln], {
                    radius: r,
                    color: isEV ? '#00ffff' : c,
                    fillColor: c,
                    fillOpacity: isEV ? 0.9 : 0.6,
                    weight: isEV ? 2 : 1,
                })
                    .addTo(mapD91)
                    .bindPopup(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px"><b>${s.n}</b><br>${s.t}<br>${s.sq.toLocaleString()} sqft · ${s.mwh.toLocaleString()} MWh/yr<br>${s.ti} · ${s.cat}${evLabel}</div>`);
                // Index by partial name for flash matching
                d91SellerIndex[s.n.substring(0, 10)] = { la: s.la, ln: s.ln };"""

if OLD_MARKER not in src:
    print("  ❌ Patch 2a failed — marker rendering block not found")
    exit(1)

src = src.replace(OLD_MARKER, NEW_MARKER, 1)
print("  ✅ Patch 2a: dashboard.html — EV battery cyan markers added")

# Patch 2b: Add EV battery entry to the map legend
OLD_LEGEND = """<div class="legend-item"><div class="legend-dot" style="background:#00b4ff"></div> Micro (&lt;10k sqft)</div>"""
NEW_LEGEND = """<div class="legend-item"><div class="legend-dot" style="background:#00b4ff"></div> Micro (&lt;10k sqft)</div>
            <div class="legend-item"><div class="legend-dot" style="background:#00ffff;border:1px solid #00ffff"></div> ⚡ EV Battery Home</div>"""

if OLD_LEGEND not in src:
    print("  ⚠️  Patch 2b: legend entry not found — skipping (non-critical)")
else:
    src = src.replace(OLD_LEGEND, NEW_LEGEND, 1)
    print("  ✅ Patch 2b: dashboard.html — EV battery legend entry added")

DASH.write_text(src, encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# PATCH 3 — d91_marketplace_live.py: EV homes as sellers + buyers
# ═══════════════════════════════════════════════════════════
MKT = Path("d91_marketplace_live.py")
src = MKT.read_text(encoding="utf-8")

# Add hashlib import if not present
if "import hashlib" not in src:
    src = src.replace("import math", "import math\nimport hashlib", 1)
    print("  ✅ Patch 3a: hashlib import added")

# Add EV battery helper + seller/buyer injection after sellers are loaded
OLD_SELLERS_END = 'print(f"  Sellers loaded: {len(SELLERS)}")'
NEW_SELLERS_END = '''print(f"  Sellers loaded: {len(SELLERS)}")

# ── EV Battery Residential Nodes ────────────────────────────
# 15% of residential sellers are also EV battery owners.
# They appear in both SELLERS (can discharge) and BUYERS (charge from grid).
# Uses same hash as app.py so map markers match marketplace behavior.

def _is_ev_battery(osm_id, category):
    if category != "residential":
        return False
    h = int(hashlib.md5(str(osm_id).encode()).hexdigest(), 16)
    return (h % 100) < 15

EV_SELLERS = []
EV_BUYERS  = []

for s in bdata["sellers"]:
    if not _is_ev_battery(str(s.get("osm_id", "")), s.get("category", "")):
        continue
    osm_id = str(s.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")
    if ext_name and ext_name != "Unidentified":
        label = ext_name
    elif s.get("name"):
        label = s["name"]
    else:
        label = f"EV Home {s['town']}"

    # EV battery capacity: 10-20 kWh typical home battery (0.01-0.02 MWh)
    ev_cap = round(min(s.get("capacity_mwh", 0.01) * 0.05, 0.02), 4)
    if ev_cap < 0.005:
        ev_cap = 0.01

    station_id = f"ev-{osm_id or len(EV_SELLERS)}"

    EV_SELLERS.append({
        "id": station_id,
        "osm_id": osm_id,
        "district": "IL_D91",
        "type": "battery",
        "label": f"⚡ {label[:38]}",
        "town": s["town"],
        "lat": s.get("lat", D91_LAT),
        "lng": s.get("lng", D91_LNG),
        "capacity_mwh": ev_cap,
        "real_mwh_yr": ev_cap * 365,
        "area_sqft": s.get("area_sqft", 0),
        "solar_source": "ev_battery",
        "is_ev": True,
    })

    EV_BUYERS.append({
        "id": f"evb-{osm_id or len(EV_BUYERS)}",
        "osm_id": osm_id,
        "type": "ev_home",
        "label": f"⚡ {label[:38]}",
        "town": s["town"],
        "max_bid": round(random.uniform(0.12, 0.18), 3),
        "is_ev": True,
    })

SELLERS.extend(EV_SELLERS)
BUYERS.extend(EV_BUYERS)
print(f"  EV battery homes: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")'''

if OLD_SELLERS_END not in src:
    print("  ❌ Patch 3 failed — 'Sellers loaded' print not found")
    exit(1)

src = src.replace(OLD_SELLERS_END, NEW_SELLERS_END, 1)
MKT.write_text(src, encoding="utf-8")
print("  ✅ Patch 3: d91_marketplace_live.py — EV homes added as sellers + buyers")

print()
print("  ✅ All EV battery patches applied.")
print()
print("  Next steps:")
print("  1. Restart marketplace:  screen -r marketplace → Ctrl+C → python3 -u d91_marketplace_live.py")
print("  2. Restart dashboard:    screen -r dashboard   → Ctrl+C → python3 app.py")
print("  3. Reload the dashboard map — EV homes appear in cyan ⚡")
print()
