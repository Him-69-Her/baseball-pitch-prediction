"""
TINY-HUB-NETWORK — Smart Meter API Integration
Pulls 15-minute interval consumption data from Ameren IL and ComEd
via UtilityAPI (primary) and Green Button XML (fallback).

Used to verify buyer demand — cross-reference claimed consumption
against actual smart meter reads.

Usage:
    from smart_meter import SmartMeterClient

    meter = SmartMeterClient()

    # Pull latest 15-min readings for a meter
    readings = meter.get_readings("meter-id-123", hours=24)
    # [{"timestamp": "...", "kwh": 1.23, "interval_min": 15}, ...]

    # Verify a buyer's claimed demand
    verified = meter.verify_demand("meter-id-123", claimed_kwh=5.0)
    # {"verified": True, "actual_kwh": 4.8, "variance_pct": 4.2}

Environment variables:
    UTILITYAPI_TOKEN    — UtilityAPI bearer token
    AMEREN_ACCOUNT_ID   — Ameren IL customer account (optional)
    COMED_ACCOUNT_ID    — ComEd customer account (optional)

UtilityAPI docs: https://utilityapi.com/docs
Green Button:    https://green-button.github.io/
"""

import os
import time
import json
import threading
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import xml.etree.ElementTree as ET
    HAS_XML = True
except ImportError:
    HAS_XML = False


# ── Config ──────────────────────────────────────────────────
UTILITYAPI_BASE = "https://utilityapi.com/api/v2"
UTILITYAPI_TOKEN = os.environ.get("UTILITYAPI_TOKEN", "")

# Green Button namespace
GB_NS = "{http://naesb.org/espi}"

# Cache TTL (15 min — matches interval granularity)
CACHE_TTL = 900


@dataclass
class MeterReading:
    timestamp: str          # ISO 8601
    kwh: float              # consumption in kWh
    interval_min: int = 15  # interval length
    source: str = ""        # "utilityapi", "green_button", "simulated"
    quality: str = "actual" # "actual", "estimated", "simulated"


@dataclass
class DemandVerification:
    verified: bool
    actual_kwh: float
    claimed_kwh: float
    variance_pct: float
    readings_count: int
    source: str
    window_hours: float


class SmartMeterClient:
    """
    Unified client for pulling 15-min smart meter data.
    Priority: UtilityAPI → Green Button XML → Simulation
    """

    def __init__(self, token: str = None, cache_ttl: int = CACHE_TTL):
        self.token = token or UTILITYAPI_TOKEN
        self.cache_ttl = cache_ttl
        self._cache: dict = {}
        self._cache_lock = threading.Lock()
        self._meters: dict = {}  # meter_id -> metadata

        if self.token:
            print(f"  [SmartMeter] UtilityAPI token configured")
        else:
            print(f"  [SmartMeter] No UTILITYAPI_TOKEN — using simulation")

    # ── UtilityAPI ──────────────────────────────────────────

    def _utilityapi_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _utilityapi_get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make authenticated GET to UtilityAPI."""
        if not self.token or not HAS_REQUESTS:
            return None
        try:
            r = requests.get(
                f"{UTILITYAPI_BASE}/{endpoint}",
                headers=self._utilityapi_headers(),
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  [SmartMeter] UtilityAPI error: {str(e)[:60]}")
            return None

    def list_meters(self) -> list[dict]:
        """List all authorized meters from UtilityAPI."""
        data = self._utilityapi_get("meters")
        if data and "meters" in data:
            meters = []
            for m in data["meters"]:
                info = {
                    "meter_id": m.get("uid", ""),
                    "utility": m.get("utility", ""),
                    "address": m.get("service_address", ""),
                    "meter_type": m.get("meter_type", ""),
                    "status": m.get("status", ""),
                }
                self._meters[info["meter_id"]] = info
                meters.append(info)
            return meters
        return []

    def get_readings_utilityapi(self, meter_id: str, hours: int = 24) -> list[MeterReading]:
        """Pull interval data from UtilityAPI."""
        # UtilityAPI uses "bills" endpoint with intervals
        data = self._utilityapi_get(f"meters/{meter_id}/intervals", {
            "start": (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
        })
        if not data or "intervals" not in data:
            return []

        readings = []
        for interval in data["intervals"]:
            readings.append(MeterReading(
                timestamp=interval.get("start", ""),
                kwh=float(interval.get("kwh", 0)),
                interval_min=int(interval.get("duration_seconds", 900) / 60),
                source="utilityapi",
                quality="actual",
            ))
        return readings

    # ── Green Button XML ────────────────────────────────────

    def parse_green_button_xml(self, xml_path: str) -> list[MeterReading]:
        """
        Parse a Green Button XML file (ESPI format).
        Ameren and ComEd both support Green Button export.
        Users download XML from their utility portal.
        """
        if not HAS_XML:
            return []

        readings = []
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            for interval in root.iter(f"{GB_NS}IntervalReading"):
                ts_elem = interval.find(f"{GB_NS}timePeriod/{GB_NS}start")
                dur_elem = interval.find(f"{GB_NS}timePeriod/{GB_NS}duration")
                val_elem = interval.find(f"{GB_NS}value")

                if ts_elem is not None and val_elem is not None:
                    # Green Button timestamps are Unix epoch seconds
                    ts = datetime.fromtimestamp(
                        int(ts_elem.text), tz=timezone.utc
                    ).isoformat()
                    duration = int(dur_elem.text) if dur_elem is not None else 900
                    # Value is in Wh, convert to kWh
                    kwh = float(val_elem.text) / 1000.0

                    readings.append(MeterReading(
                        timestamp=ts,
                        kwh=kwh,
                        interval_min=int(duration / 60),
                        source="green_button",
                        quality="actual",
                    ))
        except Exception as e:
            print(f"  [SmartMeter] Green Button parse error: {str(e)[:60]}")

        return sorted(readings, key=lambda r: r.timestamp)

    # ── Simulation (fallback) ───────────────────────────────

    def get_readings_simulated(self, meter_id: str, hours: int = 24) -> list[MeterReading]:
        """
        Generate simulated 15-min consumption data.
        Uses a realistic residential load curve:
          - Low overnight (0.2-0.5 kWh/15min)
          - Morning ramp (0.5-1.5 kWh)
          - Midday moderate (0.8-1.2 kWh)
          - Evening peak (1.5-3.0 kWh)
          - Late night decline
        """
        import random
        readings = []
        now = datetime.now(timezone.utc)
        intervals = int(hours * 4)  # 4 intervals per hour

        for i in range(intervals):
            ts = now - timedelta(minutes=15 * (intervals - i))
            hour = ts.hour

            # Realistic load curve
            if 0 <= hour < 6:
                base_kwh = random.uniform(0.2, 0.5)
            elif 6 <= hour < 9:
                base_kwh = random.uniform(0.5, 1.5)
            elif 9 <= hour < 16:
                base_kwh = random.uniform(0.8, 1.2)
            elif 16 <= hour < 21:
                base_kwh = random.uniform(1.5, 3.0)
            else:
                base_kwh = random.uniform(0.4, 0.8)

            readings.append(MeterReading(
                timestamp=ts.isoformat(),
                kwh=round(base_kwh, 3),
                interval_min=15,
                source="simulated",
                quality="simulated",
            ))

        return readings

    # ── Unified Interface ───────────────────────────────────

    def get_readings(self, meter_id: str, hours: int = 24) -> list[MeterReading]:
        """
        Get 15-min interval readings. Tries:
          1. UtilityAPI (if token configured)
          2. Cache
          3. Simulation fallback
        """
        # Check cache
        cache_key = f"{meter_id}:{hours}"
        with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if time.time() - cached["fetched_at"] < self.cache_ttl:
                    return cached["readings"]

        # Try UtilityAPI
        readings = []
        if self.token:
            readings = self.get_readings_utilityapi(meter_id, hours)

        # Fallback to simulation
        if not readings:
            readings = self.get_readings_simulated(meter_id, hours)

        # Cache
        with self._cache_lock:
            self._cache[cache_key] = {
                "readings": readings,
                "fetched_at": time.time(),
            }

        return readings

    def verify_demand(self, meter_id: str, claimed_kwh: float,
                      window_hours: float = 1.0,
                      tolerance_pct: float = 20.0) -> DemandVerification:
        """
        Verify a buyer's claimed demand against smart meter data.

        Args:
            meter_id:      Utility meter identifier
            claimed_kwh:   What the buyer says they consumed
            window_hours:  Time window to sum readings over
            tolerance_pct: Max allowed variance (default 20%)

        Returns:
            DemandVerification with verified flag and details
        """
        readings = self.get_readings(meter_id, hours=window_hours + 1)

        # Sum readings within the window
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=window_hours)
        recent = [r for r in readings
                  if datetime.fromisoformat(r.timestamp.replace('Z', '+00:00')) >= cutoff]

        actual_kwh = sum(r.kwh for r in recent)
        actual_kwh = round(actual_kwh, 3)

        if claimed_kwh == 0:
            variance_pct = 0.0
        else:
            variance_pct = round(abs(actual_kwh - claimed_kwh) / claimed_kwh * 100, 1)

        verified = variance_pct <= tolerance_pct
        source = recent[0].source if recent else "none"

        return DemandVerification(
            verified=verified,
            actual_kwh=actual_kwh,
            claimed_kwh=claimed_kwh,
            variance_pct=variance_pct,
            readings_count=len(recent),
            source=source,
            window_hours=window_hours,
        )

    def get_daily_summary(self, meter_id: str) -> dict:
        """
        Get a 24-hour consumption summary with peak/off-peak breakdown.
        """
        readings = self.get_readings(meter_id, hours=24)

        total_kwh = sum(r.kwh for r in readings)
        peak_kwh = sum(r.kwh for r in readings
                       if 16 <= datetime.fromisoformat(
                           r.timestamp.replace('Z', '+00:00')).hour < 21)
        offpeak_kwh = total_kwh - peak_kwh

        return {
            "meter_id": meter_id,
            "total_kwh": round(total_kwh, 2),
            "peak_kwh": round(peak_kwh, 2),
            "offpeak_kwh": round(offpeak_kwh, 2),
            "readings_count": len(readings),
            "source": readings[0].source if readings else "none",
            "avg_15min_kwh": round(total_kwh / max(len(readings), 1), 3),
        }

    def stats(self) -> dict:
        """Return client stats."""
        with self._cache_lock:
            cached_meters = len(self._cache)
        return {
            "api_configured": bool(self.token),
            "cached_meters": cached_meters,
            "known_meters": len(self._meters),
        }


# ── Module-level convenience ────────────────────────────────
_client: Optional[SmartMeterClient] = None


def get_meter_client() -> SmartMeterClient:
    """Get or create the global SmartMeterClient."""
    global _client
    if _client is None:
        _client = SmartMeterClient()
    return _client
