#!/usr/bin/env python3
"""
TINY-HUB — Wire battery VPP arbitrage into matching_engine.py

Adds a battery_output() helper that marketplaces call instead of
solar_output() for battery sellers. The VPP decides whether to
charge, discharge, or idle based on current LMP and LCOS economics.

Also patches the matching_engine stats() method to include battery status.

Run from project root:
    python3 add_battery_vpp.py
"""

from pathlib import Path

# ── Patch matching_engine.py ─────────────────────────────────
TARGET = Path("matching_engine.py")
if not TARGET.exists():
    print("  ❌ matching_engine.py not found.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# Patch 1: Add battery_vpp import after existing imports
OLD_IMPORT = "from __future__ import annotations"
NEW_IMPORT = """from __future__ import annotations
from battery_vpp import get_battery, all_battery_status"""

if OLD_IMPORT not in source:
    print("  ❌ Patch 1 failed — import block not found.")
    exit(1)

source = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
print("  ✅ Patch 1: battery_vpp import added to matching_engine.py")

# Patch 2: Add battery_output() helper before MatchingEngine class
OLD_CLASS = "class MatchingEngine:"
NEW_HELPER = '''def battery_output(station_id: str, label: str, capacity_mwh: float,
                   grid_price_kwh: float, toll: float = 0.025) -> float:
    """
    VPP arbitrage wrapper for battery sellers.
    Returns MWh to sell this tick (0 if charging or idle).
    Automatically manages state of charge and LCOS economics.
    """
    vpp = get_battery(station_id, label, capacity_mwh, toll)
    return vpp.get_output(grid_price_kwh)


class MatchingEngine:'''

if OLD_CLASS not in source:
    print("  ❌ Patch 2 failed — MatchingEngine class not found.")
    exit(1)

source = source.replace(OLD_CLASS, NEW_HELPER, 1)
print("  ✅ Patch 2: battery_output() helper added")

# Patch 3: Add battery status to stats() method
OLD_STATS = """    def stats(self) -> dict:
        return {
            "pending_sell_orders": len(self._sell_orders),
            "pending_buy_orders":  len(self._buy_orders),
            "sell_mwh_available":  sum(s.remaining_mwh for s in self._sell_orders),
            "buy_mwh_demanded":    sum(b.remaining_mwh for b in self._buy_orders),
        }"""

NEW_STATS = """    def stats(self) -> dict:
        return {
            "pending_sell_orders": len(self._sell_orders),
            "pending_buy_orders":  len(self._buy_orders),
            "sell_mwh_available":  sum(s.remaining_mwh for s in self._sell_orders),
            "buy_mwh_demanded":    sum(b.remaining_mwh for b in self._buy_orders),
            "batteries":           all_battery_status(),
        }"""

if OLD_STATS not in source:
    print("  ⚠️  Patch 3: stats() not found — skipping (non-critical)")
else:
    source = source.replace(OLD_STATS, NEW_STATS, 1)
    print("  ✅ Patch 3: battery status added to stats()")

TARGET.write_text(source, encoding="utf-8")
print()

# ── Patch d91_marketplace_live.py ───────────────────────────
D91 = Path("d91_marketplace_live.py")
if not D91.exists():
    print("  ❌ d91_marketplace_live.py not found.")
    exit(1)

src = D91.read_text(encoding="utf-8")

# Add battery_output to the matching_engine import line
OLD_ME_IMPORT = "from matching_engine import MatchingEngine"
NEW_ME_IMPORT = "from matching_engine import MatchingEngine, battery_output"

if OLD_ME_IMPORT not in src:
    print("  ❌ D91 patch failed — MatchingEngine import not found.")
else:
    src = src.replace(OLD_ME_IMPORT, NEW_ME_IMPORT, 1)
    print("  ✅ D91: battery_output imported")

# Replace battery seller handling in the order submission loop
OLD_BATTERY = """        mwh = solar_output(seller["capacity_mwh"], seller.get("lat", D91_LAT), seller.get("lng", D91_LNG))
        if mwh <= 0:
            continue"""

NEW_BATTERY = """        # Battery VPP: use arbitrage logic instead of solar irradiance
        if seller.get("type") == "battery":
            with GRID_PRICE_LOCK:
                gp = GRID_PRICE_CACHE.get("price") or grid_price
            mwh = battery_output(
                seller["id"], seller.get("label", seller["id"]),
                seller["capacity_mwh"], gp, toll=AMEREN_TOLL
            )
        else:
            mwh = solar_output(seller["capacity_mwh"], seller.get("lat", D91_LAT), seller.get("lng", D91_LNG))
        if mwh <= 0:
            continue"""

if OLD_BATTERY not in src:
    print("  ⚠️  D91 battery patch: solar_output block not found — skipping")
else:
    src = src.replace(OLD_BATTERY, NEW_BATTERY, 1)
    print("  ✅ D91: battery sellers now use VPP arbitrage logic")

D91.write_text(src, encoding="utf-8")
print()
print("  ✅ Battery VPP arbitrage wired in.")
print("     Copy battery_vpp.py to ~/tiny-hub/ then restart the marketplace.")
print()
