"""
TINY-HUB-NETWORK — Inverter API Test Script
Registers a sample Enphase device, then sends telemetry readings.

Usage:
  python3 test_inverter_api.py [master_key]

If no master_key arg, reads from INVERTER_MASTER_KEY env var.
"""

import os
import sys
import json
import time
import random
import requests
from datetime import datetime, timezone

BASE_URL = "http://localhost:5001"
MASTER_KEY = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INVERTER_MASTER_KEY", "")

if not MASTER_KEY:
    print("Usage: python3 test_inverter_api.py <master_key>")
    print("  or set INVERTER_MASTER_KEY env var")
    sys.exit(1)

HEADERS_MASTER = {"X-API-Key": MASTER_KEY, "Content-Type": "application/json"}


def test_health():
    print("\n── Health Check ──────────────────────────")
    r = requests.get(f"{BASE_URL}/api/v1/inverter/health")
    print(f"  Status: {r.status_code}")
    print(f"  {json.dumps(r.json(), indent=2)}")
    return r.status_code == 200


def test_register():
    print("\n── Register Enphase Device ───────────────")
    payload = {
        "device_id": "enphase-woodstock-001",
        "district": "McHenry_D63",
        "device_type": "enphase",
        "station_id": "coin-base-1",  # maps to Walmart Woodstock seller
        "label": "Enphase IQ8+ Walmart Woodstock",
        "lat": 42.31,
        "lng": -88.44,
        "capacity_kw": 42.0,
    }
    r = requests.post(f"{BASE_URL}/api/v1/inverter/register",
                      headers=HEADERS_MASTER, json=payload)
    print(f"  Status: {r.status_code}")
    data = r.json()
    print(f"  {json.dumps(data, indent=2)}")

    if r.status_code == 201:
        return data["api_key"]
    elif r.status_code == 409:
        print("  (Already registered — skipping)")
        return None
    return None


def test_register_d91():
    print("\n── Register SolarEdge Device (D91) ──────")
    payload = {
        "device_id": "solaredge-caterpillar-001",
        "district": "IL_D91",
        "device_type": "solaredge",
        "station_id": "seller-peoria-001",
        "label": "SolarEdge SE33.3K Caterpillar HQ",
        "lat": 40.69,
        "lng": -89.59,
        "capacity_kw": 333.0,
    }
    r = requests.post(f"{BASE_URL}/api/v1/inverter/register",
                      headers=HEADERS_MASTER, json=payload)
    print(f"  Status: {r.status_code}")
    data = r.json()
    print(f"  {json.dumps(data, indent=2)}")

    if r.status_code == 201:
        return data["api_key"]
    return None


def test_report(device_key, device_id, watts_range=(5000, 35000)):
    print(f"\n── Submit Telemetry ({device_id}) ────────")
    headers = {"X-API-Key": device_key, "Content-Type": "application/json"}
    watts = random.uniform(*watts_range)
    payload = {
        "watts": round(watts, 1),
        "energy_wh": random.randint(100000, 9999999),
        "voltage": round(random.uniform(235, 245), 1),
        "frequency": round(random.uniform(59.95, 60.05), 2),
        "temperature_c": round(random.uniform(25, 55), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(f"{BASE_URL}/api/v1/inverter/report",
                      headers=headers, json=payload)
    print(f"  Status: {r.status_code}")
    print(f"  {json.dumps(r.json(), indent=2)}")
    return r.status_code == 202


def test_report_rate_limit(device_key, device_id):
    print(f"\n── Rate Limit Test ({device_id}) ─────────")
    headers = {"X-API-Key": device_key, "Content-Type": "application/json"}
    payload = {
        "watts": 10000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(f"{BASE_URL}/api/v1/inverter/report",
                      headers=headers, json=payload)
    print(f"  Status: {r.status_code} (expect 429)")
    print(f"  {json.dumps(r.json(), indent=2)}")
    return r.status_code == 429


def test_devices():
    print("\n── List Devices ─────────────────────────")
    r = requests.get(f"{BASE_URL}/api/v1/inverter/devices",
                     headers=HEADERS_MASTER)
    print(f"  Status: {r.status_code}")
    print(f"  {json.dumps(r.json(), indent=2)}")


def test_readings(device_id):
    print(f"\n── Readings ({device_id}) ────────────────")
    r = requests.get(f"{BASE_URL}/api/v1/inverter/readings/{device_id}",
                     headers=HEADERS_MASTER)
    print(f"  Status: {r.status_code}")
    print(f"  {json.dumps(r.json(), indent=2)}")


def test_bad_auth():
    print("\n── Bad Auth Test ────────────────────────")
    r = requests.post(f"{BASE_URL}/api/v1/inverter/report",
                      headers={"X-API-Key": "fake-key", "Content-Type": "application/json"},
                      json={"watts": 100, "timestamp": datetime.now(timezone.utc).isoformat()})
    print(f"  Status: {r.status_code} (expect 401)")


# ── Run Tests ───────────────────────────────────────────────
print("╔═════════════════════════════════════════════════════╗")
print("║  TINY-HUB Inverter API — Integration Test          ║")
print("╚═════════════════════════════════════════════════════╝")

test_health()

d63_key = test_register()
d91_key = test_register_d91()

if d63_key:
    test_report(d63_key, "enphase-woodstock-001", (5000, 35000))
    test_report_rate_limit(d63_key, "enphase-woodstock-001")

if d91_key:
    test_report(d91_key, "solaredge-caterpillar-001", (50000, 250000))

test_devices()
test_readings("enphase-woodstock-001")
test_bad_auth()

print("\n── Final Health ─────────────────────────")
test_health()

print("\n✅ All tests complete.")
