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
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify, Response, request
from openadr_vtn import oadr_bp, init_vtn
from google.cloud import pubsub_v1

app = Flask(__name__)
app.register_blueprint(oadr_bp)

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
D63_SUB = "energy-pulse-dashboard-sub"
D91_SUB = "district91-energy-dashboard-sub"
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"

# ── Trade Buffers ───────────────────────────────────────────
MAX_TRADES = 200
d63_trades = deque(maxlen=MAX_TRADES)
d91_trades = deque(maxlen=MAX_TRADES)
bridge_trades = deque(maxlen=MAX_TRADES)

# ── Stats ───────────────────────────────────────────────────
stats = {
    "d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0},
    "d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0},
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
    return render_template("dashboard.html")


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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
