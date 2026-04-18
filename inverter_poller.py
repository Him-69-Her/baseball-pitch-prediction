"""
TINY-HUB-NETWORK — IoT Inverter Poller
Pulls real production data from Enphase Enlighten + SolarEdge monitoring APIs.
Feeds readings into the inverter telemetry pipeline via Pub/Sub.

Supports:
  - Enphase Enlighten API v4 (OAuth2)
  - SolarEdge Monitoring API v1 (API key)
  - Tesla Powerwall (local gateway API)

Polling interval: 5 min (matches market tick cadence)

Env vars:
  ENPHASE_CLIENT_ID     — Enlighten OAuth2 client ID
  ENPHASE_CLIENT_SECRET — Enlighten OAuth2 client secret
  ENPHASE_API_KEY       — Enlighten API key
  SOLAREDGE_API_KEY     — SolarEdge site-level API key
  TESLA_GATEWAY_IP      — Local Powerwall gateway IP (optional)
  TESLA_GATEWAY_PASS    — Gateway customer password (optional)

Run:
  python3 -u inverter_poller.py
"""

import os
import json
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Optional: Pub/Sub ───────────────────────────────────────
try:
    from google.cloud import pubsub_v1
    PUBSUB_AVAILABLE = True
except ImportError:
    PUBSUB_AVAILABLE = False

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
TELEMETRY_TOPIC = "inverter-telemetry"
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"

POLL_INTERVAL = 300  # 5 min — matches Cloud Scheduler ticks

# ── API Credentials ─────────────────────────────────────────
ENPHASE_CLIENT_ID = os.environ.get("ENPHASE_CLIENT_ID", "")
ENPHASE_CLIENT_SECRET = os.environ.get("ENPHASE_CLIENT_SECRET", "")
ENPHASE_API_KEY = os.environ.get("ENPHASE_API_KEY", "")
ENPHASE_ACCESS_TOKEN = os.environ.get("ENPHASE_ACCESS_TOKEN", "")

SOLAREDGE_API_KEY = os.environ.get("SOLAREDGE_API_KEY", "")

TESLA_GATEWAY_IP = os.environ.get("TESLA_GATEWAY_IP", "")
TESLA_GATEWAY_PASS = os.environ.get("TESLA_GATEWAY_PASS", "")

# ── Registered Systems ──────────────────────────────────────
# Each system maps a cloud platform site to a TinyHub station_id
# In production, load from database or config file
SYSTEMS_FILE = "inverter_systems.json"

DEFAULT_SYSTEMS = {
    "enphase": [
        # {
        #     "system_id": "2567890",         # Enphase system ID
        #     "station_id": "coin-base-1",     # TinyHub marketplace seller
        #     "district": "McHenry_D63",
        #     "label": "Walmart Woodstock Enphase",
        #     "lat": 42.31, "lng": -88.44,
        # },
    ],
    "solaredge": [
        # {
        #     "site_id": "1234567",            # SolarEdge site ID
        #     "station_id": "seller-peoria-001",
        #     "district": "IL_D91",
        #     "label": "Caterpillar HQ SolarEdge",
        #     "lat": 40.69, "lng": -89.59,
        # },
    ],
    "tesla_powerwall": [
        # {
        #     "gateway_ip": "192.168.1.50",
        #     "station_id": "batt-marengo",
        #     "district": "McHenry_D63",
        #     "label": "Marengo Battery Powerwall",
        #     "lat": 42.24, "lng": -88.60,
        # },
    ],
}

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
        print(f"  [Poller] Pub/Sub init error: {e}")
        publisher = None


def publish(topic_key, data):
    """Publish JSON to Pub/Sub. Fire-and-forget."""
    if not publisher or topic_key not in topic_paths:
        return
    try:
        msg = json.dumps(data).encode("utf-8")
        publisher.publish(topic_paths[topic_key], msg)
    except Exception as e:
        print(f"  [Pub/Sub] Publish error ({topic_key}): {e}")


def publish_reading(system, watts, energy_wh=None, voltage=None,
                    frequency=None, temperature_c=None, extra=None):
    """Publish a normalized reading from any platform."""
    now = datetime.now(timezone.utc).isoformat()
    reading = {
        "type": "INVERTER_READING",
        "source": "poller",
        "device_type": system.get("platform", "unknown"),
        "station_id": system["station_id"],
        "district": system["district"],
        "device_id": f"poller-{system['platform']}-{system.get('system_id', system.get('site_id', 'unknown'))}",
        "label": system.get("label", ""),
        "watts": watts,
        "kwh": round(watts / 1000, 4),
        "mwh": round(watts / 1_000_000, 6),
        "energy_wh": energy_wh,
        "voltage": voltage,
        "frequency": frequency,
        "temperature_c": temperature_c,
        "timestamp": now,
    }
    if extra:
        reading.update(extra)

    # Telemetry archive
    publish("telemetry", reading)

    # District marketplace
    topic_key = "d63" if system["district"] == "McHenry_D63" else "d91"
    publish(topic_key, {
        "type": "INVERTER_GENERATION",
        "station_id": system["station_id"],
        "district": system["district"],
        "device_id": reading["device_id"],
        "device_type": system["platform"],
        "watts": watts,
        "mwh": reading["mwh"],
        "timestamp": now,
    })

    src = system["platform"].upper()
    print(f"  [{src}] {system['label']:30} | {watts:>10.1f}W | {reading['kwh']:>8.2f}kW | {system['district']}")


# ══════════════════════════════════════════════════════════════
# ENPHASE ENLIGHTEN API v4
# Docs: https://developer-v4.enphase.com/docs
# ══════════════════════════════════════════════════════════════

class EnphaseClient:
    """Enphase Enlighten API v4 client."""

    BASE_URL = "https://api.enphaseenergy.com/api/v4"

    def __init__(self, client_id, client_secret, api_key, access_token=""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_key = api_key
        self.access_token = access_token
        self.enabled = bool(client_id and api_key)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "key": self.api_key,
            "Content-Type": "application/json",
        }

    def get_system_summary(self, system_id):
        """Get current system summary including production."""
        if not self.enabled:
            return None
        try:
            url = f"{self.BASE_URL}/systems/{system_id}/summary"
            r = requests.get(url, headers=self._headers(), timeout=30)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                print(f"  [Enphase] Auth expired for system {system_id} — need token refresh")
                return None
            else:
                print(f"  [Enphase] Error {r.status_code} for system {system_id}: {r.text[:100]}")
                return None
        except Exception as e:
            print(f"  [Enphase] Request failed for {system_id}: {e}")
            return None

    def get_production_stats(self, system_id):
        """Get recent microinverter-level production."""
        if not self.enabled:
            return None
        try:
            url = f"{self.BASE_URL}/systems/{system_id}/telemetry/production_micro"
            r = requests.get(url, headers=self._headers(), timeout=30)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            print(f"  [Enphase] Telemetry error for {system_id}: {e}")
            return None

    def poll_system(self, system_config):
        """Poll one Enphase system and publish reading."""
        system_id = system_config["system_id"]
        summary = self.get_system_summary(system_id)
        if not summary:
            return False

        # current_power is in Watts
        watts = summary.get("current_power", 0)
        energy_today = summary.get("energy_today", 0)  # Wh

        publish_reading(system_config,
                        watts=watts,
                        energy_wh=energy_today,
                        extra={
                            "modules_count": summary.get("modules", 0),
                            "status": summary.get("status", "unknown"),
                            "energy_lifetime_wh": summary.get("energy_lifetime", 0),
                        })
        return True


# ══════════════════════════════════════════════════════════════
# SOLAREDGE MONITORING API v1
# Docs: https://monitoring.solaredge.com/solaredge-web/p/kits
# ══════════════════════════════════════════════════════════════

class SolarEdgeClient:
    """SolarEdge Monitoring API client."""

    BASE_URL = "https://monitoringapi.solaredge.com"

    def __init__(self, api_key):
        self.api_key = api_key
        self.enabled = bool(api_key)

    def get_site_overview(self, site_id):
        """Get site overview with current power."""
        if not self.enabled:
            return None
        try:
            url = f"{self.BASE_URL}/site/{site_id}/overview"
            r = requests.get(url, params={"api_key": self.api_key}, timeout=30)
            if r.status_code == 200:
                return r.json().get("overview", {})
            else:
                print(f"  [SolarEdge] Error {r.status_code} for site {site_id}: {r.text[:100]}")
                return None
        except Exception as e:
            print(f"  [SolarEdge] Request failed for {site_id}: {e}")
            return None

    def get_power_details(self, site_id, start_time=None, end_time=None):
        """Get 15-min granularity power data."""
        if not self.enabled:
            return None
        if not end_time:
            end_time = datetime.now(timezone.utc)
        if not start_time:
            start_time = end_time - timedelta(hours=1)

        try:
            url = f"{self.BASE_URL}/site/{site_id}/powerDetails"
            params = {
                "api_key": self.api_key,
                "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json().get("powerDetails", {})
            return None
        except Exception as e:
            print(f"  [SolarEdge] Power details error for {site_id}: {e}")
            return None

    def get_inverter_data(self, site_id):
        """Get per-inverter technical data."""
        if not self.enabled:
            return None
        try:
            now = datetime.now(timezone.utc)
            start = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            end = now.strftime("%Y-%m-%d %H:%M:%S")
            url = f"{self.BASE_URL}/site/{site_id}/inventory"
            r = requests.get(url, params={"api_key": self.api_key}, timeout=30)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            print(f"  [SolarEdge] Inverter data error for {site_id}: {e}")
            return None

    def poll_site(self, system_config):
        """Poll one SolarEdge site and publish reading."""
        site_id = system_config["site_id"]
        overview = self.get_site_overview(site_id)
        if not overview:
            return False

        current = overview.get("currentPower", {})
        watts = current.get("power", 0)  # Watts

        energy_today = overview.get("lastDayData", {}).get("energy", 0)  # Wh
        energy_lifetime = overview.get("lifeTimeData", {}).get("energy", 0)  # Wh

        publish_reading(system_config,
                        watts=watts,
                        energy_wh=energy_today,
                        extra={
                            "energy_lifetime_wh": energy_lifetime,
                            "last_update": overview.get("lastUpdateTime", ""),
                        })
        return True


# ══════════════════════════════════════════════════════════════
# TESLA POWERWALL (LOCAL GATEWAY)
# Docs: https://github.com/vloschiavo/powerwall2 (community)
# ══════════════════════════════════════════════════════════════

class TeslaPowerwallClient:
    """Tesla Powerwall local gateway API client."""

    def __init__(self, gateway_ip="", password=""):
        self.gateway_ip = gateway_ip
        self.password = password
        self.token = None
        self.enabled = bool(gateway_ip)

    def _base_url(self, ip=None):
        return f"https://{ip or self.gateway_ip}"

    def authenticate(self, ip=None):
        """Get auth token from local gateway."""
        if not self.enabled and not ip:
            return False
        try:
            url = f"{self._base_url(ip)}/api/login/Basic"
            r = requests.post(url, json={
                "username": "customer",
                "password": self.password,
            }, verify=False, timeout=10)
            if r.status_code == 200:
                self.token = r.json().get("token")
                return True
        except Exception as e:
            print(f"  [Tesla] Auth failed: {e}")
        return False

    def get_meters(self, ip=None):
        """Get power meter aggregates."""
        target_ip = ip or self.gateway_ip
        if not target_ip:
            return None
        try:
            url = f"{self._base_url(target_ip)}/api/meters/aggregates"
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401 or r.status_code == 403:
                if self.authenticate(target_ip):
                    return self.get_meters(target_ip)
            return None
        except Exception as e:
            print(f"  [Tesla] Meter read failed: {e}")
            return None

    def get_soe(self, ip=None):
        """Get State of Energy (battery %)."""
        target_ip = ip or self.gateway_ip
        if not target_ip:
            return None
        try:
            url = f"{self._base_url(target_ip)}/api/system_status/soe"
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            r = requests.get(url, headers=headers, verify=False, timeout=10)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            return None

    def poll_gateway(self, system_config):
        """Poll one Powerwall gateway and publish reading."""
        ip = system_config.get("gateway_ip", self.gateway_ip)
        if not ip:
            return False

        meters = self.get_meters(ip)
        if not meters:
            return False

        # Solar production
        solar = meters.get("solar", {})
        solar_watts = solar.get("instant_power", 0)

        # Battery state
        battery = meters.get("battery", {})
        battery_watts = battery.get("instant_power", 0)  # + = charging, - = discharging

        # Grid interaction
        site = meters.get("site", {})
        grid_watts = site.get("instant_power", 0)

        # State of energy
        soe_data = self.get_soe(ip)
        soe_pct = soe_data.get("percentage", 0) if soe_data else None

        publish_reading(system_config,
                        watts=max(0, solar_watts),
                        voltage=solar.get("instant_average_voltage"),
                        frequency=solar.get("frequency"),
                        extra={
                            "battery_watts": battery_watts,
                            "battery_soe_pct": soe_pct,
                            "grid_watts": grid_watts,
                            "is_battery": True,
                        })
        return True


# ══════════════════════════════════════════════════════════════
# SYSTEM MANAGEMENT
# ══════════════════════════════════════════════════════════════

def load_systems():
    """Load registered systems from config file."""
    if os.path.exists(SYSTEMS_FILE):
        try:
            with open(SYSTEMS_FILE) as f:
                systems = json.load(f)
            # Tag each system with its platform
            for platform, entries in systems.items():
                for entry in entries:
                    entry["platform"] = platform
            return systems
        except Exception as e:
            print(f"  [Config] Error loading {SYSTEMS_FILE}: {e}")
    return DEFAULT_SYSTEMS


def save_systems(systems):
    """Persist systems config."""
    # Strip runtime fields before saving
    clean = {}
    for platform, entries in systems.items():
        clean[platform] = []
        for entry in entries:
            e = {k: v for k, v in entry.items() if k != "platform"}
            clean[platform].append(e)
    with open(SYSTEMS_FILE, "w") as f:
        json.dump(clean, f, indent=2)


# ══════════════════════════════════════════════════════════════
# POLLING LOOP
# ══════════════════════════════════════════════════════════════

def poll_all(enphase, solaredge, tesla, systems):
    """Run one poll cycle across all registered systems."""
    success = 0
    failed = 0
    skipped = 0

    # Enphase systems
    for sys in systems.get("enphase", []):
        sys["platform"] = "enphase"
        if enphase.enabled:
            if enphase.poll_system(sys):
                success += 1
            else:
                failed += 1
        else:
            skipped += 1

    # SolarEdge systems
    for sys in systems.get("solaredge", []):
        sys["platform"] = "solaredge"
        if solaredge.enabled:
            if solaredge.poll_site(sys):
                success += 1
            else:
                failed += 1
        else:
            skipped += 1

    # Tesla Powerwall systems
    for sys in systems.get("tesla_powerwall", []):
        sys["platform"] = "tesla_powerwall"
        if tesla.enabled or sys.get("gateway_ip"):
            if tesla.poll_gateway(sys):
                success += 1
            else:
                failed += 1
        else:
            skipped += 1

    return success, failed, skipped


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  ╔═══════════════════════════════════════════════════════════════════════╗")
    print("  ║     TINY-HUB-NETWORK — IoT Inverter Poller                           ║")
    print("  ║     Enphase Enlighten + SolarEdge + Tesla Powerwall                   ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")

    # Init clients
    enphase = EnphaseClient(ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET,
                            ENPHASE_API_KEY, ENPHASE_ACCESS_TOKEN)
    solaredge = SolarEdgeClient(SOLAREDGE_API_KEY)
    tesla = TeslaPowerwallClient(TESLA_GATEWAY_IP, TESLA_GATEWAY_PASS)

    print(f"  ║  Enphase:    {'enabled' if enphase.enabled else 'no credentials — set ENPHASE_* env vars':>50}  ║")
    print(f"  ║  SolarEdge:  {'enabled' if solaredge.enabled else 'no credentials — set SOLAREDGE_API_KEY':>50}  ║")
    print(f"  ║  Tesla PW:   {'enabled' if tesla.enabled else 'no gateway — set TESLA_GATEWAY_IP':>50}  ║")
    print(f"  ║  Pub/Sub:    {'connected' if publisher else 'unavailable':>50}  ║")
    print(f"  ║  Interval:   {POLL_INTERVAL}s{' ':>47}  ║")

    # Load systems
    systems = load_systems()
    total_systems = sum(len(v) for v in systems.values())

    print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  Registered systems: {total_systems:>3}                                              ║")
    for platform, entries in systems.items():
        if entries:
            print(f"  ║    {platform:>16}: {len(entries)} system(s)                                       ║")
    print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
    print()

    if total_systems == 0:
        print("  No systems registered. To add systems:")
        print(f"    1. Edit {SYSTEMS_FILE} (or create it)")
        print("    2. Add entries under 'enphase', 'solaredge', or 'tesla_powerwall'")
        print("    3. Set the corresponding API key env vars")
        print()
        print("  Example inverter_systems.json:")
        print('  {')
        print('    "enphase": [{')
        print('      "system_id": "2567890",')
        print('      "station_id": "coin-base-1",')
        print('      "district": "McHenry_D63",')
        print('      "label": "Walmart Woodstock Enphase",')
        print('      "lat": 42.31, "lng": -88.44')
        print('    }],')
        print('    "solaredge": [{')
        print('      "system_id": "1234567",')
        print('      "station_id": "seller-peoria-001",')
        print('      "district": "IL_D91",')
        print('      "label": "Caterpillar HQ SolarEdge",')
        print('      "lat": 40.69, "lng": -89.59')
        print('    }]')
        print('  }')
        print()
        print("  Poller will start and wait for systems to be configured.")
        print()

    # Save default config if it doesn't exist
    if not os.path.exists(SYSTEMS_FILE):
        save_systems(systems)
        print(f"  Created {SYSTEMS_FILE} — edit it to add your systems.")
        print()

    # ── Poll Loop ───────────────────────────────────────────
    cycle = 0
    while True:
        cycle += 1
        systems = load_systems()  # Reload each cycle (hot-reload support)
        total = sum(len(v) for v in systems.values())

        if total > 0:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"  ── Poll cycle #{cycle} @ {ts} ({total} systems) ──")
            ok, fail, skip = poll_all(enphase, solaredge, tesla, systems)
            print(f"     Results: {ok} ok / {fail} failed / {skip} skipped (no credentials)")
            print()

        try:
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print()
            print(f"  Poller stopped after {cycle} cycles.")
            break
