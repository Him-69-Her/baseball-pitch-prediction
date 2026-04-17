"""
TINY-HUB-NETWORK — Dual-District Dashboard Server
Serves live trade data from both McHenry D63 and IL District 91.

Subscribes to both Pub/Sub topics in background threads.
Serves JSON endpoints + SSE for the dashboard frontend.

Run: python3 app.py
"""

import os
import json
import threading
from cloudsql_api import register_postgis_routes
from chain_api import register_chain_routes
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify, Response, request, session, redirect, url_for
from openadr_vtn import oadr_bp, init_vtn
from smart_meter import get_meter_client
from fraud_detection import get_detector
from websocket_handler import init_socketio, broadcast_trade as ws_broadcast_trade, broadcast_stats as ws_broadcast_stats
from vnm_reporting import VNMReporter
from google.cloud import pubsub_v1

import os as _os
import functools
import hashlib
import secrets

# ── Auth Config ─────────────────────────────────────────────
ADMIN_USER = _os.environ.get("TINYHUB_ADMIN_USER", "admin")
ADMIN_PASS = _os.environ.get("TINYHUB_ADMIN_PASS", "tinyhub2026")
SECRET_KEY = _os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.register_blueprint(oadr_bp)

# ── Auth Routes + Decorator ─────────────────────────────────
def login_required(f):
    """No-op: auth disabled for public demo mode."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


@app.before_request
def check_auth():
    """No-op: auth disabled for public demo mode."""
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    """Auth disabled — public demo mode. Redirect to landing."""
    return redirect("/")


@app.route("/logout")
def logout():
    """Auth disabled — public demo mode."""
    session.clear()
    return redirect("/")
socketio = init_socketio(app)

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tinyhub-data-dev"
D63_SUB = "energy-pulse-dashboard-sub"
D91_SUB = "d91-dashboard-sub"
D63_TOPIC = "energy-pulse"
D91_TOPIC = "d91-trades"

# ── Trade Buffers ───────────────────────────────────────────
MAX_TRADES = 200
d63_trades = deque(maxlen=MAX_TRADES)
d91_trades = deque(maxlen=MAX_TRADES)
bridge_trades = deque(maxlen=MAX_TRADES)

# ── Stats ───────────────────────────────────────────────────
stats = {
    "d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0},
    "d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0},
    "bridge": {"d63_to_d91": 0, "d91_to_d63": 0, "mwh_bridged": 0.0, "toll_revenue": 0.0},
}
stats_lock = threading.Lock()

# ── SSE Clients ─────────────────────────────────────────────
sse_clients = []


def broadcast_sse(data):
    """Send trade to all SSE clients."""
    msg = f"data: {json.dumps(data)}\n\n"
    dead = []
    for q in sse_clients:
        try:
            q.append(msg)
        except:
            dead.append(q)
    for d in dead:
        sse_clients.remove(d)


def ensure_sub(subscriber, sub_path, topic_path):
    """Create subscription if it doesn't exist."""
    publisher = pubsub_v1.PublisherClient()
    try:
        tp = publisher.topic_path(PROJECT_ID, topic_path.split("/")[-1] if "/" in topic_path else topic_path)
        subscriber.create_subscription(
            request={"name": sub_path, "topic": tp, "ack_deadline_seconds": 30}
        )
    except Exception as e:
        if "ALREADY_EXISTS" not in str(e) and "lready" not in str(e):
            print(f"  Sub error: {e}")


def d63_callback(message):
    message.ack()
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return
    trade["_district"] = "D63"
    trade["_received"] = datetime.utcnow().isoformat() + "Z"

    is_bridge = trade.get("trade_status") == "BRIDGE_LISTED"

    with stats_lock:
        if is_bridge:
            bridge_trades.appendleft(trade)
            if trade.get("origin_district") == "IL_D91":
                stats["bridge"]["d91_to_d63"] += 1
                stats["bridge"]["mwh_bridged"] += trade.get("mwh", 0)
                stats["bridge"]["toll_revenue"] += trade.get("bridge_profit", 0)
        else:
            d63_trades.appendleft(trade)
            stats["d63"]["trades"] += 1
            status = trade.get("trade_status", "")
            if "SETTLED" in status:
                stats["d63"]["settled"] += 1
                stats["d63"]["mwh"] += trade.get("mwh", 0)
                stats["d63"]["profit"] += trade.get("net_profit", 0)
                stats["d63"]["co2"] += trade.get("co2_tons", trade.get("mwh", 0) * 0.42)
            elif status == "REJECTED":
                stats["d63"]["rejected"] += 1
            if "ISLAND" in status:
                stats["d63"]["island"] += 1

    broadcast_sse(trade)


def d91_callback(message):
    message.ack()
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return
    trade["_district"] = "D91"
    trade["_received"] = datetime.utcnow().isoformat() + "Z"

    is_bridge = trade.get("trade_status") == "BRIDGE_LISTED"

    with stats_lock:
        if is_bridge:
            bridge_trades.appendleft(trade)
            if trade.get("origin_district") == "McHenry_D63":
                stats["bridge"]["d63_to_d91"] += 1
                stats["bridge"]["mwh_bridged"] += trade.get("mwh", 0)
                stats["bridge"]["toll_revenue"] += trade.get("bridge_profit", 0)
        else:
            d91_trades.appendleft(trade)
            stats["d91"]["trades"] += 1
            status = trade.get("trade_status", "")
            if "SETTLED" in status:
                stats["d91"]["settled"] += 1
                stats["d91"]["mwh"] += trade.get("mwh", 0)
                stats["d91"]["profit"] += trade.get("net_profit", 0)
                stats["d91"]["co2"] += trade.get("co2_tons", trade.get("mwh", 0) * 0.42)
            elif status == "REJECTED":
                stats["d91"]["rejected"] += 1
            if "ISLAND" in status:
                stats["d91"]["island"] += 1

    broadcast_sse(trade)


def start_subscribers():
    """Start Pub/Sub subscribers in background threads."""
    subscriber = pubsub_v1.SubscriberClient()

    d63_sub_path = subscriber.subscription_path(PROJECT_ID, D63_SUB)
    d91_sub_path = subscriber.subscription_path(PROJECT_ID, D91_SUB)

    # Ensure subs exist
    publisher = pubsub_v1.PublisherClient()
    d63_topic_path = publisher.topic_path(PROJECT_ID, D63_TOPIC)
    d91_topic_path = publisher.topic_path(PROJECT_ID, D91_TOPIC)

    for sub_path, topic_path in [(d63_sub_path, d63_topic_path), (d91_sub_path, d91_topic_path)]:
        try:
            subscriber.create_subscription(
                request={"name": sub_path, "topic": topic_path, "ack_deadline_seconds": 30}
            )
            print(f"  ✅ Created {sub_path}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
                print(f"  ⏭️  {sub_path} exists")
            else:
                print(f"  ❌ {sub_path}: {e}")

    flow = pubsub_v1.types.FlowControl(max_messages=20)
    subscriber.subscribe(d63_sub_path, callback=d63_callback, flow_control=flow)
    subscriber.subscribe(d91_sub_path, callback=d91_callback, flow_control=flow)
    print("  ✅ Subscribed to both topics")


# ── Routes ──────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("landing.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/d91map")
def d91map():
    """Serve the existing D91 building map."""
    return render_template("district91_map.html")


@app.route("/api/buildings/d91")
def api_buildings_d91():
    """Serve all D91 buildings for map rendering."""
    try:
        with open("district91_buildings.json") as f:
            bdata = json.load(f)
        names = {}
        if os.path.exists("district91_names.json"):
            with open("district91_names.json") as f:
                names = json.load(f)

        # Deterministically assign 15% of residential sellers as EV battery homes
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
            })

        buyers = []
        for b in bdata.get("commercial_buyers", []):
            osm_id = str(b.get("osm_id", ""))
            ext_name = names.get(osm_id, "")
            label = ext_name if ext_name and ext_name != "Unidentified" else b.get("name", "")
            if not label:
                label = f"{b['category'].title()} ({b['area_sqft']:,} sqft)"
            buyers.append({
                "la": b["lat"], "ln": b["lng"],
                "n": label[:45], "t": b["town"],
                "sq": b["area_sqft"],
            })

        # Add residential sellers (from scan_residential_d91.py)
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
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trades/d63")
def api_d63():
    return jsonify(list(d63_trades)[:50])


@app.route("/api/trades/d91")
def api_d91():
    return jsonify(list(d91_trades)[:50])


@app.route("/api/trades/bridge")
def api_bridge():
    return jsonify(list(bridge_trades)[:50])


@app.route("/api/stats")
def api_stats():
    with stats_lock:
        s = json.loads(json.dumps(stats))
    # Add computed fields
    for d in ["d63", "d91"]:
        total = s[d]["settled"] + s[d]["rejected"]
        s[d]["rate"] = round(s[d]["settled"] / total * 100, 1) if total > 0 else 0
        s[d]["mwh"] = round(s[d]["mwh"], 2)
        s[d]["profit"] = round(s[d]["profit"], 2)
    s["bridge"]["mwh_bridged"] = round(s["bridge"]["mwh_bridged"], 2)
    s["bridge"]["toll_revenue"] = round(s["bridge"]["toll_revenue"], 4)
    return jsonify(s)


@app.route("/api/stream")
def stream():
    """SSE endpoint for real-time trade streaming."""
    q = deque(maxlen=50)
    sse_clients.append(q)

    def generate():
        yield "data: {\"type\": \"connected\"}\n\n"
        while True:
            while q:
                yield q.popleft()
            import time
            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Start ───────────────────────────────────────────────────
print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║     TINY-HUB-NETWORK — Dual-District Dashboard                      ║")
print("  ║     McHenry D63 + IL District 91                                     ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print("  ║  Endpoints:                                                          ║")
print("  ║    /              → Live dashboard                                   ║")
print("  ║    /d91map        → D91 building map                                 ║")
print("  ║    /api/trades/d63  → D63 trade feed                                 ║")
print("  ║    /api/trades/d91  → D91 trade feed                                 ║")
print("  ║    /api/trades/bridge → Bridge trades                                ║")
print("  ║    /api/stats     → Aggregate stats                                  ║")
print("  ║    /api/stream    → SSE real-time stream                             ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")
print()

start_subscribers()

# ── OpenADR VTN init ─────────────────────────────────────────
try:
    from google.cloud import pubsub_v1 as _psv1
    _vtn_pub = _psv1.PublisherClient()
    init_vtn(_vtn_pub, PROJECT_ID, "market-ticks")
    print("  ✅ OpenADR VTN active")
    print("     POST /oadr/event/create  — issue DR event")
    print("     GET  /oadr/status        — VTN health")
except Exception as _e:
    print(f"  ⚠️  OpenADR VTN init failed: {_e}")

register_postgis_routes(app)
register_chain_routes(app)


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



# ── VNM Regulatory Reporting API ─────────────────────────────
_vnm_reporter = VNMReporter()

@app.route("/api/vnm/report")
def api_vnm_report():
    """Generate ICC-compliant VNM settlement report."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    # Collect trades from buffer
    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    return jsonify(_vnm_reporter.to_summary_dict(report))


@app.route("/api/vnm/csv")
def api_vnm_csv():
    """Download VNM credit allocations as CSV."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    csv_data = _vnm_reporter.to_csv(report)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=vnm_{district}_{period}.csv"}
    )


@app.route("/api/vnm/edi")
def api_vnm_edi():
    """Download EDI 867 format for utility interchange."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    edi_data = _vnm_reporter.to_edi_867(report)

    return Response(
        edi_data,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename=vnm_edi867_{district}_{period}.txt"}
    )



# ── WebSocket Status API ─────────────────────────────────────
@app.route("/api/ws/status")
def api_ws_status():
    """WebSocket connection status."""
    from websocket_handler import get_client_count
    return jsonify({
        "websocket_enabled": True,
        "connected_clients": get_client_count(),
        "transport": "websocket + sse",
    })


if __name__ == "__main__":
    if socketio:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
