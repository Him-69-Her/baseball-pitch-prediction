#!/usr/bin/env python3
"""
TINY-HUB — Wire smart_meter.py into app.py

Adds Flask API endpoints for smart meter data:
  GET /api/meter/<meter_id>/readings?hours=24
  GET /api/meter/<meter_id>/verify?claimed_kwh=5.0
  GET /api/meter/<meter_id>/summary
  POST /api/meter/upload-greenbutton  (upload Green Button XML)

Run from project root:
    python3 add_smart_meter.py
"""

from pathlib import Path

# ── Verify smart_meter.py exists ────────────────────────────
SM = Path("smart_meter.py")
if not SM.exists():
    print("  ❌ smart_meter.py not found. Copy it to your project root first.")
    exit(1)

# ── Patch app.py ────────────────────────────────────────────
APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found.")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Patch 1: Add import
ANCHOR_IMPORT = "from openadr_vtn import oadr_bp, init_vtn"
NEW_IMPORT = """from openadr_vtn import oadr_bp, init_vtn
from smart_meter import get_meter_client"""

if "smart_meter" in src:
    print("  ⏭️  Patch 1: smart_meter already imported — skipping")
elif ANCHOR_IMPORT not in src:
    print("  ❌ Patch 1 failed — openadr import not found.")
    exit(1)
else:
    src = src.replace(ANCHOR_IMPORT, NEW_IMPORT, 1)
    print("  ✅ Patch 1: smart_meter import added to app.py")

# Patch 2: Add API routes before if __name__ == "__main__":
ANCHOR_MAIN = 'if __name__ == "__main__":'

METER_ROUTES = '''
# ── Smart Meter API ─────────────────────────────────────────
@app.route("/api/meter/<meter_id>/readings")
def api_meter_readings(meter_id):
    """Get 15-min interval readings for a meter."""
    hours = request.args.get("hours", 24, type=int)
    hours = min(hours, 168)  # cap at 1 week
    client = get_meter_client()
    readings = client.get_readings(meter_id, hours=hours)
    return jsonify({
        "meter_id": meter_id,
        "hours": hours,
        "readings": [
            {"timestamp": r.timestamp, "kwh": r.kwh,
             "interval_min": r.interval_min, "source": r.source,
             "quality": r.quality}
            for r in readings
        ],
        "count": len(readings),
        "total_kwh": round(sum(r.kwh for r in readings), 2),
    })


@app.route("/api/meter/<meter_id>/verify")
def api_meter_verify(meter_id):
    """Verify a buyer's claimed demand against smart meter data."""
    claimed = request.args.get("claimed_kwh", 0, type=float)
    window = request.args.get("window_hours", 1.0, type=float)
    tolerance = request.args.get("tolerance_pct", 20.0, type=float)
    client = get_meter_client()
    v = client.verify_demand(meter_id, claimed, window, tolerance)
    return jsonify({
        "meter_id": meter_id,
        "verified": v.verified,
        "actual_kwh": v.actual_kwh,
        "claimed_kwh": v.claimed_kwh,
        "variance_pct": v.variance_pct,
        "readings_count": v.readings_count,
        "source": v.source,
        "window_hours": v.window_hours,
    })


@app.route("/api/meter/<meter_id>/summary")
def api_meter_summary(meter_id):
    """Get 24-hour consumption summary with peak/off-peak breakdown."""
    client = get_meter_client()
    return jsonify(client.get_daily_summary(meter_id))


@app.route("/api/meter/upload-greenbutton", methods=["POST"])
def api_meter_upload_gb():
    """Upload Green Button XML for a meter."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".xml"):
        return jsonify({"error": "File must be .xml"}), 400

    # Save temp file and parse
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
    f.save(tmp.name)
    tmp.close()

    client = get_meter_client()
    readings = client.parse_green_button_xml(tmp.name)

    import os
    os.unlink(tmp.name)

    if not readings:
        return jsonify({"error": "No interval data found in XML"}), 400

    return jsonify({
        "readings": [
            {"timestamp": r.timestamp, "kwh": r.kwh,
             "interval_min": r.interval_min, "source": r.source}
            for r in readings
        ],
        "count": len(readings),
        "total_kwh": round(sum(r.kwh for r in readings), 2),
    })


@app.route("/api/meter/status")
def api_meter_status():
    """Smart meter client status."""
    client = get_meter_client()
    return jsonify(client.stats())


'''

if "/api/meter/" in src:
    print("  ⏭️  Patch 2: meter routes already exist — skipping")
elif ANCHOR_MAIN not in src:
    print("  ❌ Patch 2 failed — if __name__ block not found.")
    exit(1)
else:
    src = src.replace(ANCHOR_MAIN, METER_ROUTES + ANCHOR_MAIN, 1)
    print("  ✅ Patch 2: Smart meter API routes added")

APP.write_text(src, encoding="utf-8")

print()
print("  ✅ Smart meter API wired in.")
print()
print("  Endpoints:")
print("    GET  /api/meter/<id>/readings?hours=24    — 15-min interval data")
print("    GET  /api/meter/<id>/verify?claimed_kwh=5 — verify buyer demand")
print("    GET  /api/meter/<id>/summary              — 24hr peak/off-peak")
print("    POST /api/meter/upload-greenbutton         — upload Green Button XML")
print("    GET  /api/meter/status                     — client health")
print()
print("  To enable real meter data, set: export UTILITYAPI_TOKEN=your_token")
print("  Without a token, endpoints return realistic simulated data.")
print()
print("  Restart the dashboard to apply: screen -r dashboard → Ctrl+C → python3 app.py")
print()
