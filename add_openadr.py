#!/usr/bin/env python3
"""
TINY-HUB — Wire OpenADR VTN into app.py + marketplace curtailment handler.
"""
from pathlib import Path

# ── Patch app.py ─────────────────────────────────────────────
APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

# Add import
OLD_IMPORT = "from flask import Flask, render_template, jsonify, Response"
NEW_IMPORT = "from flask import Flask, render_template, jsonify, Response, request\nfrom openadr_vtn import oadr_bp, init_vtn"

if OLD_IMPORT not in src:
    print("  ❌ Flask import not found in app.py")
    exit(1)

src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)
print("  ✅ Patch 1: OpenADR imports added to app.py")

# Register blueprint after app = Flask(__name__)
OLD_APP = "app = Flask(__name__)"
NEW_APP = """app = Flask(__name__)
app.register_blueprint(oadr_bp)"""

if OLD_APP not in src:
    print("  ❌ app = Flask() not found")
    exit(1)

src = src.replace(OLD_APP, NEW_APP, 1)
print("  ✅ Patch 2: OpenADR blueprint registered")

# Init VTN with publisher after start_subscribers()
OLD_START = "start_subscribers()"
NEW_START = """start_subscribers()

# ── OpenADR VTN init ─────────────────────────────────────────
try:
    from google.cloud import pubsub_v1 as _psv1
    _vtn_pub = _psv1.PublisherClient()
    init_vtn(_vtn_pub, PROJECT_ID, "market-ticks")
    print("  ✅ OpenADR VTN active")
    print("     POST /oadr/event/create  — issue DR event")
    print("     GET  /oadr/status        — VTN health")
except Exception as _e:
    print(f"  ⚠️  OpenADR VTN init failed: {_e}")"""

if OLD_START not in src:
    print("  ❌ start_subscribers() not found")
    exit(1)

src = src.replace(OLD_START, NEW_START, 1)
print("  ✅ Patch 3: VTN initialized with Pub/Sub publisher")

APP.write_text(src, encoding="utf-8")

# ── Patch d91_marketplace_live.py: handle OADR_CURTAILMENT ticks ──
MKT = Path("d91_marketplace_live.py")
src = MKT.read_text(encoding="utf-8")

# Add OADR curtailment state after CURTAIL_FLOOR
OLD_CONST = "curtailed_count = 0      # running count of curtailed events"
NEW_CONST = """curtailed_count = 0      # running count of curtailed events

# OpenADR demand response state
_oadr_curtail_pct  = 0.0    # 0.0 = normal, 1.0 = full curtailment
_oadr_event_id     = None
_oadr_lock         = threading.Lock()"""

if OLD_CONST not in src:
    print("  ❌ curtailed_count constant not found")
    exit(1)

src = src.replace(OLD_CONST, NEW_CONST, 1)
print("  ✅ Patch 4: OADR state variables added to marketplace")

# Patch the on_tick callback to handle OADR messages
OLD_TICK = """def on_tick(message):
    \"\"\"Called by Pub/Sub when a market-tick arrives.\"\"\"
    message.ack()
    try:
        payload = json.loads(message.data.decode("utf-8"))
        district = payload.get("district", "")
        if district and district != "IL_D91":
            return  # Not our district
    except Exception:
        pass  # Malformed tick — run anyway

    try:
        run_trade()
    except Exception as e:
        print(f"  ⚠️  Trade error on tick: {e}")"""

NEW_TICK = """def on_tick(message):
    \"\"\"Called by Pub/Sub when a market-tick arrives.\"\"\"
    message.ack()
    try:
        payload = json.loads(message.data.decode("utf-8"))
    except Exception:
        payload = {}

    # ── Handle OpenADR curtailment commands ─────────────────
    if payload.get("type") == "OADR_CURTAILMENT":
        district = payload.get("district", "ALL")
        if district in ("ALL", "IL_D91"):
            curtail_pct = float(payload.get("curtail_pct", 0.0))
            event_id    = payload.get("event_id", "unknown")
            level_name  = payload.get("signal_name", "UNKNOWN")
            with _oadr_lock:
                global _oadr_curtail_pct, _oadr_event_id
                _oadr_curtail_pct = curtail_pct
                _oadr_event_id    = event_id if curtail_pct > 0 else None
            if curtail_pct > 0:
                print(f"  🔴 OpenADR DR EVENT: {level_name} | {curtail_pct*100:.0f}% curtailment | event={event_id}")
            else:
                print(f"  🟢 OpenADR DR EVENT cleared — returning to normal operation")
        return  # Don't run a trade on curtailment ticks

    # ── Normal market tick ───────────────────────────────────
    district = payload.get("district", "")
    if district and district != "IL_D91":
        return  # Not our district

    try:
        run_trade()
    except Exception as e:
        print(f"  ⚠️  Trade error on tick: {e}")"""

if OLD_TICK not in src:
    print("  ❌ on_tick() not found")
    exit(1)

src = src.replace(OLD_TICK, NEW_TICK, 1)
print("  ✅ Patch 5: on_tick() handles OADR_CURTAILMENT messages")

# Patch run_trade to respect OADR curtailment
OLD_CURTAIL = """    # ── Automated curtailment ──────────────────────────────
    # If the clearing price is below the floor, curtail solar sellers.
    # Batteries are exempt — they just stop discharging (handled by VPP).
    projected_clearing = round((ask_price + bid_price) / 2, 4)
    is_solar = seller.get("type") not in ("battery",) and not seller.get("is_ev", False)
    if is_solar and projected_clearing < CURTAIL_FLOOR:"""

NEW_CURTAIL = """    # ── Automated curtailment (price + OpenADR) ───────────────
    # Curtail if:
    #   1. P2P clearing price is below the floor, OR
    #   2. An active OpenADR DR event requires curtailment
    projected_clearing = round((ask_price + bid_price) / 2, 4)
    is_solar = seller.get("type") not in ("battery",) and not seller.get("is_ev", False)
    with _oadr_lock:
        oadr_pct = _oadr_curtail_pct
    if is_solar and oadr_pct > 0 and random.random() < oadr_pct:
        # OpenADR curtailment — throttle this seller
        curtailed_count += 1
        status = "CURTAILED"
        settled = 0.0
        profit = 0.0
        mwh = 0.0
    elif is_solar and projected_clearing < CURTAIL_FLOOR:"""

if OLD_CURTAIL not in src:
    print("  ❌ Curtailment block not found")
    exit(1)

src = src.replace(OLD_CURTAIL, NEW_CURTAIL, 1)
print("  ✅ Patch 6: run_trade() respects OpenADR curtailment level")

MKT.write_text(src, encoding="utf-8")

print()
print("  ✅ OpenADR VTN fully wired.")
print()
print("  Test it after restart:")
print("  curl -X POST http://35.209.110.230:5000/oadr/event/create \\")
print('       -H "Content-Type: application/json" \\')
print('       -d \'{"signal_level": 2, "duration_min": 15, "district": "IL_D91", "note": "Grid stress test"}\'')
print()
