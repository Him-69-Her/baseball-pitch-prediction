"""
TINY-HUB — Battery Dispatch Optimizer (#23)
=============================================
Replaces simple threshold-based battery charge/discharge with a
lookahead optimizer that uses price history and time-of-day patterns
to schedule optimal dispatch windows.

Strategy:
  1. Track 24h rolling price history → build hourly price profile
  2. Identify daily charge window (cheapest 4-hour block)
  3. Identify daily discharge window (most expensive 4-hour block)
  4. Adjust thresholds dynamically based on learned patterns
  5. Override when real-time price deviates significantly from forecast

The optimizer wraps BatteryVPP and overrides _update_mode().

Usage:
    from dispatch_optimizer import OptimizedBattery, get_optimized_battery

    batt = get_optimized_battery("batt-marengo", "Marengo 20MW", 20.0)
    output = batt.get_output(grid_price_kwh=0.045)
"""

import time
import math
import threading
from collections import deque, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone


# ── Constants ───────────────────────────────────────────────
LCOS_PER_MWH     = 0.015   # $/kWh degradation cost
MIN_SOC          = 0.10
MAX_SOC          = 0.95
CHARGE_RATE      = 0.25    # 25% capacity per tick (more aggressive)
DISCHARGE_RATE   = 0.35    # 35% capacity per tick
HISTORY_HOURS    = 72      # 3 days of price history
LOOKAHEAD_HOURS  = 24      # Optimize over next 24 hours


@dataclass
class DispatchState:
    """Optimizer state for logging."""
    mode: str = "IDLE"
    soc_pct: float = 50.0
    charge_price: float = 0.0
    optimal_charge_hour: int = 3     # Best hour to charge (0-23 UTC)
    optimal_discharge_hour: int = 22  # Best hour to discharge (0-23 UTC)
    hourly_avg_prices: dict = None
    threshold_charge: float = 0.020
    threshold_discharge: float = 0.050
    profit_per_cycle: float = 0.0
    cycles: int = 0
    total_profit: float = 0.0


class OptimizedBattery:
    """
    Battery with lookahead dispatch optimization.

    Learns the daily price curve from historical observations
    and schedules charge/discharge to maximize arbitrage profit.
    """

    def __init__(self, station_id: str, label: str, capacity_mwh: float,
                 toll: float = 0.025):
        self.station_id = station_id
        self.label = label
        self.capacity_mwh = capacity_mwh
        self.toll = toll

        # Battery state
        self.soc = 0.50
        self.charge_price = 0.0
        self.mode = "IDLE"
        self.cycles = 0
        self.total_profit = 0.0

        # Price learning
        self._price_history = deque(maxlen=HISTORY_HOURS * 12)  # 5-min intervals
        self._hourly_prices = defaultdict(list)  # hour -> [prices]
        self._hourly_avg = {}  # hour -> avg price (learned)

        # Optimal windows (updated periodically)
        self._optimal_charge_hours = {2, 3, 4, 5}        # Default: 2-5 AM UTC
        self._optimal_discharge_hours = {21, 22, 23, 0}   # Default: 9PM-12AM UTC (evening peak)

        # Dynamic thresholds (learned from data)
        self._charge_threshold = 0.020     # $/kWh
        self._discharge_threshold = 0.050  # $/kWh

        self._lock = threading.Lock()
        self._last_optimization = 0

    def observe_price(self, grid_price_kwh: float):
        """Feed price observation for learning."""
        if grid_price_kwh <= 0:
            return

        now = datetime.now(timezone.utc)
        hour = now.hour

        with self._lock:
            self._price_history.append((now.timestamp(), grid_price_kwh))
            self._hourly_prices[hour].append(grid_price_kwh)

            # Keep only last 72h per hour bucket
            max_per_hour = HISTORY_HOURS * 12 // 24
            if len(self._hourly_prices[hour]) > max_per_hour:
                self._hourly_prices[hour] = self._hourly_prices[hour][-max_per_hour:]

            # Re-optimize every 30 minutes
            if time.time() - self._last_optimization > 1800:
                self._optimize_windows()
                self._last_optimization = time.time()

    def get_output(self, grid_price_kwh: float) -> float:
        """
        Decide charge/discharge/idle and return MWh to sell.
        Also feeds the price observation for learning.
        """
        self.observe_price(grid_price_kwh)
        self._update_mode(grid_price_kwh)

        if self.mode == "CHARGING":
            self._do_charge(grid_price_kwh)
            return 0.0
        elif self.mode == "DISCHARGING":
            return self._do_discharge(grid_price_kwh)
        return 0.0

    def status(self) -> dict:
        """Return current state for dashboard."""
        with self._lock:
            return {
                "station_id": self.station_id,
                "label": self.label,
                "mode": self.mode,
                "soc_pct": round(self.soc * 100, 1),
                "stored_mwh": round(self.soc * self.capacity_mwh, 2),
                "charge_price": round(self.charge_price, 4),
                "cycles": self.cycles,
                "total_profit": round(self.total_profit, 2),
                "charge_threshold": round(self._charge_threshold, 4),
                "discharge_threshold": round(self._discharge_threshold, 4),
                "optimal_charge_hours": sorted(self._optimal_charge_hours),
                "optimal_discharge_hours": sorted(self._optimal_discharge_hours),
                "hourly_avg_prices": dict(self._hourly_avg),
            }

    def _optimize_windows(self):
        """Learn optimal charge/discharge windows from price history."""
        # Calculate hourly averages
        for hour in range(24):
            prices = self._hourly_prices.get(hour, [])
            if prices:
                self._hourly_avg[hour] = sum(prices) / len(prices)

        if len(self._hourly_avg) < 12:
            return  # Not enough data yet

        # Find cheapest 4-hour window (charge)
        sorted_hours = sorted(self._hourly_avg.items(), key=lambda x: x[1])
        self._optimal_charge_hours = {h for h, _ in sorted_hours[:4]}
        self._charge_threshold = sorted_hours[3][1] * 1.1 if sorted_hours else 0.020

        # Find most expensive 4-hour window (discharge)
        self._optimal_discharge_hours = {h for h, _ in sorted_hours[-4:]}
        self._discharge_threshold = sorted_hours[-4][1] * 0.9 if sorted_hours else 0.050

        # Ensure discharge threshold > charge threshold + toll + LCOS
        min_discharge = self._charge_threshold + self.toll + LCOS_PER_MWH
        self._discharge_threshold = max(self._discharge_threshold, min_discharge)

    def _update_mode(self, grid_price_kwh: float):
        """Smart dispatch: use learned windows + real-time price."""
        now = datetime.now(timezone.utc)
        hour = now.hour

        in_charge_window = hour in self._optimal_charge_hours
        in_discharge_window = hour in self._optimal_discharge_hours

        # ── Priority 1: Real-time price override ────────────
        # If price is extremely low, charge regardless of window
        if grid_price_kwh < self._charge_threshold * 0.5 and self.soc < MAX_SOC:
            self.mode = "CHARGING"
            return

        # If price is extremely high, discharge regardless of window
        min_sell = self.charge_price + self.toll + LCOS_PER_MWH
        if grid_price_kwh > self._discharge_threshold * 2 and self.soc > MIN_SOC:
            if grid_price_kwh > min_sell:
                self.mode = "DISCHARGING"
                return

        # ── Priority 2: Scheduled window ────────────────────
        if in_charge_window and grid_price_kwh <= self._charge_threshold:
            if self.soc < MAX_SOC:
                self.mode = "CHARGING"
                return

        if in_discharge_window and self.soc > MIN_SOC:
            if grid_price_kwh > min_sell:
                self.mode = "DISCHARGING"
                return

        # ── Priority 3: Opportunistic ───────────────────────
        # Even outside windows, charge if very cheap
        if grid_price_kwh <= self._charge_threshold and self.soc < 0.80:
            self.mode = "CHARGING"
            return

        # Even outside windows, discharge if profitable and SOC is high
        if self.soc > 0.80 and grid_price_kwh > min_sell * 1.2:
            self.mode = "DISCHARGING"
            return

        self.mode = "IDLE"

    def _do_charge(self, grid_price_kwh: float):
        """Charge the battery."""
        charge_mwh = self.capacity_mwh * CHARGE_RATE
        max_fillable = (MAX_SOC - self.soc) * self.capacity_mwh
        actual = min(charge_mwh, max_fillable)

        if actual <= 0:
            self.mode = "IDLE"
            return

        stored = self.soc * self.capacity_mwh
        new_stored = stored + actual
        if new_stored > 0:
            self.charge_price = (stored * self.charge_price + actual * grid_price_kwh) / new_stored

        self.soc = min(MAX_SOC, self.soc + actual / self.capacity_mwh)

    def _do_discharge(self, grid_price_kwh: float) -> float:
        """Discharge and return MWh. Track profit."""
        discharge_mwh = self.capacity_mwh * DISCHARGE_RATE
        max_discharge = (self.soc - MIN_SOC) * self.capacity_mwh
        actual = min(discharge_mwh, max_discharge)

        if actual <= 0:
            self.mode = "IDLE"
            return 0.0

        # Calculate profit for this discharge
        revenue_per_kwh = grid_price_kwh - self.toll
        cost_per_kwh = self.charge_price + LCOS_PER_MWH
        profit_per_kwh = revenue_per_kwh - cost_per_kwh
        self.total_profit += profit_per_kwh * actual * 1000  # Convert MWh to kWh

        prev_soc = self.soc
        self.soc = max(MIN_SOC, self.soc - actual / self.capacity_mwh)

        if prev_soc > 0.50 and self.soc <= 0.50:
            self.cycles += 1

        return round(actual, 3)


# ── Registry ────────────────────────────────────────────────
_opt_registry = {}

def get_optimized_battery(station_id: str, label: str, capacity_mwh: float,
                          toll: float = 0.025) -> OptimizedBattery:
    """Get or create an optimized battery."""
    if station_id not in _opt_registry:
        _opt_registry[station_id] = OptimizedBattery(station_id, label, capacity_mwh, toll)
    return _opt_registry[station_id]

def all_optimized_battery_status() -> list:
    """Return status of all optimized batteries."""
    return [b.status() for b in _opt_registry.values()]
