"""
TINY-HUB-NETWORK — Building Data Migration to PostGIS
Loads district91_buildings.json + residential buildings into Cloud SQL.

Requires:
  pip install psycopg2-binary --break-system-packages
  source .db_env

Run:
  python3 cloudsql_migrate.py
"""

import os
import sys
import json
import time
import psycopg2
from psycopg2.extras import execute_values

DB_URL = os.environ.get("TINYHUB_DB_URL", "")
if not DB_URL:
    print("  Error: Set TINYHUB_DB_URL env var (or source .db_env)")
    sys.exit(1)

BUILDINGS_FILE = "district91_buildings.json"
NAMES_FILE = "district91_names.json"
RESIDENTIAL_FILE = "residential_buildings.json"  # if available

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

print()
print("  ╔═══════════════════════════════════════════════════════════════════╗")
print("  ║   TINY-HUB-NETWORK — PostGIS Building Migration                 ║")
print("  ╚═══════════════════════════════════════════════════════════════════╝")
print()

# ── Load source data ────────────────────────────────────────
print("  [1/4] Loading building data...")

if not os.path.exists(BUILDINGS_FILE):
    print(f"  Error: {BUILDINGS_FILE} not found")
    sys.exit(1)

with open(BUILDINGS_FILE) as f:
    bdata = json.load(f)

names = {}
if os.path.exists(NAMES_FILE):
    with open(NAMES_FILE) as f:
        names = json.load(f)
    print(f"  Loaded {len(names)} name overrides")

sellers = bdata.get("sellers", [])
buyers = bdata.get("commercial_buyers", [])
print(f"  Sellers:    {len(sellers)}")
print(f"  Buyers:     {len(buyers)}")

# ── Helper ──────────────────────────────────────────────────
def resolve_label(building, names_overlay):
    osm_id = str(building.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")
    if ext_name and ext_name != "Unidentified":
        return ext_name
    if building.get("name"):
        return building["name"]
    cat = building.get("category", "building").title()
    sqft = building.get("area_sqft", 0)
    return f"{cat} ({sqft:,} sqft)"


def building_to_row(b, role, district="IL_D91"):
    solar = b.get("solar", {})
    label = resolve_label(b, names)
    return (
        b.get("osm_id"),
        district,
        role,
        b.get("category", "unknown"),
        b.get("building_type", ""),
        b.get("name", ""),
        label[:100],
        b.get("town", ""),
        b.get("area_sqft", 0),
        b.get("amenity", ""),
        b.get("shop", ""),
        solar.get("panels", 0),
        solar.get("roof_sqft", 0),
        solar.get("kwh_per_year", 0),
        solar.get("mwh_per_year", 0),
        solar.get("co2_saved_tons", 0),
        solar.get("source", "estimated"),
        b.get("capacity_mwh", 0),
        b.get("lat", 0),
        b.get("lng", 0),
    )


# ── Clear existing data ────────────────────────────────────
print()
print("  [2/4] Clearing existing building data...")
cur.execute("DELETE FROM buildings WHERE district = 'IL_D91';")
conn.commit()
print("  ✅ Cleared")

# ── Insert sellers ──────────────────────────────────────────
print()
print("  [3/4] Inserting sellers...")
t0 = time.time()

# Deduplicate by osm_id
seen = set()
seller_rows = []
for s in sellers:
    oid = s.get("osm_id")
    if oid and oid not in seen:
        seen.add(oid)
        seller_rows.append(building_to_row(s, "seller"))

buyer_rows_raw = []
for b in buyers:
    oid = b.get("osm_id")
    if oid and oid not in seen:
        seen.add(oid)
        buyer_rows_raw.append(building_to_row(b, "buyer"))

INSERT_SQL = """
    INSERT INTO buildings (
        osm_id, district, role, category, building_type,
        name, label, town, area_sqft, amenity, shop,
        solar_panels, solar_roof_sqft, solar_kwh_year,
        solar_mwh_year, solar_co2_tons, solar_source,
        capacity_mwh, geom
    ) VALUES %s
    ON CONFLICT (osm_id) DO UPDATE SET
        role = EXCLUDED.role,
        label = EXCLUDED.label,
        solar_mwh_year = EXCLUDED.solar_mwh_year,
        capacity_mwh = EXCLUDED.capacity_mwh,
        updated_at = NOW()
"""

TEMPLATE = """(
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s,
    %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)  -- lng, lat
)"""

# Batch insert sellers
batch_size = 500
for i in range(0, len(seller_rows), batch_size):
    batch = seller_rows[i:i + batch_size]
    execute_values(cur, INSERT_SQL, batch, template=TEMPLATE, page_size=batch_size)
    conn.commit()
    print(f"    Inserted sellers {i+1}-{min(i+batch_size, len(seller_rows))}")

t1 = time.time()
print(f"  ✅ {len(seller_rows)} sellers inserted ({t1-t0:.1f}s)")

# ── Insert buyers ───────────────────────────────────────────
print()
print("  [4/4] Inserting commercial buyers...")
t0 = time.time()

buyer_rows = buyer_rows_raw

for i in range(0, len(buyer_rows), batch_size):
    batch = buyer_rows[i:i + batch_size]
    execute_values(cur, INSERT_SQL, batch, template=TEMPLATE, page_size=batch_size)
    conn.commit()
    print(f"    Inserted buyers {i+1}-{min(i+batch_size, len(buyer_rows))}")

t1 = time.time()
print(f"  ✅ {len(buyer_rows)} buyers inserted ({t1-t0:.1f}s)")

# ── Load residential buildings if available ─────────────────
if os.path.exists(RESIDENTIAL_FILE):
    print()
    print("  [Bonus] Loading residential buildings...")
    with open(RESIDENTIAL_FILE) as f:
        residential = json.load(f)

    res_rows = [building_to_row(r, "residential") for r in residential]
    for i in range(0, len(res_rows), batch_size):
        batch = res_rows[i:i + batch_size]
        execute_values(cur, INSERT_SQL, batch, template=TEMPLATE, page_size=batch_size)
        conn.commit()
    print(f"  ✅ {len(res_rows)} residential buildings inserted")

# ── Verify ──────────────────────────────────────────────────
print()
print("  ── Verification ──────────────────────────────────────")

cur.execute("SELECT role, COUNT(*), ROUND(SUM(solar_mwh_year)::numeric, 2) FROM buildings GROUP BY role ORDER BY role;")
for row in cur.fetchall():
    print(f"    {row[0]:>15}: {row[1]:>6} buildings | {row[2]:>12} MWh/yr")

cur.execute("SELECT COUNT(*) FROM buildings;")
total = cur.fetchone()[0]

cur.execute("SELECT ST_Extent(geom) FROM buildings;")
extent = cur.fetchone()[0]

cur.execute("""
    SELECT town, COUNT(*)
    FROM buildings
    WHERE role = 'seller'
    GROUP BY town
    ORDER BY COUNT(*) DESC
    LIMIT 10;
""")
print()
print("  ── Top 10 towns by seller count ──────────────────────")
for row in cur.fetchall():
    print(f"    {row[0]:>20}: {row[1]:>5} sellers")

# ── Test viewport query ─────────────────────────────────────
print()
print("  ── Viewport query test (Peoria area) ────────────────")
cur.execute("""
    SELECT COUNT(*) FROM buildings_in_viewport(
        40.60, -89.70, 40.75, -89.50, 'IL_D91', NULL, 5000
    );
""")
vp_count = cur.fetchone()[0]
print(f"    Buildings in Peoria viewport: {vp_count}")

cur.close()
conn.close()

print()
print("  ╔═══════════════════════════════════════════════════════════════════╗")
print(f"  ║  Migration complete — {total:,} buildings in PostGIS               ║")
print(f"  ║  Spatial extent: {extent}")
print("  ║  Next: Update app.py to use PostGIS viewport queries             ║")
print("  ╚═══════════════════════════════════════════════════════════════════╝")
print()
