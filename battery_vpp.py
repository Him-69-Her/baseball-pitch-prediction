"""
TINY-HUB — Battery VPP Arbitrage + LCOS-Aware Trading
=======================================================
Manages virtual power plant (VPP) battery state for both D63 and D91.

Strategy:
  CHARGE  when MISO/PJM LMP is near zero (cheap grid power fills the battery)
  DISCHARGE when LMP > (charge_price + toll + LCOS) — profitable to sell

LCOS (Levelized Cost of Storage):
  ~$15/MWh degradation cost per cycle. Only discharge if:
    P2P clearing price - charge price > toll + LCOS

Usage:
    from battery_vpp import BatteryVPP

    vpp = BatteryVPP(
        station_id="batt-marengo",
        label="Marengo Battery 20MW",
        capacity_mwh=20.0,
        toll=0.025,           # Ameren toll
    )

    # Each market tick:
    output_mwh = vpp.get_output(grid_price_kwh=0.0178)
    # Returns > 0 if discharging, 0 if charging or idle
"""

from __future__ import annotations
import time


# ── Constants ───────────────────────────────────────────────
LCOS_PER_MWH     = 0.015   # $15/MWh degradation cost ($/kWh = 0.015)
CHARGE_THRESHOLD = 0.020   # Charge when LMP < $0.020/kWh (~$20/MWh)
MIN_SOC          = 0.10    # Never discharge below 10% state of charge
MAX_SOC          = 0.95    # Never charge above 95%
CHARGE_RATE      = 0.20    # Charge at 20% of capacity per tick
DISCHARGE_RATE   = 0.30    # Discharge at 30% of capacity per tick
EVENING_RAMP_START_UTC = 21  # 4 PM CDT = 21:00 UTC
EVENING_RAMP_END_UTC   = 1  # 8 PM CDT = 01:00 UTC


class BatteryVPP:
    """
    Stateful battery with VPP arbitrage and LCOS-aware discharge logic.

    State machine:
        IDLE      → no action (LMP in middle range, not worth charging or discharging)
        CHARGING  → buying cheap grid power to fill battery
        DISCHARGING → selling into P2P market at a profit
    """

    def __init__(self, station_id: str, label: str, capacity_mwh: float,
                 toll: float = 0.025):
        self.station_id   = station_id
        self.label        = label
        self.capacity_mwh = capacity_mwh
        self.toll         = toll

        # State
        self.soc          = 0.50   # State of charge (0–1), start at 50%
        self.charge_price = 0.0    # Avg price paid to charge ($/kWh)
        self.mode         = "IDLE" # IDLE | CHARGING | DISCHARGING
        self.cycles       = 0      # Full charge/discharge cycles completed
        self._last_mode_change = time.time()

    # ── Public API ──────────────────────────────────────────

    def get_output(self, grid_price_kwh: float) -> float:
        """
        Given current grid price ($/kWh), decide whether to charge or discharge.
        Returns MWh available to sell this tick (0 if charging or idle).
        """
        self._update_mode(grid_price_kwh)

        if self.mode == "CHARGING":
            self._do_charge(grid_price_kwh)
            return 0.0

        if self.mode == "DISCHARGING":
            return self._do_discharge()

        return 0.0  # IDLE

    def status(self) -> dict:
        return {
            "station_id":   self.station_id,
            "label":        self.label,
            "mode":         self.mode,
            "soc_pct":      round(self.soc * 100, 1),
            "stored_mwh":   round(self.soc * self.capacity_mwh, 2),
            "charge_price": self.charge_price,
            "cycles":       self.cycles,
        }

    # ── Internal logic ──────────────────────────────────────

    def _update_mode(self, grid_price_kwh: float):
        """Decide the battery mode based on current LMP and LCOS economics."""
        import datetime
        utc_hour = datetime.datetime.utcnow().hour

        # ── Charge decision ─────────────────────────────────
        # Charge when LMP is near zero AND battery isn't full
        if grid_price_kwh <= CHARGE_THRESHOLD and self.soc < MAX_SOC:
            self.mode = "CHARGING"
            return

        # ── Discharge decision ──────────────────────────────
        # Discharge when:
        #   1. Battery has enough charge (above MIN_SOC)
        #   2. Profit > toll + LCOS (won't lose money)
        #   3. Preferably during evening ramp (4-8 PM CDT = 21-01 UTC)
        if self.soc > MIN_SOC:
            min_sell_price = self.charge_price + self.toll + LCOS_PER_MWH
            is_evening_ramp = (utc_hour >= EVENING_RAMP_START_UTC or
                               utc_hour <= EVENING_RAMP_END_UTC)

            # Discharge if profitable AND (evening ramp OR price is very high)
            if grid_price_kwh > min_sell_price:
                if is_evening_ramp or grid_price_kwh > min_sell_price * 2:
                    self.mode = "DISCHARGING"
                    return

        # ── Default: idle ────────────────────────────────────
        self.mode = "IDLE"

    def _do_charge(self, grid_price_kwh: float):
        """Charge the battery at current grid price."""
        charge_mwh = self.capacity_mwh * CHARGE_RATE
        max_fillable = (MAX_SOC - self.soc) * self.capacity_mwh
        actual_mwh = min(charge_mwh, max_fillable)

        if actual_mwh <= 0:
            self.mode = "IDLE"
            return

        # Update weighted average charge price
        stored = self.soc * self.capacity_mwh
        new_stored = stored + actual_mwh
        if new_stored > 0:
            self.charge_price = (
                (stored * self.charge_price + actual_mwh * grid_price_kwh)
                / new_stored
            )

        self.soc = min(MAX_SOC, self.soc + actual_mwh / self.capacity_mwh)

    def _do_discharge(self) -> float:
        """Discharge the battery and return MWh available to sell."""
        discharge_mwh = self.capacity_mwh * DISCHARGE_RATE
        max_dischargeable = (self.soc - MIN_SOC) * self.capacity_mwh
        actual_mwh = min(discharge_mwh, max_dischargeable)

        if actual_mwh <= 0:
            self.mode = "IDLE"
            return 0.0

        prev_soc = self.soc
        self.soc = max(MIN_SOC, self.soc - actual_mwh / self.capacity_mwh)

        # Count cycle (rough: every time we cross from >50% to <50%)
        if prev_soc > 0.50 and self.soc <= 0.50:
            self.cycles += 1

        return round(actual_mwh, 3)


# ── Registry: shared instances across the marketplace ───────
# Keyed by station_id so the same battery object persists across ticks.
_registry: dict[str, BatteryVPP] = {}


def get_battery(station_id: str, label: str, capacity_mwh: float,
                toll: float = 0.025) -> BatteryVPP:
    """Get or create a battery VPP instance."""
    if station_id not in _registry:
        _registry[station_id] = BatteryVPP(station_id, label, capacity_mwh, toll)
    return _registry[station_id]


def all_battery_status() -> list[dict]:
    """Return status of all registered batteries."""
    return [b.status() for b in _registry.values()]
