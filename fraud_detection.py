"""
TINY-HUB-NETWORK — Physics-Based Fraud Detection
Cross-references inverter generation claims against:
  1. Roof size (area_sqft → max possible panel count)
  2. Live DNI from Open-Meteo (W/m² → max possible output)
  3. Time of day (no solar at night)
  4. Historical patterns (sudden spikes)

Flags impossible generation as FRAUD_FLAG in trade data.

Usage:
    from fraud_detection import FraudDetector

    detector = FraudDetector()
    result = detector.check_trade(trade_data, building_info)
    # {"flagged": True, "reason": "claimed 5.2 MWh but max possible is 1.8 MWh", ...}
"""

import math
import time
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

try:
    from weather_feed import get_weather
    HAS_WEATHER = True
except ImportError:
    HAS_WEATHER = False


# ── Physics Constants ───────────────────────────────────────
PANEL_SQFT = 17.5         # avg residential panel footprint
PANEL_KW = 0.4            # avg panel rated capacity (400W)
ROOF_USABLE_PCT = 0.65    # ~65% of roof is usable for panels
SYSTEM_EFFICIENCY = 0.85  # inverter + wiring losses
PEAK_SUN_DNI = 1000.0     # W/m² — clear sky noon benchmark
INTERVAL_HOURS = 5 / 60   # 5-minute trade interval


@dataclass
class FraudCheckResult:
    flagged: bool
    severity: str           # "clean", "warning", "critical"
    reason: str
    claimed_mwh: float
    max_possible_mwh: float
    roof_sqft: int
    dni_wm2: float
    checks_passed: list
    checks_failed: list


class FraudDetector:
    """
    Physics-based fraud detection for solar generation claims.
    """

    def __init__(self, tolerance: float = 1.3):
        """
        Args:
            tolerance: How much over theoretical max before flagging.
                       1.3 = 30% tolerance (accounts for measurement variance)
        """
        self.tolerance = tolerance
        self._history: dict = {}  # station_id → list of recent mwh values
        self._history_lock = threading.Lock()
        self.stats = {
            "checked": 0,
            "clean": 0,
            "warnings": 0,
            "critical": 0,
        }

    def _max_solar_output(self, area_sqft: int, dni_wm2: float) -> float:
        """
        Calculate maximum physically possible solar output for a building.

        Args:
            area_sqft: Roof area in square feet
            dni_wm2:   Current Direct Normal Irradiance in W/m²

        Returns:
            Max MWh for one 5-minute interval
        """
        usable_sqft = area_sqft * ROOF_USABLE_PCT
        max_panels = int(usable_sqft / PANEL_SQFT)
        rated_kw = max_panels * PANEL_KW

        # DNI ratio: actual irradiance vs peak
        dni_ratio = min(dni_wm2 / PEAK_SUN_DNI, 1.0) if dni_wm2 > 0 else 0.0

        # Max kWh for this interval
        max_kwh = rated_kw * dni_ratio * SYSTEM_EFFICIENCY * INTERVAL_HOURS

        return round(max_kwh / 1000, 6)  # convert to MWh

    def _check_nighttime(self, lat: float, lng: float) -> tuple[bool, float]:
        """Check if it's nighttime at the building's location."""
        now = datetime.now(timezone.utc)
        utc_hour = now.hour + now.minute / 60
        day_of_year = now.timetuple().tm_yday

        declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
        solar_noon_utc = 12 - lng / 15
        hour_angle = 15 * (utc_hour - solar_noon_utc)
        alt = math.asin(
            math.sin(math.radians(lat)) * math.sin(math.radians(declination)) +
            math.cos(math.radians(lat)) * math.cos(math.radians(declination)) *
            math.cos(math.radians(hour_angle))
        )
        alt_deg = math.degrees(alt)

        is_night = alt_deg <= 0
        return is_night, alt_deg

    def _check_spike(self, station_id: str, claimed_mwh: float) -> Optional[str]:
        """
        Check for sudden generation spikes (>3x rolling average).
        Returns warning string if spike detected, None if clean.
        """
        with self._history_lock:
            history = self._history.get(station_id, [])

            if len(history) < 5:
                # Not enough history yet
                history.append(claimed_mwh)
                self._history[station_id] = history[-50:]  # keep last 50
                return None

            avg = sum(history) / len(history)
            history.append(claimed_mwh)
            self._history[station_id] = history[-50:]

            if avg > 0 and claimed_mwh > avg * 3:
                return f"sudden spike: {claimed_mwh:.4f} MWh is {claimed_mwh/avg:.1f}x rolling avg ({avg:.4f})"

        return None

    def check_trade(self, trade: dict, building: dict = None) -> FraudCheckResult:
        """
        Run physics-based fraud checks on a trade.

        Args:
            trade:    Trade data dict (must have 'mwh', 'station_id')
            building: Building info dict (should have 'area_sqft', 'lat', 'lng')
                      If None, only spike detection runs.

        Returns:
            FraudCheckResult with flagged status and details
        """
        self.stats["checked"] += 1
        claimed_mwh = trade.get("mwh", 0)
        station_id = trade.get("station_id", "unknown")
        seller_type = trade.get("seller_type", "")

        checks_passed = []
        checks_failed = []
        max_possible = float('inf')
        dni = 0.0
        area = 0

        # Skip checks for battery, macro-grid, and bridge trades
        if seller_type in ("battery", "macro_grid", "ev_battery"):
            self.stats["clean"] += 1
            return FraudCheckResult(
                flagged=False, severity="clean",
                reason="battery/grid — physics checks not applicable",
                claimed_mwh=claimed_mwh, max_possible_mwh=0,
                roof_sqft=0, dni_wm2=0,
                checks_passed=["type_exempt"], checks_failed=[],
            )

        if trade.get("match_type") == "fallback":
            self.stats["clean"] += 1
            return FraudCheckResult(
                flagged=False, severity="clean",
                reason="fallback trade — no generation to verify",
                claimed_mwh=claimed_mwh, max_possible_mwh=0,
                roof_sqft=0, dni_wm2=0,
                checks_passed=["fallback_exempt"], checks_failed=[],
            )

        # ── Check 1: Nighttime generation ───────────────────
        if building and building.get("lat") and building.get("lng"):
            is_night, alt_deg = self._check_nighttime(
                building["lat"], building["lng"]
            )
            if is_night and claimed_mwh > 0.001:
                checks_failed.append(f"nighttime generation (sun alt: {alt_deg:.1f}°)")
            else:
                checks_passed.append("daytime_ok")

        # ── Check 2: Roof size vs claimed output ────────────
        if building and building.get("area_sqft"):
            area = building["area_sqft"]

            # Get live DNI
            if HAS_WEATHER and building.get("lat") and building.get("lng"):
                weather = get_weather(building["lat"], building["lng"])
                dni = weather.get("dni", 0.0)
            else:
                # Assume moderate irradiance for check
                dni = 500.0

            max_possible = self._max_solar_output(area, dni)

            if max_possible > 0 and claimed_mwh > max_possible * self.tolerance:
                checks_failed.append(
                    f"claimed {claimed_mwh:.4f} MWh but max possible is {max_possible:.4f} MWh "
                    f"(roof: {area:,} sqft, DNI: {dni:.0f} W/m²)"
                )
            else:
                checks_passed.append("physics_ok")

        # ── Check 3: Spike detection ────────────────────────
        spike = self._check_spike(station_id, claimed_mwh)
        if spike:
            checks_failed.append(spike)
        else:
            checks_passed.append("no_spike")

        # ── Result ──────────────────────────────────────────
        if not checks_failed:
            self.stats["clean"] += 1
            return FraudCheckResult(
                flagged=False, severity="clean", reason="all checks passed",
                claimed_mwh=claimed_mwh, max_possible_mwh=max_possible,
                roof_sqft=area, dni_wm2=dni,
                checks_passed=checks_passed, checks_failed=[],
            )

        # Determine severity
        has_nighttime = any("nighttime" in f for f in checks_failed)
        has_physics = any("max possible" in f for f in checks_failed)

        if has_nighttime or (has_physics and claimed_mwh > max_possible * 2):
            severity = "critical"
            self.stats["critical"] += 1
        else:
            severity = "warning"
            self.stats["warnings"] += 1

        return FraudCheckResult(
            flagged=True,
            severity=severity,
            reason="; ".join(checks_failed),
            claimed_mwh=claimed_mwh,
            max_possible_mwh=max_possible if max_possible != float('inf') else 0,
            roof_sqft=area,
            dni_wm2=dni,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

    def get_stats(self) -> dict:
        return dict(self.stats)


# ── Module-level convenience ────────────────────────────────
_detector: Optional[FraudDetector] = None


def get_detector() -> FraudDetector:
    global _detector
    if _detector is None:
        _detector = FraudDetector()
    return _detector
