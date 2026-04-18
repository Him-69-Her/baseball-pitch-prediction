"""
TINY-HUB-NETWORK — Inverter Telemetry API
Authenticated REST endpoint for physical Enphase/SolarEdge inverters
to POST live generation data into the marketplace.

Port: 5001
Auth: X-API-Key header

Endpoints:
  POST /api/v1/inverter/report      — submit generation telemetry
  POST /api/v1/inverter/register     — register a new device
  GET  /api/v1/inverter/devices      — list registered devices + last reading
  GET  /api/v1/inverter/readings/:id — recent readings for a device
  GET  /api/v1/inverter/health       — service health

Publishes telemetry to:
  - inverter-telemetry  (dedicated topic for archival / BigQuery)
  - energy-pulse OR district91-energy (so marketplace uses real data)

Run:
  python3 -u inverter_api.py
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import threading
from datetime import datetime, timezone
from collections import deque, defaultdict
from flask import Flask, request, jsonify

# ── Optional: Pub/Sub (graceful if unavailable) ─────────────
try:
    from google.cloud import pubsub_v1
    PUBSUB_AVAILABLE = True
except ImportError:
    PUBSUB_AVAILABLE = False

app = Flask(__name__)

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
PORT = int(os.environ.get("INVERTER_API_PORT", 5001))

TELEMETRY_TOPIC = "inverter-telemetry"
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"

# District mapping
DISTRICT_TOPICS = {
    "McHenry_D63": D63_TOPIC,
    "IL_D91": D91_TOPIC,
}

# ── API Key Management ──────────────────────────────────────
# Master key for admin operations (register new devices)
# In production, pull from Secret Manager
MASTER_API_KEY = os.environ.get("INVERTER_MASTER_KEY", "thub-master-" + secrets.token_hex(16))

# Device keys: device_id -> {key, district, device_type, ...}
_devices = {}
_devices_lock = threading.Lock()

# ── Telemetry Storage ───────────────────────────────────────
MAX_READINGS = 500
_readings = defaultdict(lambda: deque(maxlen=MAX_READINGS))
_readings_lock = threading.Lock()

# ── Rate Limiting ───────────────────────────────────────────
_last_report = {}  # device_id -> timestamp
RATE_LIMIT_SECONDS = 30  # min interval between reports per device

# ── Stats ───────────────────────────────────────────────────
_stats = {
    "total_reports": 0,
    "total_kwh": 0.0,
    "rejected_auth": 0,
    "rejected_rate": 0,
    "rejected_validation": 0,
    "started": datetime.now(timezone.utc).isoformat(),
}
_stats_lock = threading.Lock()

# ── Pub/Sub Publisher ───────────────────────────────────────
publisher = None
topic_paths = {}

if PUBSUB_AVAILABLE:
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_paths = {
            "telemetry": publisher.topic_path(PROJECT_ID, TELEMETRY_TOPIC),
            "d63": publisher.topic_path(PROJECT_ID, D63_TOPIC),
            "d91": publisher.topic_path(PROJECT_ID, D91_TOPIC),
        }
    except Exception as e:
        print(f"  [Inverter API] Pub/Sub init error: {e}")
        publisher = None


def publish(topic_key, data):
    """Publish JSON to a Pub/Sub topic. Fire-and-forget."""
    if not publisher or topic_key not in topic_paths:
        return
    try:
        msg = json.dumps(data).encode("utf-8")
        publisher.publish(topic_paths[topic_key], msg)
    except Exception as e:
        print(f"  [Pub/Sub] Publish error ({topic_key}): {e}")


# ── Auth Helpers ────────────────────────────────────────────
def check_master_key():
    """Verify the master API key from request headers."""
    key = request.headers.get("X-API-Key", "")
    return hmac.compare_digest(key, MASTER_API_KEY)


def check_device_key():
    """Verify a device API key. Returns device_id or None."""
    key = request.headers.get("X-API-Key", "")
    if not key:
        return None
    with _devices_lock:
        for dev_id, dev in _devices.items():
            if hmac.compare_digest(key, dev["api_key"]):
                return dev_id
    return None


def check_any_key():
    """Accept either master or device key. Returns (role, device_id)."""
    if check_master_key():
        return "master", None
    dev_id = check_device_key()
    if dev_id:
        return "device", dev_id
    return None, None


# ── Validation ──────────────────────────────────────────────
VALID_DEVICE_TYPES = ["enphase", "solaredge", "sma", "fronius", "tesla_pw", "generac", "other"]
VALID_DISTRICTS = ["McHenry_D63", "IL_D91"]


def validate_report(data, device_id):
    """Validate a telemetry report payload."""
    errors = []

    # Required fields
    for field in ["watts", "timestamp"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Watts must be numeric and reasonable (0 to 500kW per device)
    try:
        watts = float(data["watts"])
        if watts < 0:
            errors.append("watts cannot be negative")
        if watts > 500000:
            errors.append("watts exceeds 500kW device maximum")
    except (TypeError, ValueError):
        errors.append("watts must be a number")

    # Timestamp must be ISO format and not too old
    try:
        ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > 600:  # 10 min stale limit
            errors.append("timestamp is more than 10 minutes old")
        if age < -60:  # 1 min future tolerance
            errors.append("timestamp is in the future")
    except (TypeError, ValueError, AttributeError):
        errors.append("timestamp must be ISO 8601 format")

    # Optional: energy_wh cumulative reading
    if "energy_wh" in data:
        try:
            ewh = float(data["energy_wh"])
            if ewh < 0:
                errors.append("energy_wh cannot be negative")
        except (TypeError, ValueError):
            errors.append("energy_wh must be a number")

    return errors


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/api/v1/inverter/health", methods=["GET"])
def health():
    """Service health — no auth required."""
    with _devices_lock:
        num_devices = len(_devices)
    with _stats_lock:
        total = _stats["total_reports"]
        kwh = _stats["total_kwh"]
    return jsonify({
        "service": "inverter-telemetry-api",
        "status": "healthy",
        "version": "1.0.0",
        "registered_devices": num_devices,
        "total_reports": total,
        "total_kwh_ingested": round(kwh, 2),
        "pubsub_connected": publisher is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/v1/inverter/register", methods=["POST"])
def register_device():
    """Register a new inverter device. Requires master key."""
    if not check_master_key():
        with _stats_lock:
            _stats["rejected_auth"] += 1
        return jsonify({"error": "Invalid or missing master API key"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # Required fields
    device_id = data.get("device_id", "").strip()
    district = data.get("district", "").strip()
    device_type = data.get("device_type", "other").strip().lower()
    station_id = data.get("station_id", "").strip()  # maps to marketplace seller
    label = data.get("label", device_id).strip()
    lat = data.get("lat")
    lng = data.get("lng")
    capacity_kw = data.get("capacity_kw", 0)

    errors = []
    if not device_id:
        errors.append("device_id required")
    if district not in VALID_DISTRICTS:
        errors.append(f"district must be one of: {VALID_DISTRICTS}")
    if device_type not in VALID_DEVICE_TYPES:
        errors.append(f"device_type must be one of: {VALID_DEVICE_TYPES}")
    if not station_id:
        errors.append("station_id required (maps to marketplace seller)")

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    # Check duplicate
    with _devices_lock:
        if device_id in _devices:
            return jsonify({"error": f"Device {device_id} already registered"}), 409

    # Generate device API key
    device_key = f"thub-dev-{secrets.token_hex(24)}"

    device_record = {
        "device_id": device_id,
        "api_key": device_key,
        "district": district,
        "device_type": device_type,
        "station_id": station_id,
        "label": label,
        "lat": lat,
        "lng": lng,
        "capacity_kw": capacity_kw,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "last_report": None,
        "last_watts": None,
        "total_reports": 0,
        "total_kwh": 0.0,
    }

    with _devices_lock:
        _devices[device_id] = device_record

    print(f"  [Register] {device_type} device '{label}' ({device_id}) -> {district} / {station_id}")

    # Publish registration event
    publish("telemetry", {
        "type": "DEVICE_REGISTERED",
        "device_id": device_id,
        "district": district,
        "device_type": device_type,
        "station_id": station_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return jsonify({
        "status": "registered",
        "device_id": device_id,
        "api_key": device_key,
        "district": district,
        "station_id": station_id,
        "note": "Store this API key securely. Use it in X-API-Key header for /report calls.",
    }), 201


@app.route("/api/v1/inverter/report", methods=["POST"])
def report_telemetry():
    """Submit inverter telemetry. Requires device API key."""
    # Auth
    role, device_id = check_any_key()

    if role == "master":
        # Master key can report on behalf of any device
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        device_id = data.get("device_id", "").strip()
        if not device_id:
            return jsonify({"error": "device_id required when using master key"}), 400
    elif role == "device":
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        # Device can only report for itself
        if "device_id" in data and data["device_id"] != device_id:
            return jsonify({"error": "Device key mismatch"}), 403
        data["device_id"] = device_id
    else:
        with _stats_lock:
            _stats["rejected_auth"] += 1
        return jsonify({"error": "Invalid or missing API key"}), 401

    # Check device exists
    with _devices_lock:
        device = _devices.get(device_id)
    if not device:
        return jsonify({"error": f"Device {device_id} not registered"}), 404

    # Rate limit
    now = time.time()
    last = _last_report.get(device_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (now - last))
        with _stats_lock:
            _stats["rejected_rate"] += 1
        return jsonify({
            "error": "Rate limited",
            "retry_after_seconds": remaining,
        }), 429

    # Validate
    errors = validate_report(data, device_id)
    if errors:
        with _stats_lock:
            _stats["rejected_validation"] += 1
        return jsonify({"error": "Validation failed", "details": errors}), 400

    # ── Process the report ──────────────────────────────────
    _last_report[device_id] = now

    watts = float(data["watts"])
    kwh = watts / 1000.0  # instantaneous kW reading
    energy_wh = data.get("energy_wh")  # cumulative if provided
    ts = data["timestamp"]

    reading = {
        "device_id": device_id,
        "station_id": device["station_id"],
        "district": device["district"],
        "device_type": device["device_type"],
        "watts": watts,
        "kwh": round(kwh, 4),
        "energy_wh": energy_wh,
        "voltage": data.get("voltage"),
        "frequency": data.get("frequency"),
        "temperature_c": data.get("temperature_c"),
        "timestamp": ts,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store reading
    with _readings_lock:
        _readings[device_id].appendleft(reading)

    # Update device stats
    with _devices_lock:
        dev = _devices.get(device_id)
        if dev:
            dev["last_report"] = ts
            dev["last_watts"] = watts
            dev["total_reports"] += 1
            dev["total_kwh"] += kwh

    # Update global stats
    with _stats_lock:
        _stats["total_reports"] += 1
        _stats["total_kwh"] += kwh

    # ── Publish to Pub/Sub ──────────────────────────────────
    # 1. Telemetry topic (for BigQuery archival)
    publish("telemetry", {
        "type": "INVERTER_READING",
        **reading,
    })

    # 2. District marketplace topic (so marketplace can use real generation)
    district = device["district"]
    topic_key = "d63" if district == "McHenry_D63" else "d91"
    publish(topic_key, {
        "type": "INVERTER_GENERATION",
        "station_id": device["station_id"],
        "district": district,
        "device_id": device_id,
        "device_type": device["device_type"],
        "watts": watts,
        "mwh": round(kwh / 1000, 6),  # kW -> MW for marketplace
        "timestamp": ts,
    })

    src = device["device_type"].upper()
    print(f"  [Telemetry] {src} {device['label']:24} | {watts:>8.1f}W | {kwh:>6.2f}kW | {district}")

    return jsonify({
        "status": "accepted",
        "device_id": device_id,
        "watts": watts,
        "kwh": round(kwh, 4),
        "next_report_after": RATE_LIMIT_SECONDS,
    }), 202


@app.route("/api/v1/inverter/devices", methods=["GET"])
def list_devices():
    """List all registered devices. Requires master key."""
    if not check_master_key():
        return jsonify({"error": "Master API key required"}), 401

    with _devices_lock:
        devices = []
        for dev_id, dev in _devices.items():
            devices.append({
                "device_id": dev["device_id"],
                "district": dev["district"],
                "device_type": dev["device_type"],
                "station_id": dev["station_id"],
                "label": dev["label"],
                "lat": dev["lat"],
                "lng": dev["lng"],
                "capacity_kw": dev["capacity_kw"],
                "registered_at": dev["registered_at"],
                "last_report": dev["last_report"],
                "last_watts": dev["last_watts"],
                "total_reports": dev["total_reports"],
                "total_kwh": round(dev["total_kwh"], 2),
                # Note: api_key intentionally excluded
            })

    return jsonify({
        "devices": devices,
        "count": len(devices),
    })


@app.route("/api/v1/inverter/readings/<device_id>", methods=["GET"])
def get_readings(device_id):
    """Get recent readings for a device. Requires master or matching device key."""
    role, auth_dev_id = check_any_key()
    if role is None:
        return jsonify({"error": "API key required"}), 401
    if role == "device" and auth_dev_id != device_id:
        return jsonify({"error": "Cannot view readings for another device"}), 403

    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, MAX_READINGS)

    with _readings_lock:
        readings = list(_readings.get(device_id, []))[:limit]

    return jsonify({
        "device_id": device_id,
        "readings": readings,
        "count": len(readings),
    })


# ── Setup: Create Pub/Sub topic ─────────────────────────────
def ensure_telemetry_topic():
    """Create the inverter-telemetry Pub/Sub topic if needed."""
    if not publisher:
        return
    try:
        publisher.create_topic(request={"name": topic_paths["telemetry"]})
        print(f"  [Setup] Created topic: {TELEMETRY_TOPIC}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
            print(f"  [Setup] Topic exists: {TELEMETRY_TOPIC}")
        else:
            print(f"  [Setup] Topic error: {e}")


# ── Banner + Start ──────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("  ╔═══════════════════════════════════════════════════════════════════════╗")
    print("  ║     TINY-HUB-NETWORK — Inverter Telemetry API                        ║")
    print("  ║     Physical Device Ingestion Gateway                                 ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")
    print("  ║  Endpoints:                                                           ║")
    print("  ║    POST /api/v1/inverter/register  — register device (master key)     ║")
    print("  ║    POST /api/v1/inverter/report    — submit telemetry (device key)    ║")
    print("  ║    GET  /api/v1/inverter/devices   — list devices (master key)        ║")
    print("  ║    GET  /api/v1/inverter/readings/  — device readings                 ║")
    print("  ║    GET  /api/v1/inverter/health    — service health (no auth)         ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  Port: {PORT}                                                          ║")
    print(f"  ║  Pub/Sub: {'connected' if publisher else 'unavailable':>12}                                       ║")
    print(f"  ║  Rate limit: {RATE_LIMIT_SECONDS}s per device                                        ║")
    print("  ╚═══════════════════════════════════════════════════════════════════════╝")
    print()

    # Print master key (first run only — in prod, use Secret Manager)
    print(f"  Master API Key: {MASTER_API_KEY}")
    print("  (Store this securely. Use in X-API-Key header for /register and /devices)")
    print()

    ensure_telemetry_topic()
    print()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
