#!/usr/bin/env python3
"""
TINY-HUB — WebSocket Migration

Adds Flask-SocketIO alongside existing SSE for bi-directional
communication. Key features:

1. Real-time trade broadcasts via WebSocket (faster than SSE)
2. User-triggered battery discharge events (new!)
3. Live battery status queries
4. SSE kept as fallback for older clients

New events (server → client):
  "trade"           — real-time trade data
  "stats_update"    — periodic stats push
  "battery_status"  — battery VPP state

New events (client → server):
  "trigger_discharge" — user requests battery discharge
  "request_stats"     — client requests fresh stats

Run from project root:
    python3 add_websocket.py
"""

from pathlib import Path

# ══════════════════════════════════════════════════════════════
# STEP 1: Create websocket_handler.py
# ══════════════════════════════════════════════════════════════
WS = Path("websocket_handler.py")

WS_CODE = '''"""
TINY-HUB-NETWORK — WebSocket Handler
Bi-directional real-time communication via Flask-SocketIO.

Usage in app.py:
    from websocket_handler import init_socketio, broadcast_trade

    socketio = init_socketio(app)
    # In trade callbacks:
    broadcast_trade(trade_data)
    # Start server:
    socketio.run(app, host="0.0.0.0", port=5000)
"""

import json
import threading
from datetime import datetime, timezone

try:
    from flask_socketio import SocketIO, emit
    HAS_SOCKETIO = True
except ImportError:
    HAS_SOCKETIO = False
    print("  ⚠️  flask-socketio not installed. Run: pip install flask-socketio")

# ── Module state ────────────────────────────────────────────
_socketio = None
_connected_clients = 0
_clients_lock = threading.Lock()


def init_socketio(app, **kwargs):
    """Initialize SocketIO on the Flask app."""
    global _socketio

    if not HAS_SOCKETIO:
        print("  ⚠️  WebSocket disabled — flask-socketio not installed")
        return None

    _socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        ping_timeout=60,
        ping_interval=25,
        **kwargs,
    )

    @_socketio.on("connect")
    def on_connect():
        global _connected_clients
        with _clients_lock:
            _connected_clients += 1
        emit("server_info", {
            "message": "Connected to Tiny-Hub WebSocket",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "clients": _connected_clients,
        })

    @_socketio.on("disconnect")
    def on_disconnect():
        global _connected_clients
        with _clients_lock:
            _connected_clients = max(0, _connected_clients - 1)

    @_socketio.on("request_stats")
    def on_request_stats():
        """Client requests fresh stats."""
        try:
            from app import stats, stats_lock
            with stats_lock:
                s = json.loads(json.dumps(stats))
            emit("stats_update", s)
        except Exception as e:
            emit("error", {"message": str(e)})

    @_socketio.on("trigger_discharge")
    def on_trigger_discharge(data):
        """
        User triggers a battery discharge.
        data: {"station_id": "ev-12345", "mwh": 0.01}
        """
        station_id = data.get("station_id", "")
        mwh = float(data.get("mwh", 0))

        if not station_id or mwh <= 0:
            emit("discharge_result", {
                "success": False,
                "error": "Invalid station_id or mwh",
            })
            return

        try:
            from matching_engine import battery_output
            # Attempt discharge via VPP
            result_mwh = battery_output(
                station_id, f"Manual discharge {station_id}",
                capacity_mwh=mwh, grid_price_kwh=0.10, toll=0.025
            )

            emit("discharge_result", {
                "success": True,
                "station_id": station_id,
                "requested_mwh": mwh,
                "actual_mwh": result_mwh,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Broadcast to all clients
            if _socketio and result_mwh > 0:
                _socketio.emit("battery_event", {
                    "type": "manual_discharge",
                    "station_id": station_id,
                    "mwh": result_mwh,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as e:
            emit("discharge_result", {
                "success": False,
                "error": str(e)[:100],
            })

    @_socketio.on("request_battery_status")
    def on_battery_status():
        """Client requests current battery VPP status."""
        try:
            from matching_engine import MatchingEngine
            engine = MatchingEngine()
            status = engine.stats()
            emit("battery_status", status.get("batteries", {}))
        except Exception as e:
            emit("error", {"message": str(e)})

    print("  ✅ WebSocket (Flask-SocketIO) initialized")
    print("     Events: trade, stats_update, trigger_discharge, battery_status")

    return _socketio


def broadcast_trade(trade_data):
    """Broadcast a trade to all WebSocket clients."""
    if _socketio:
        _socketio.emit("trade", trade_data)


def broadcast_stats(stats_data):
    """Broadcast stats update to all WebSocket clients."""
    if _socketio:
        _socketio.emit("stats_update", stats_data)


def get_client_count():
    """Return number of connected WebSocket clients."""
    with _clients_lock:
        return _connected_clients


def get_socketio():
    """Return the SocketIO instance."""
    return _socketio
'''

WS.write_text(WS_CODE, encoding="utf-8")
print("  ✅ websocket_handler.py created")


# ══════════════════════════════════════════════════════════════
# STEP 2: Patch app.py
# ══════════════════════════════════════════════════════════════
APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Patch 1: Add import
if "websocket_handler" not in src:
    ANCHOR = "from fraud_detection import get_detector"
    NEW_IMPORT = "from fraud_detection import get_detector\nfrom websocket_handler import init_socketio, broadcast_trade as ws_broadcast_trade, broadcast_stats as ws_broadcast_stats"

    if ANCHOR in src:
        src = src.replace(ANCHOR, NEW_IMPORT, 1)
        print("  ✅ app.py Patch 1: websocket_handler import added")
    else:
        # Try alternate anchor
        for anchor in ["from vnm_reporting import VNMReporter", "from smart_meter import get_meter_client", "from openadr_vtn import oadr_bp"]:
            if anchor in src:
                src = src.replace(anchor, anchor + "\nfrom websocket_handler import init_socketio, broadcast_trade as ws_broadcast_trade, broadcast_stats as ws_broadcast_stats", 1)
                print("  ✅ app.py Patch 1: websocket_handler import added (alt)")
                break
        else:
            print("  ❌ app.py Patch 1 failed — no suitable import anchor")
            exit(1)
else:
    print("  ⏭️  app.py Patch 1: websocket already imported")

# Patch 2: Init SocketIO after app creation
if "init_socketio" not in src or "socketio = init_socketio" not in src:
    OLD_APP = "app = Flask(__name__)\napp.register_blueprint(oadr_bp)"
    NEW_APP = "app = Flask(__name__)\napp.register_blueprint(oadr_bp)\nsocketio = init_socketio(app)"

    if OLD_APP in src:
        src = src.replace(OLD_APP, NEW_APP, 1)
        print("  ✅ app.py Patch 2: SocketIO initialized")
    else:
        print("  ⚠️  app.py Patch 2: app creation block not found — add manually: socketio = init_socketio(app)")
else:
    print("  ⏭️  app.py Patch 2: socketio already initialized")

# Patch 3: Add ws_broadcast to broadcast_sse
OLD_BROADCAST = """def broadcast_sse(data):
    \"\"\"Send trade to all SSE clients.\"\"\"
    msg = f"data: {json.dumps(data)}\\n\\n"
    dead = []
    for q in sse_clients:
        try:
            q.append(msg)
        except:
            dead.append(q)
    for d in dead:
        sse_clients.remove(d)"""

NEW_BROADCAST = """def broadcast_sse(data):
    \"\"\"Send trade to all SSE + WebSocket clients.\"\"\"
    # SSE clients
    msg = f"data: {json.dumps(data)}\\n\\n"
    dead = []
    for q in sse_clients:
        try:
            q.append(msg)
        except:
            dead.append(q)
    for d in dead:
        sse_clients.remove(d)
    # WebSocket clients
    try:
        ws_broadcast_trade(data)
    except:
        pass"""

if "ws_broadcast_trade" not in src:
    if OLD_BROADCAST in src:
        src = src.replace(OLD_BROADCAST, NEW_BROADCAST, 1)
        print("  ✅ app.py Patch 3: WebSocket broadcast added to broadcast_sse()")
    else:
        print("  ⚠️  app.py Patch 3: broadcast_sse not found exactly — may need manual wiring")
else:
    print("  ⏭️  app.py Patch 3: ws_broadcast already in broadcast_sse")

# Patch 4: Replace app.run with socketio.run
OLD_RUN = 'app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)'
NEW_RUN = """if socketio:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)"""

if "socketio.run" not in src:
    if OLD_RUN in src:
        src = src.replace(OLD_RUN, NEW_RUN, 1)
        print("  ✅ app.py Patch 4: socketio.run() replaces app.run()")
    else:
        print("  ⚠️  app.py Patch 4: app.run() not found — may need manual update")
else:
    print("  ⏭️  app.py Patch 4: socketio.run already in place")

# Patch 5: Add WebSocket status endpoint
ANCHOR_MAIN = 'if __name__ == "__main__":'

WS_ROUTES = '''
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


'''

if "/api/ws/" not in src:
    if ANCHOR_MAIN in src:
        src = src.replace(ANCHOR_MAIN, WS_ROUTES + ANCHOR_MAIN, 1)
        print("  ✅ app.py Patch 5: /api/ws/status endpoint added")
else:
    print("  ⏭️  app.py Patch 5: ws routes already exist")

APP.write_text(src, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# STEP 3: Patch requirements.txt
# ══════════════════════════════════════════════════════════════
REQ = Path("requirements.txt")
if REQ.exists():
    req_src = REQ.read_text(encoding="utf-8")
    if "flask-socketio" not in req_src.lower():
        req_src = req_src.rstrip() + "\nflask-socketio>=5.3\n"
        REQ.write_text(req_src, encoding="utf-8")
        print("  ✅ requirements.txt: flask-socketio added")
    else:
        print("  ⏭️  requirements.txt: flask-socketio already listed")
else:
    print("  ⚠️  requirements.txt not found")


# ══════════════════════════════════════════════════════════════
# STEP 4: Patch dashboard.html — add WebSocket client
# ══════════════════════════════════════════════════════════════
DASH = Path("templates/dashboard.html")
if DASH.exists():
    dash_src = DASH.read_text(encoding="utf-8")

    if "io(" not in dash_src and "socket.io" not in dash_src:
        # Add SocketIO client script before closing </body>
        OLD_BODY = "</body>"
        WS_CLIENT = """<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.4/socket.io.min.js"></script>
    <script>
    // ═══ WEBSOCKET ═══
    let wsSocket = null;
    function connectWebSocket() {
        if (typeof io === 'undefined') return;
        try {
            wsSocket = io({ transports: ['websocket', 'polling'] });
            wsSocket.on('connect', () => {
                console.log('WebSocket connected');
                $('conn-status').textContent = 'WS LIVE';
                $('conn-status').style.color = 'var(--green)';
            });
            wsSocket.on('trade', (t) => { try { processTrade(t); } catch(e) {} });
            wsSocket.on('stats_update', (s) => { try { updateStats(s); } catch(e) {} });
            wsSocket.on('battery_event', (e) => {
                console.log('Battery event:', e);
            });
            wsSocket.on('disconnect', () => {
                console.log('WebSocket disconnected — falling back to SSE');
                $('conn-status').textContent = 'SSE';
                connectSSE();
            });
        } catch(e) {
            console.warn('WebSocket failed, using SSE:', e);
            connectSSE();
        }
    }
    // Try WebSocket first, fall back to SSE
    if (typeof io !== 'undefined') {
        connectWebSocket();
    } else {
        connectSSE();
    }

    // Battery discharge trigger
    function triggerDischarge(stationId, mwh) {
        if (wsSocket && wsSocket.connected) {
            wsSocket.emit('trigger_discharge', { station_id: stationId, mwh: mwh });
            wsSocket.once('discharge_result', (r) => {
                if (r.success) {
                    console.log('Discharge OK:', r.actual_mwh, 'MWh');
                } else {
                    console.warn('Discharge failed:', r.error);
                }
            });
        }
    }
    </script>
</body>"""

        if OLD_BODY in dash_src:
            dash_src = dash_src.replace(OLD_BODY, WS_CLIENT, 1)
            print("  ✅ dashboard.html: WebSocket client + battery discharge added")
        else:
            print("  ⚠️  dashboard.html: </body> not found")
    else:
        print("  ⏭️  dashboard.html: socket.io already present")

    DASH.write_text(dash_src, encoding="utf-8")
else:
    print("  ⚠️  templates/dashboard.html not found")


print()
print("  ✅ WebSocket migration complete.")
print()
print("  What changed:")
print("    • websocket_handler.py — new module (Flask-SocketIO)")
print("    • app.py — SocketIO init, broadcast to WS + SSE, socketio.run()")
print("    • dashboard.html — WebSocket client with SSE fallback")
print("    • requirements.txt — flask-socketio>=5.3 added")
print()
print("  New bi-directional events:")
print("    Server → Client: trade, stats_update, battery_event")
print("    Client → Server: trigger_discharge, request_stats, request_battery_status")
print()
print("  Install + rebuild:")
print("    pip install flask-socketio")
print("    sudo docker-compose up -d --build")
print()
