#!/usr/bin/env python3
"""
TINY-HUB — D91 Residential Building Scanner
============================================
Queries OpenStreetMap Overpass API for all residential buildings
in Peoria, Tazewell, Woodford, and McLean counties (IL District 91).

Adds results to district91_buildings.json under "residential_sellers" key.
15% of these get EV battery flags (deterministic by osm_id hash).

Run from project root:
    python3 scan_residential_d91.py

Expected output: 10,000–50,000 residential buildings.
Takes ~2–5 minutes depending on Overpass load.
"""

import json
import time
import hashlib
import random
import math
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    print("  pip install requests")
    exit(1)

# ── Config ───────────────────────────────────────────────────
OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
BUILDINGS_FILE = Path("district91_buildings.json")

# Bounding boxes for each county [south, west, north, east]
COUNTIES = {
    "Peoria":   (40.460, -89.820, 40.980, -89.340),
    "Tazewell": (40.240, -89.760, 40.700, -89.330),
    "Woodford": (40.580, -89.340, 40.980, -89.000),
    "McLean":   (40.000, -89.320, 40.820, -88.700),
}

# Residential OSM tags to include
RESIDENTIAL_TAGS = [
    'building=house',
    'building=residential',
    'building=detached',
    'building=semidetached_house',
    'building=terrace',
    'building=apartments',
    'building=townhouse',
]

# Average home solar capacity (small rooftop system)
AVG_SOLAR_MWH_YR = 8.5     # ~8.5 MWh/yr average US rooftop solar
AVG_ROOF_SQFT    = 1800     # average home roof
EV_BATTERY_CAP   = 0.013   # 13 kWh typical home EV battery (MWh)


def _is_ev_battery(osm_id):
    """Deterministically assign EV battery to 15% of homes."""
    h = int(hashlib.md5(str(osm_id).encode()).hexdigest(), 16)
    return (h % 100) < 15


def build_overpass_query(bbox, county_name):
    """Build Overpass query for residential buildings in bbox."""
    s, w, n, e = bbox
    tag_filters = "\n  ".join([f'node["{t.split("=")[0]}"="{t.split("=")[1]}"]({s},{w},{n},{e});'
                                + f'\n  way["{t.split("=")[0]}"="{t.split("=")[1]}"]({s},{w},{n},{e});'
                                for t in RESIDENTIAL_TAGS])
    return f"""
[out:json][timeout:120];
(
  {tag_filters}
);
out center tags;
"""


def fetch_county(county_name, bbox):
    """Fetch residential buildings for one county."""
    print(f"  [{county_name}] Querying Overpass...")
    query = build_overpass_query(bbox, county_name)

    for attempt in range(3):
        try:
            r = requests.post(OVERPASS_URL, data=query, timeout=180)
            r.raise_for_status()
            data = r.json()
            elements = data.get("elements", [])
            print(f"  [{county_name}] Got {len(elements):,} elements")
            return elements
        except Exception as e:
            print(f"  [{county_name}] Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(10)
    return []


def parse_building(el, county_name):
    """Parse an Overpass element into a building record."""
    # Get coordinates
    if el["type"] == "node":
        lat, lng = el.get("lat"), el.get("lon")
    else:
        # Way with center
        center = el.get("center", {})
        lat, lng = center.get("lat"), center.get("lon")

    if lat is None or lng is None:
        return None

    osm_id  = el.get("id", 0)
    tags    = el.get("tags", {})
    name    = tags.get("name", tags.get("addr:street", ""))
    btype   = tags.get("building", "residential")

    # Estimate roof area from building levels
    levels  = int(float(tags.get("building:levels", 1)))
    area    = AVG_ROOF_SQFT  # We don't have footprint area from nodes

    # Solar estimate
    solar_mwh = round(AVG_SOLAR_MWH_YR * random.uniform(0.7, 1.3), 2)
    ev        = _is_ev_battery(osm_id)

    return {
        "osm_id":       osm_id,
        "type":         "node" if el["type"] == "node" else "way",
        "lat":          round(lat, 6),
        "lng":          round(lng, 6),
        "name":         name,
        "county":       county_name,
        "building_tag": btype,
        "area_sqft":    area,
        "levels":       levels,
        "solar_mwh_yr": solar_mwh,
        "ev_battery":   ev,
        "ev_cap_mwh":   round(EV_BATTERY_CAP * random.uniform(0.8, 1.5), 4) if ev else 0,
    }


def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  TINY-HUB — D91 Residential Building Scanner            ║")
    print("  ║  Peoria · Tazewell · Woodford · McLean Counties         ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    all_buildings = []
    seen_ids = set()

    for county_name, bbox in COUNTIES.items():
        elements = fetch_county(county_name, bbox)
        count = 0
        for el in elements:
            osm_id = el.get("id")
            if osm_id in seen_ids:
                continue
            seen_ids.add(osm_id)

            building = parse_building(el, county_name)
            if building:
                all_buildings.append(building)
                count += 1

        print(f"  [{county_name}] Parsed {count:,} unique buildings")
        time.sleep(3)  # Be polite to Overpass

    print()
    print(f"  Total residential buildings: {len(all_buildings):,}")

    ev_count = sum(1 for b in all_buildings if b["ev_battery"])
    print(f"  EV battery homes:            {ev_count:,} ({ev_count/max(len(all_buildings),1)*100:.1f}%)")

    # Load existing buildings file
    if BUILDINGS_FILE.exists():
        with open(BUILDINGS_FILE) as f:
            bdata = json.load(f)
    else:
        bdata = {}

    # Add residential sellers
    bdata["residential_sellers"] = all_buildings
    bdata["residential_count"]   = len(all_buildings)
    bdata["ev_battery_count"]    = ev_count

    # Update summary
    if "summary" not in bdata:
        bdata["summary"] = {}
    bdata["summary"]["residential_buildings"] = len(all_buildings)
    bdata["summary"]["ev_battery_homes"]      = ev_count

    with open(BUILDINGS_FILE, "w") as f:
        json.dump(bdata, f)

    print()
    print(f"  ✅ Saved to {BUILDINGS_FILE}")
    print()
    print("  Next: restart marketplace + dashboard to load residential nodes")
    print()


if __name__ == "__main__":
    main()
