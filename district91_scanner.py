"""
TINY-HUB-NETWORK — IL District 91 Building Footprint Scanner
Pulls actual building outlines from OpenStreetMap for all major
towns in Illinois State House District 91.

Covers: East Peoria, Washington, Morton, Pekin, Metamora,
        Eureka, El Paso, Gridley, Goodfield, Deer Creek

Outputs: district91_buildings.json
"""

import json
import math
import time
import requests
import os

# Solar API setup
try:
    from google.cloud import secretmanager
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/tiny-hub-network/secrets/Maps_API_Key/versions/latest"
    API_KEY = client.access_secret_version(request={"name": name}).payload.data.decode("UTF-8")
    HAS_SOLAR_API = True
    print("  [Solar API] Key loaded")
except:
    HAS_SOLAR_API = False
    API_KEY = None
    print("  [Solar API] Not available — using estimates only")

# District 91 towns with bounding boxes
TOWNS = [
    {"name": "East Peoria",  "south": 40.635, "north": 40.695, "west": -89.610, "east": -89.530},
    {"name": "Washington",   "south": 40.685, "north": 40.725, "west": -89.440, "east": -89.375},
    {"name": "Morton",       "south": 40.600, "north": 40.640, "west": -89.480, "east": -89.430},
    {"name": "Pekin",        "south": 40.545, "north": 40.590, "west": -89.670, "east": -89.610},
    {"name": "Metamora",     "south": 40.780, "north": 40.810, "west": -89.380, "east": -89.345},
    {"name": "Eureka",       "south": 40.710, "north": 40.740, "west": -89.290, "east": -89.255},
    {"name": "El Paso",      "south": 40.730, "north": 40.760, "west": -89.030, "east": -88.990},
    {"name": "Gridley",      "south": 40.735, "north": 40.755, "west": -88.890, "east": -88.860},
    {"name": "Goodfield",    "south": 40.620, "north": 40.640, "west": -89.290, "east": -89.260},
    {"name": "Deer Creek",   "south": 40.615, "north": 40.640, "west": -89.340, "east": -89.315},
    {"name": "Tremont",      "south": 40.520, "north": 40.545, "west": -89.510, "east": -89.480},
    {"name": "Mackinaw",     "south": 40.525, "north": 40.545, "west": -89.370, "east": -89.345},
    {"name": "Bartonville",  "south": 40.635, "north": 40.660, "west": -89.665, "east": -89.635},
    {"name": "Creve Coeur",  "south": 40.615, "north": 40.640, "west": -89.610, "east": -89.580},
    {"name": "Marquette Heights", "south": 40.605, "north": 40.625, "west": -89.630, "east": -89.605},
]

# Solar constants
SUNSHINE_HRS = 1640
PANEL_SQFT = 17.5
PANEL_KW = 0.4
MIN_ROOF_SQFT_SELLER = 5000


def calc_polygon_area_sqft(coords):
    if len(coords) < 3:
        return 0
    ref_lat = coords[0][1]
    lat_to_ft = 364000
    lon_to_ft = 364000 * math.cos(math.radians(ref_lat))
    pts = [(( lon - coords[0][0]) * lon_to_ft, (lat - coords[0][1]) * lat_to_ft) for lon, lat in coords]
    n = len(pts)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(area) / 2


def get_center(coords):
    lats = [c[1] for c in coords]
    lons = [c[0] for c in coords]
    return round(sum(lats)/len(lats), 6), round(sum(lons)/len(lons), 6)


def solar_audit(lat, lng):
    if not HAS_SOLAR_API:
        return None
    try:
        url = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
        r = requests.get(url, params={"location.latitude": lat, "location.longitude": lng, "key": API_KEY}).json()
        if "error" in r:
            return None
        sp = r.get("solarPotential", {})
        if not sp:
            return None
        panels = sp.get("maxArrayPanelsCount", 0)
        area_sqft = round(sp.get("maxArrayAreaMeters2", 0) * 10.764, 1)
        kwh = round(sp.get("maxSunshineHoursPerYear", 0) * panels * 0.4, 1)
        return {
            "panels": panels, "roof_sqft": area_sqft,
            "kwh_per_year": kwh, "mwh_per_year": round(kwh/1000, 2),
            "co2_saved_tons": round(kwh/1000 * 0.42, 2), "source": "solar_api",
        }
    except:
        return None


def estimate_solar(area_sqft):
    usable = area_sqft * 0.65
    panels = int(usable / PANEL_SQFT)
    kwh = round(SUNSHINE_HRS * panels * PANEL_KW, 1)
    return {
        "panels": panels, "roof_sqft": area_sqft,
        "kwh_per_year": kwh, "mwh_per_year": round(kwh/1000, 2),
        "co2_saved_tons": round(kwh/1000 * 0.42, 2), "source": "estimated",
    }


def fetch_buildings(town):
    query = f"""
[out:json][timeout:60];
(
  way["building"]({town['south']},{town['west']},{town['north']},{town['east']});
);
out body;
>;
out skel qt;
"""
    try:
        r = requests.get("https://overpass-api.de/api/interpreter", params={"data": query}, timeout=120)
        return r.json()
    except Exception as e:
        print(f"    Error: {e}")
        return {"elements": []}


print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║  TINY-HUB-NETWORK — IL District 91 Building Scanner        ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Towns: {len(TOWNS):>2}                                               ║")
print(f"  ║  Min seller roof: {MIN_ROOF_SQFT_SELLER:,} sqft                            ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()

all_sellers = []
all_commercial_buyers = []
all_residential = []
solar_api_hits = 0
solar_api_tries = 0

for town in TOWNS:
    print(f"  ── {town['name'].upper()} ──────────────────────────────────")
    print(f"    Fetching buildings from OSM...")
    data = fetch_buildings(town)
    time.sleep(1)  # Rate limit Overpass

    # Pass 1: collect all nodes
    nodes = {}
    for el in data["elements"]:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])

    # Pass 2: collect buildings
    buildings = []
    for el in data["elements"]:
        if el["type"] == "way" and "tags" in el:
            if "building" in el.get("tags", {}):
                coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
                if len(coords) >= 3:
                    buildings.append({"osm_id": el["id"], "tags": el["tags"], "coords": coords})

    print(f"    Found {len(buildings)} buildings")

    sellers_here = 0
    for b in buildings:
        area_sqft = round(calc_polygon_area_sqft(b["coords"]))
        lat, lng = get_center(b["coords"])
        tags = b["tags"]

        btype = tags.get("building", "yes")
        bname = tags.get("name", "")
        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")

        if btype in ("house", "residential", "apartments", "detached", "semidetached_house", "terrace"):
            category = "residential"
        elif btype in ("commercial", "retail", "industrial", "warehouse", "office", "supermarket") or shop or (amenity and amenity not in ("place_of_worship",)):
            category = "commercial"
        elif btype in ("church", "school", "public", "civic", "government") or amenity in ("school", "place_of_worship", "library", "fire_station", "police", "hospital", "community_centre"):
            category = "institutional"
        else:
            category = "residential" if area_sqft < 4000 else "commercial"

        # Solar data
        solar = None
        if area_sqft >= MIN_ROOF_SQFT_SELLER and category in ("commercial", "institutional"):
            solar_api_tries += 1
            solar = solar_audit(lat, lng)
            if solar:
                solar_api_hits += 1
            else:
                solar = estimate_solar(area_sqft)
            time.sleep(0.1)
        else:
            solar = estimate_solar(area_sqft)

        label = bname if bname else f"{category.title()} ({area_sqft:,} sqft)"

        node = {
            "osm_id": b["osm_id"],
            "name": bname,
            "label": label,
            "town": town["name"],
            "lat": lat, "lng": lng,
            "category": category,
            "building_type": btype,
            "amenity": amenity,
            "shop": shop,
            "area_sqft": area_sqft,
            "solar": solar,
        }

        if area_sqft >= MIN_ROOF_SQFT_SELLER and category in ("commercial", "institutional"):
            node["role"] = "seller"
            node["capacity_mwh"] = solar["mwh_per_year"]
            all_sellers.append(node)
            sellers_here += 1
        elif category == "residential":
            node["role"] = "buyer"
            all_residential.append(node)
        else:
            node["role"] = "buyer"
            all_commercial_buyers.append(node)

    print(f"    Sellers: {sellers_here} | Commercial buyers: {len([b for b in buildings if calc_polygon_area_sqft(b['coords']) < MIN_ROOF_SQFT_SELLER])} | Residential: counted")
    print()

# Sort sellers
all_sellers.sort(key=lambda x: x["area_sqft"], reverse=True)

# Strip coords from output to keep file size manageable
for s in all_sellers:
    if "coords" in s:
        del s["coords"]

# Print top sellers
print("  ── TOP 30 SELLERS ──────────────────────────────────────")
for i, s in enumerate(all_sellers[:30]):
    src = "🛰️" if s["solar"]["source"] == "solar_api" else "📐"
    print(f"  {i+1:>3}. {s['label'][:35]:35} | {s['town']:15} | {s['area_sqft']:>8,} sqft | {s['solar']['panels']:>5} panels | {s['solar']['mwh_per_year']:>7.2f} MWh/yr {src}")

# Save
output = {
    "district": "IL State House District 91",
    "counties": ["Peoria", "Tazewell", "Woodford", "McLean"],
    "towns_scanned": [t["name"] for t in TOWNS],
    "sellers": all_sellers,
    "commercial_buyers": all_commercial_buyers[:500],  # Cap to keep file size down
    "residential_count": len(all_residential),
    "summary": {
        "total_buildings": len(all_sellers) + len(all_commercial_buyers) + len(all_residential),
        "sellers": len(all_sellers),
        "commercial_buyers": len(all_commercial_buyers),
        "residential": len(all_residential),
        "solar_api_hits": solar_api_hits,
        "solar_api_tries": solar_api_tries,
        "seller_roof_sqft": sum(s["area_sqft"] for s in all_sellers),
        "seller_panels": sum(s["solar"]["panels"] for s in all_sellers),
        "seller_mwh_year": round(sum(s["solar"]["mwh_per_year"] for s in all_sellers), 2),
        "seller_co2_saved": round(sum(s["solar"]["co2_saved_tons"] for s in all_sellers), 2),
        "total_mwh_potential": round(sum(s["solar"]["mwh_per_year"] for s in all_sellers + all_commercial_buyers + all_residential), 2),
    },
}

with open("district91_buildings.json", "w") as f:
    json.dump(output, f, indent=2)

sm = output["summary"]
print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║           IL DISTRICT 91 — SCAN RESULTS                    ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Towns scanned:          {len(TOWNS):>6}                          ║")
print(f"  ║  Total buildings:        {sm['total_buildings']:>6}                          ║")
print(f"  ║  Qualified sellers:      {sm['sellers']:>6}                          ║")
print(f"  ║  Commercial buyers:      {sm['commercial_buyers']:>6}                          ║")
print(f"  ║  Residential:            {sm['residential']:>6}                          ║")
print(f"  ║  Solar API hits:         {sm['solar_api_hits']:>6} / {sm['solar_api_tries']}                    ║")
print(f"  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Seller roof space:  {sm['seller_roof_sqft']:>10,} sqft                  ║")
print(f"  ║  Seller panels:      {sm['seller_panels']:>10,}                       ║")
print(f"  ║  Seller MWh/year:    {sm['seller_mwh_year']:>10,.2f}                      ║")
print(f"  ║  CO2 saved/year:     {sm['seller_co2_saved']:>10,.2f} tons                 ║")
print(f"  ║  Total MWh potential:{sm['total_mwh_potential']:>10,.2f} (all buildings)     ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()
print("  📄 Saved to district91_buildings.json")
print()
