#!/usr/bin/env python3
"""
TINY-HUB — Wire fraud_detection.py into app.py

Adds:
  GET /api/fraud/stats         — detection statistics
  GET /api/fraud/check/<id>    — check a specific trade

Run from project root:
    python3 add_fraud_detection.py
"""

from pathlib import Path

FD = Path("fraud_detection.py")
if not FD.exists():
    print("  ❌ fraud_detection.py not found. Copy it first.")
    exit(1)

APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found.")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Patch 1: Add import
if "fraud_detection" not in src:
    ANCHOR = "from smart_meter import get_meter_client"
    NEW_IMPORT = "from smart_meter import get_meter_client\nfrom fraud_detection import get_detector"

    if ANCHOR in src:
        src = src.replace(ANCHOR, NEW_IMPORT, 1)
        print("  ✅ Patch 1: fraud_detection import added")
    else:
        # Try adding after openadr import
        ANCHOR2 = "from openadr_vtn import oadr_bp, init_vtn"
        if ANCHOR2 in src:
            src = src.replace(ANCHOR2, ANCHOR2 + "\nfrom fraud_detection import get_detector", 1)
            print("  ✅ Patch 1: fraud_detection import added (alt)")
        else:
            print("  ❌ Patch 1 failed — no suitable import anchor found")
            exit(1)
else:
    print("  ⏭️  Patch 1: fraud_detection already imported")

# Patch 2: Add API routes
ANCHOR_MAIN = 'if __name__ == "__main__":'

FRAUD_ROUTES = '''
# ── Fraud Detection API ─────────────────────────────────────
@app.route("/api/fraud/stats")
def api_fraud_stats():
    """Fraud detection statistics."""
    detector = get_detector()
    return jsonify(detector.get_stats())


@app.route("/api/fraud/check", methods=["POST"])
def api_fraud_check():
    """
    Check a trade for physics-based fraud.
    POST body: {"trade": {...}, "building": {...}}
    """
    data = request.get_json(silent=True) or {}
    trade = data.get("trade", {})
    building = data.get("building")
    detector = get_detector()
    result = detector.check_trade(trade, building)
    return jsonify({
        "flagged": result.flagged,
        "severity": result.severity,
        "reason": result.reason,
        "claimed_mwh": result.claimed_mwh,
        "max_possible_mwh": result.max_possible_mwh,
        "roof_sqft": result.roof_sqft,
        "dni_wm2": result.dni_wm2,
        "checks_passed": result.checks_passed,
        "checks_failed": result.checks_failed,
    })


'''

if "/api/fraud/" in src:
    print("  ⏭️  Patch 2: fraud routes already exist")
elif ANCHOR_MAIN in src:
    src = src.replace(ANCHOR_MAIN, FRAUD_ROUTES + ANCHOR_MAIN, 1)
    print("  ✅ Patch 2: Fraud detection API routes added")
else:
    print("  ❌ Patch 2 failed — __main__ block not found")

APP.write_text(src, encoding="utf-8")

print()
print("  ✅ Fraud detection wired in.")
print()
print("  Endpoints:")
print("    GET  /api/fraud/stats   — detection statistics")
print("    POST /api/fraud/check   — check a trade against physics")
print()
print("  Physics checks:")
print("    1. Nighttime generation (sun below horizon)")
print("    2. Roof size vs claimed output (panel count × DNI × efficiency)")
print("    3. Spike detection (>3x rolling average)")
print()
print("  Rebuild: sudo docker-compose up -d --build")
print()
