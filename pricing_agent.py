"""
TINY-HUB — Dynamic Pricing Agent (#22)
=======================================
Adaptive clearing price optimizer that maximizes buyer savings
while protecting seller margins, based on real-time grid conditions.

Strategy:
  - Track grid LMP with exponential moving average (EMA)
  - Compute price bands (percentile-based from rolling window)
  - When LMP is HIGH (above P75): widen P2P spread → more buyer savings
  - When LMP is LOW (below P25): tighten spread → protect seller margin
  - When LMP is VOLATILE: use wider bands → cautious pricing
  - When LMP is STABLE: use tighter bands → aggressive savings

The agent outputs a `price_cap_factor` (0.70 - 0.95) applied to supply_rate.
  clearing_price = min(midpoint, supply_rate * price_cap_factor)

This replaces the fixed 0.95 cap from Task #6.

Usage:
    from pricing_agent import PricingAgent

    agent = PricingAgent(supply_rate=0.070)

    # Each tick:
    agent.observe(grid_price_kwh=0.045)
    cap_factor = agent.get_price_cap_factor()
    clearing = min(midpoint, supply_rate * cap_factor)
"""

import time
import math
import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass
class PriceState:
    """Snapshot of pricing agent state for logging/dashboard."""
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    volatility: float = 0.0
    percentile_25: float = 0.0
    percentile_75: float = 0.0
    cap_factor: float = 0.90
    regime: str = "NORMAL"       # LOW | NORMAL | HIGH | SPIKE | VOLATILE
    observations: int = 0


class PricingAgent:
    """
    Adaptive clearing price agent using EMA + percentile bands.

    Not ML — deliberately simple and interpretable so regulators
    can audit the pricing logic. Can upgrade to RL later.
    """

    def __init__(self, supply_rate: float = 0.070,
                 ema_fast_alpha: float = 0.15,
                 ema_slow_alpha: float = 0.03,
                 window_size: int = 288,       # 288 five-min intervals = 24 hours
                 min_cap: float = 0.70,        # Never price below 70% of supply
                 max_cap: float = 0.95,        # Never price above 95% of supply
                 volatility_threshold: float = 0.15):
        """
        Args:
            supply_rate:    Utility supply-only rate ($/kWh)
            ema_fast_alpha: Fast EMA decay (tracks recent prices)
            ema_slow_alpha: Slow EMA decay (tracks trend)
            window_size:    Rolling window for percentile calc
            min_cap:        Floor for price_cap_factor
            max_cap:        Ceiling for price_cap_factor
            volatility_threshold: CV above this = volatile regime
        """
        self.supply_rate = supply_rate
        self.ema_fast_alpha = ema_fast_alpha
        self.ema_slow_alpha = ema_slow_alpha
        self.window_size = window_size
        self.min_cap = min_cap
        self.max_cap = max_cap
        self.volatility_threshold = volatility_threshold

        # State
        self._prices = deque(maxlen=window_size)
        self._ema_fast = None
        self._ema_slow = None
        self._cap_factor = 0.90   # Start moderate
        self._regime = "NORMAL"
        self._observations = 0
        self._lock = threading.Lock()

    def observe(self, grid_price_kwh: float):
        """Feed a new grid price observation to the agent."""
        if grid_price_kwh <= 0:
            return

        with self._lock:
            self._prices.append(grid_price_kwh)
            self._observations += 1

            # Update EMAs
            if self._ema_fast is None:
                self._ema_fast = grid_price_kwh
                self._ema_slow = grid_price_kwh
            else:
                self._ema_fast = (self.ema_fast_alpha * grid_price_kwh +
                                  (1 - self.ema_fast_alpha) * self._ema_fast)
                self._ema_slow = (self.ema_slow_alpha * grid_price_kwh +
                                  (1 - self.ema_slow_alpha) * self._ema_slow)

            # Recalculate cap factor
            self._update_cap_factor()

    def get_price_cap_factor(self) -> float:
        """Return the current price cap factor (0.70 - 0.95)."""
        with self._lock:
            return self._cap_factor

    def get_state(self) -> PriceState:
        """Return current agent state for logging/dashboard."""
        with self._lock:
            prices = list(self._prices)

        p25 = self._percentile(prices, 25) if len(prices) > 10 else 0
        p75 = self._percentile(prices, 75) if len(prices) > 10 else 0

        return PriceState(
            ema_fast=round(self._ema_fast or 0, 6),
            ema_slow=round(self._ema_slow or 0, 6),
            volatility=round(self._calc_volatility(), 4),
            percentile_25=round(p25, 6),
            percentile_75=round(p75, 6),
            cap_factor=round(self._cap_factor, 4),
            regime=self._regime,
            observations=self._observations,
        )

    def _update_cap_factor(self):
        """Core logic: determine price cap based on market conditions."""
        prices = list(self._prices)
        n = len(prices)

        if n < 5:
            # Not enough data — use conservative default
            self._cap_factor = 0.90
            self._regime = "WARMUP"
            return

        # Calculate volatility (coefficient of variation)
        volatility = self._calc_volatility()

        # Calculate percentiles
        p25 = self._percentile(prices, 25)
        p75 = self._percentile(prices, 75)
        current = self._ema_fast

        # Determine regime
        if volatility > self.volatility_threshold:
            self._regime = "VOLATILE"
        elif current > p75 * 1.5:
            self._regime = "SPIKE"
        elif current > p75:
            self._regime = "HIGH"
        elif current < p25:
            self._regime = "LOW"
        else:
            self._regime = "NORMAL"

        # Set cap factor based on regime
        if self._regime == "SPIKE":
            # Grid is very expensive — maximize buyer savings
            # P2P should be much cheaper than grid
            self._cap_factor = self.min_cap  # 0.70 = 30% savings
        elif self._regime == "HIGH":
            # Grid is above average — good spread opportunity
            self._cap_factor = 0.78  # ~22% savings
        elif self._regime == "VOLATILE":
            # Uncertain — be cautious, moderate spread
            self._cap_factor = 0.85
        elif self._regime == "LOW":
            # Grid is cheap — tighten spread to protect sellers
            # If P2P is too cheap, sellers won't participate
            self._cap_factor = self.max_cap  # 0.95 = 5% savings (minimum)
        else:
            # NORMAL — balanced approach
            # Scale between min_cap and max_cap based on where current
            # price sits within the P25-P75 range
            if p75 > p25:
                position = (current - p25) / (p75 - p25)
                position = max(0.0, min(1.0, position))
                # Higher grid price → lower cap → more savings
                self._cap_factor = self.max_cap - position * (self.max_cap - 0.82)
            else:
                self._cap_factor = 0.88

        # Clamp
        self._cap_factor = max(self.min_cap, min(self.max_cap, self._cap_factor))

    def _calc_volatility(self) -> float:
        """Calculate coefficient of variation of recent prices."""
        prices = list(self._prices)
        if len(prices) < 5:
            return 0.0
        mean = sum(prices) / len(prices)
        if mean <= 0:
            return 0.0
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        return math.sqrt(variance) / mean

    @staticmethod
    def _percentile(data: list, pct: float) -> float:
        """Calculate percentile of a list."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = (pct / 100) * (len(sorted_data) - 1)
        lower = sorted_data[int(idx)]
        upper = sorted_data[min(int(idx) + 1, len(sorted_data) - 1)]
        frac = idx - int(idx)
        return lower + frac * (upper - lower)


# ── Singleton instances for each district ───────────────────
_agents = {}

def get_pricing_agent(district: str = "D91", supply_rate: float = 0.070) -> PricingAgent:
    """Get or create a pricing agent for a district."""
    if district not in _agents:
        _agents[district] = PricingAgent(supply_rate=supply_rate)
    return _agents[district]

def all_agent_states() -> dict:
    """Return state of all pricing agents."""
    return {k: v.get_state().__dict__ for k, v in _agents.items()}
