"""
TINY-HUB-NETWORK — PostGIS Viewport Query Module
Drop-in replacement for the JSON-based /api/buildings/d91 endpoint.

Provides spatial bounding-box queries so the map only loads
buildings in the current viewport instead of the entire JSON.

Integration:
  1. source .db_env
  2. In app.py, add:
       from cloudsql_api import register_postgis_routes
       register_postgis_routes(app)
  3. The old /api/buildings/d91 endpoint becomes the fallback

New endpoints:
  GET /api/buildings/viewport?south=X&west=X&north=X&east=X&district=X&role=X&limit=X
  GET /api/buildings/stats
  GET /api/buildings/search?q=caterpillar&district=IL_D91
  GET /api/buildings/<id>

Requires:
  pip install psycopg2-binary --break-system-packages
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import request, jsonify

DB_URL = os.environ.get("TINYHUB_DB_URL", "")

# ── Connection Pool (simple) ────────────────────────────────
_conn = None


def get_conn():
    """Get or create a database connection."""
    global _conn
    if _conn is None or _conn.closed:
        if not DB_URL:
            return None
        _conn = psycopg2.connect(DB_URL)
        _conn.autocommit = True
    return _conn


def query(sql, params=None):
    """Execute a query and return rows as dicts."""
    conn = get_conn()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except Exception as e:
        print(f"  [PostGIS] Query error: {e}")
        # Reset connection on error
        global _conn
        try:
            _conn.close()
        except:
            pass
        _conn = None
        return []


def query_one(sql, params=None):
    """Execute a query and return single row."""
    rows = query(sql, params)
    return rows[0] if rows else None


# ══════════════════════════════════════════════════════════════
# FLASK ROUTE REGISTRATION
# ══════════════════════════════════════════════════════════════

def register_postgis_routes(app):
    """Register PostGIS-backed API routes on a Flask app."""

    @app.route("/api/buildings/viewport")
    def api_buildings_viewport():
        """
        Spatial viewport query.
        Params: south, west, north, east (required)
                district (optional, e.g. IL_D91)
                role (optional: seller, buyer, residential, ev_home)
                limit (optional, default 5000)
        """
        try:
            south = float(request.args.get("south", 0))
            west = float(request.args.get("west", 0))
            north = float(request.args.get("north", 0))
            east = float(request.args.get("east", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "south, west, north, east required as floats"}), 400

        if south == 0 and west == 0 and north == 0 and east == 0:
            return jsonify({"error": "Provide viewport bounds: south, west, north, east"}), 400

        district = request.args.get("district")
        role = request.args.get("role")
        limit = request.args.get("limit", 5000, type=int)
        limit = min(limit, 10000)

        rows = query("""
            SELECT * FROM buildings_in_viewport(
                %s, %s, %s, %s, %s, %s, %s
            );
        """, (south, west, north, east, district, role, limit))

        # Format for map rendering (compact keys to reduce payload)
        buildings = []
        for r in rows:
            buildings.append({
                "id": r["id"],
                "la": r["lat"],
                "ln": r["lng"],
                "n": r["label"] or r["name"] or "",
                "t": r["town"] or "",
                "sq": r["area_sqft"] or 0,
                "mwh": r["solar_mwh_year"] or 0,
                "cat": r["category"] or "",
                "role": r["role"],
                "panels": r["solar_panels"] or 0,
                "co2": r["solar_co2_tons"] or 0,
                "ev": r["has_ev_battery"] or False,
                "ti": (
                    "mega" if (r["area_sqft"] or 0) >= 100000 else
                    "large" if (r["area_sqft"] or 0) >= 50000 else
                    "medium" if (r["area_sqft"] or 0) >= 20000 else
                    "small" if (r["area_sqft"] or 0) >= 10000 else
                    "micro"
                ),
            })

        return jsonify({
            "buildings": buildings,
            "count": len(buildings),
            "viewport": {"south": south, "west": west, "north": north, "east": east},
        })

    @app.route("/api/buildings/stats")
    def api_buildings_stats():
        """Aggregate building statistics from PostGIS."""
        district = request.args.get("district")

        where = "WHERE 1=1"
        params = []
        if district:
            where += " AND district = %s"
            params.append(district)

        row = query_one(f"""
            SELECT
                COUNT(*) AS total_buildings,
                COUNT(*) FILTER (WHERE role = 'seller') AS sellers,
                COUNT(*) FILTER (WHERE role = 'buyer') AS buyers,
                COUNT(*) FILTER (WHERE role = 'residential') AS residential,
                COUNT(*) FILTER (WHERE role = 'ev_home') AS ev_homes,
                COALESCE(SUM(solar_mwh_year), 0) AS total_mwh_year,
                COALESCE(SUM(solar_panels), 0) AS total_panels,
                COALESCE(SUM(solar_co2_tons), 0) AS total_co2_tons,
                COALESCE(SUM(area_sqft), 0) AS total_roof_sqft,
                COUNT(DISTINCT town) AS towns
            FROM buildings
            {where};
        """, params)

        if not row:
            return jsonify({"error": "Database unavailable"}), 503

        # Per-town breakdown
        towns = query(f"""
            SELECT town, COUNT(*) AS buildings,
                   SUM(solar_mwh_year) AS mwh_year,
                   COUNT(*) FILTER (WHERE role = 'seller') AS sellers
            FROM buildings
            {where}
            GROUP BY town
            ORDER BY buildings DESC;
        """, params)

        return jsonify({
            "total_buildings": row["total_buildings"],
            "sellers": row["sellers"],
            "buyers": row["buyers"],
            "residential": row["residential"],
            "ev_homes": row["ev_homes"],
            "total_mwh_year": round(float(row["total_mwh_year"]), 2),
            "total_panels": row["total_panels"],
            "total_co2_tons": round(float(row["total_co2_tons"]), 2),
            "total_roof_sqft": row["total_roof_sqft"],
            "towns": [{"name": t["town"], "buildings": t["buildings"],
                       "mwh_year": round(float(t["mwh_year"] or 0), 2),
                       "sellers": t["sellers"]} for t in towns],
        })

    @app.route("/api/buildings/search")
    def api_buildings_search():
        """Full-text search for buildings by name/label."""
        q = request.args.get("q", "").strip()
        if not q or len(q) < 2:
            return jsonify({"error": "Query must be at least 2 characters"}), 400

        district = request.args.get("district")
        limit = request.args.get("limit", 50, type=int)

        where = "WHERE (LOWER(name) LIKE %s OR LOWER(label) LIKE %s)"
        params = [f"%{q.lower()}%", f"%{q.lower()}%"]

        if district:
            where += " AND district = %s"
            params.append(district)

        rows = query(f"""
            SELECT id, osm_id, district, role, category, name, label, town,
                   area_sqft, solar_mwh_year, solar_panels, solar_co2_tons,
                   has_ev_battery, capacity_mwh,
                   ST_Y(geom) AS lat, ST_X(geom) AS lng
            FROM buildings
            {where}
            ORDER BY area_sqft DESC
            LIMIT %s;
        """, params + [limit])

        return jsonify({
            "results": [{
                "id": r["id"],
                "osm_id": r["osm_id"],
                "district": r["district"],
                "role": r["role"],
                "category": r["category"],
                "name": r["name"],
                "label": r["label"],
                "town": r["town"],
                "area_sqft": r["area_sqft"],
                "solar_mwh_year": r["solar_mwh_year"],
                "solar_panels": r["solar_panels"],
                "co2_tons": r["solar_co2_tons"],
                "has_ev": r["has_ev_battery"],
                "lat": r["lat"],
                "lng": r["lng"],
            } for r in rows],
            "count": len(rows),
            "query": q,
        })

    @app.route("/api/buildings/<int:building_id>")
    def api_building_detail(building_id):
        """Get full detail for a single building."""
        row = query_one("""
            SELECT *, ST_Y(geom) AS lat, ST_X(geom) AS lng
            FROM buildings WHERE id = %s;
        """, (building_id,))

        if not row:
            return jsonify({"error": "Building not found"}), 404

        return jsonify({
            "id": row["id"],
            "osm_id": row["osm_id"],
            "district": row["district"],
            "role": row["role"],
            "category": row["category"],
            "building_type": row["building_type"],
            "name": row["name"],
            "label": row["label"],
            "town": row["town"],
            "area_sqft": row["area_sqft"],
            "amenity": row["amenity"],
            "shop": row["shop"],
            "solar": {
                "panels": row["solar_panels"],
                "roof_sqft": row["solar_roof_sqft"],
                "kwh_year": row["solar_kwh_year"],
                "mwh_year": row["solar_mwh_year"],
                "co2_tons": row["solar_co2_tons"],
                "source": row["solar_source"],
            },
            "capacity_mwh": row["capacity_mwh"],
            "station_id": row["station_id"],
            "has_ev_battery": row["has_ev_battery"],
            "lat": row["lat"],
            "lng": row["lng"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    print("  ✅ PostGIS viewport routes registered")
    print("     GET /api/buildings/viewport?south=X&west=X&north=X&east=X")
    print("     GET /api/buildings/stats")
    print("     GET /api/buildings/search?q=caterpillar")
    print("     GET /api/buildings/<id>")
