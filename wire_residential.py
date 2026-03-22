#!/usr/bin/env python3
"""
TINY-HUB — Wire residential sellers into marketplace + dashboard API.
Run AFTER scan_residential_d91.py has populated district91_buildings.json.
"""
from pathlib import Path

# ── Patch app.py ─────────────────────────────────────────────
APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

OLD_RETURN = '''        return jsonify({
            "sellers": sellers,
            "buyers": buyers,
            "residential_count": bdata.get("residential_count", 0),
            "summary": bdata.get("summary", {}),
        })'''

NEW_RETURN = '''        # Add residential sellers (from scan_residential_d91.py)
        res_sellers = []
        for r in bdata.get("residential_sellers", []):
            res_sellers.append({
                "la": r["lat"], "ln": r["lng"],
                "n":  (r["name"] or f"Home {r['county']}") [:45],
                "t":  r["county"],
                "sq": r["area_sqft"],
                "mwh": r["solar_mwh_yr"],
                "cat": "residential",
                "ti":  "micro",
                "ev":  r.get("ev_battery", False),
            })

        return jsonify({
            "sellers": sellers + res_sellers,
            "buyers": buyers,
            "residential_count": bdata.get("residential_count", 0),
            "ev_battery_count": bdata.get("ev_battery_count", 0),
            "summary": bdata.get("summary", {}),
        })'''

if OLD_RETURN not in src:
    print("  ❌ app.py return block not found")
    exit(1)

src = src.replace(OLD_RETURN, NEW_RETURN, 1)
APP.write_text(src, encoding="utf-8")
print("  ✅ app.py — residential sellers added to map API")

# ── Patch d91_marketplace_live.py ────────────────────────────
MKT = Path("d91_marketplace_live.py")
src = MKT.read_text(encoding="utf-8")

OLD_EV = """for s in bdata["sellers"]:
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
    })"""

NEW_EV = """# Load from residential_sellers (populated by scan_residential_d91.py)
for r in bdata.get("residential_sellers", []):
    if not r.get("ev_battery", False):
        continue

    osm_id = str(r.get("osm_id", ""))
    label  = r.get("name") or f"EV Home {r.get('county','D91')}"
    ev_cap = r.get("ev_cap_mwh", 0.013)
    town   = r.get("county", "Peoria")
    station_id = f"ev-{osm_id or len(EV_SELLERS)}"

    EV_SELLERS.append({
        "id": station_id,
        "osm_id": osm_id,
        "district": "IL_D91",
        "type": "battery",
        "label": f"⚡ {label[:38]}",
        "town": town,
        "lat": r.get("lat", D91_LAT),
        "lng": r.get("lng", D91_LNG),
        "capacity_mwh": ev_cap,
        "real_mwh_yr": ev_cap * 365,
        "area_sqft": r.get("area_sqft", 1800),
        "solar_source": "ev_battery",
        "is_ev": True,
    })

    EV_BUYERS.append({
        "id": f"evb-{osm_id or len(EV_BUYERS)}",
        "osm_id": osm_id,
        "type": "ev_home",
        "label": f"⚡ {label[:38]}",
        "town": town,
        "max_bid": round(random.uniform(0.12, 0.18), 3),
        "is_ev": True,
    })"""

if OLD_EV not in src:
    print("  ❌ EV loop not found in marketplace")
    exit(1)

src = src.replace(OLD_EV, NEW_EV, 1)
MKT.write_text(src, encoding="utf-8")
print("  ✅ d91_marketplace_live.py — EV homes now loaded from residential scan")
print()
print("  ✅ Done. Run scan_residential_d91.py first, then restart both services.")
