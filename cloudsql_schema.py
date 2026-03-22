"""
TINY-HUB-NETWORK — Cloud SQL PostGIS Schema
Creates tables for building registry with spatial indexes.

Requires:
  pip install psycopg2-binary --break-system-packages
  source .db_env

Run:
  python3 cloudsql_schema.py
"""

import os
import sys
import psycopg2

DB_URL = os.environ.get("TINYHUB_DB_URL", "")
if not DB_URL:
    print("  Error: Set TINYHUB_DB_URL env var (or source .db_env)")
    sys.exit(1)

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

print()
print("  ╔═══════════════════════════════════════════════════════════════════╗")
print("  ║   TINY-HUB-NETWORK — PostGIS Schema Setup                       ║")
print("  ╚═══════════════════════════════════════════════════════════════════╝")
print()

# ── Enable PostGIS ──────────────────────────────────────────
print("  [1/5] Enabling PostGIS...")
cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
cur.execute("SELECT PostGIS_Version();")
version = cur.fetchone()[0]
print(f"  ✅ PostGIS {version}")

# ── Buildings table ─────────────────────────────────────────
print("  [2/5] Creating buildings table...")
cur.execute("""
    DROP TABLE IF EXISTS buildings CASCADE;
    CREATE TABLE buildings (
        id              SERIAL PRIMARY KEY,
        osm_id          BIGINT UNIQUE,
        district        VARCHAR(20) NOT NULL DEFAULT 'IL_D91',
        role            VARCHAR(10) NOT NULL CHECK (role IN ('seller', 'buyer', 'residential', 'ev_home')),
        category        VARCHAR(20) NOT NULL,
        building_type   VARCHAR(40),
        name            VARCHAR(100),
        label           VARCHAR(100),
        town            VARCHAR(50),
        area_sqft       INTEGER,
        amenity         VARCHAR(50),
        shop            VARCHAR(50),

        -- Solar data
        solar_panels    INTEGER DEFAULT 0,
        solar_roof_sqft INTEGER DEFAULT 0,
        solar_kwh_year  REAL DEFAULT 0,
        solar_mwh_year  REAL DEFAULT 0,
        solar_co2_tons  REAL DEFAULT 0,
        solar_source    VARCHAR(20) DEFAULT 'estimated',

        -- Marketplace
        capacity_mwh    REAL DEFAULT 0,
        station_id      VARCHAR(50),

        -- EV battery
        has_ev_battery  BOOLEAN DEFAULT FALSE,

        -- Geometry (SRID 4326 = WGS84 lat/lng)
        geom            GEOMETRY(Point, 4326),

        -- Timestamps
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    );
""")
print("  ✅ buildings table created")

# ── Spatial index ───────────────────────────────────────────
print("  [3/5] Creating spatial indexes...")
cur.execute("""
    CREATE INDEX idx_buildings_geom ON buildings USING GIST (geom);
    CREATE INDEX idx_buildings_district ON buildings (district);
    CREATE INDEX idx_buildings_role ON buildings (role);
    CREATE INDEX idx_buildings_town ON buildings (town);
    CREATE INDEX idx_buildings_category ON buildings (category);
    CREATE INDEX idx_buildings_district_role ON buildings (district, role);
    CREATE INDEX idx_buildings_area ON buildings (area_sqft DESC);
""")
print("  ✅ Spatial + attribute indexes created")

# ── Trades history table ────────────────────────────────────
print("  [4/5] Creating trades table...")
cur.execute("""
    DROP TABLE IF EXISTS trades CASCADE;
    CREATE TABLE trades (
        id              SERIAL PRIMARY KEY,
        trade_id        VARCHAR(50) UNIQUE,
        district        VARCHAR(20) NOT NULL,
        station_id      VARCHAR(50),
        seller_label    VARCHAR(100),
        buyer_label     VARCHAR(100),
        seller_type     VARCHAR(30),
        buyer_type      VARCHAR(30),
        mwh             REAL,
        ask_price       REAL,
        bid_price       REAL,
        settled_price   REAL,
        net_profit      REAL,
        grid_price      REAL,
        trade_status    VARCHAR(30),
        price_source    VARCHAR(20),
        lmp_mwh         REAL,
        data_mode       VARCHAR(10),
        cloud_cover     REAL,
        temperature     REAL,
        dni             REAL,
        traded_at       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX idx_trades_district ON trades (district);
    CREATE INDEX idx_trades_status ON trades (trade_status);
    CREATE INDEX idx_trades_traded_at ON trades (traded_at DESC);
    CREATE INDEX idx_trades_station ON trades (station_id);
""")
print("  ✅ trades table created")

# ── Viewport query function ─────────────────────────────────
print("  [5/5] Creating viewport query function...")
cur.execute("""
    CREATE OR REPLACE FUNCTION buildings_in_viewport(
        south DOUBLE PRECISION,
        west DOUBLE PRECISION,
        north DOUBLE PRECISION,
        east DOUBLE PRECISION,
        filter_district VARCHAR DEFAULT NULL,
        filter_role VARCHAR DEFAULT NULL,
        max_results INTEGER DEFAULT 5000
    )
    RETURNS TABLE (
        id INTEGER,
        osm_id BIGINT,
        role VARCHAR,
        category VARCHAR,
        name VARCHAR,
        label VARCHAR,
        town VARCHAR,
        area_sqft INTEGER,
        solar_mwh_year REAL,
        solar_panels INTEGER,
        solar_co2_tons REAL,
        has_ev_battery BOOLEAN,
        lat DOUBLE PRECISION,
        lng DOUBLE PRECISION
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT
            b.id, b.osm_id, b.role, b.category,
            b.name, b.label, b.town, b.area_sqft,
            b.solar_mwh_year, b.solar_panels, b.solar_co2_tons,
            b.has_ev_battery,
            ST_Y(b.geom)::DOUBLE PRECISION AS lat,
            ST_X(b.geom)::DOUBLE PRECISION AS lng
        FROM buildings b
        WHERE b.geom && ST_MakeEnvelope(west, south, east, north, 4326)
          AND (filter_district IS NULL OR b.district = filter_district)
          AND (filter_role IS NULL OR b.role = filter_role)
        ORDER BY b.area_sqft DESC
        LIMIT max_results;
    END;
    $$ LANGUAGE plpgsql STABLE;
""")
print("  ✅ buildings_in_viewport() function created")

# ── Summary ─────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
count = cur.fetchone()[0]

cur.close()
conn.close()

print()
print("  ╔═══════════════════════════════════════════════════════════════════╗")
print(f"  ║  Schema ready — {count} tables in public schema                     ║")
print("  ║  Next: python3 cloudsql_migrate.py                               ║")
print("  ╚═══════════════════════════════════════════════════════════════════╝")
print()
