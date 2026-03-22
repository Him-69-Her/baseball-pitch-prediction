"""
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
