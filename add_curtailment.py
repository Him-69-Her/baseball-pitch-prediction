#!/usr/bin/env python3
"""
TINY-HUB — Automated Curtailment (Negative Pricing)

When the P2P clearing price drops below the curtailment floor:
  - Solar sellers are curtailed (output = 0) for that tick
  - Trade published with trade_status = "CURTAILED"
  - Dashboard shows ✂️ CURTAILED trades in the feed

Curtailment floor: $0.005/kWh ($5/MWh) — below this it's not worth selling.
Battery sellers are exempt (they can just stop discharging).

Run from project root:
    python3 add_curtailment.py
"""

from pathlib import Path

TARGET = Path("d91_marketplace_live.py")
src = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add curtailment constants after ISLAND_THRESHOLD ──
OLD_CONST = "AMEREN_TOLL    = 0.025"
NEW_CONST = """AMEREN_TOLL    = 0.025
CURTAIL_FLOOR  = 0.005   # $/kWh — curtail solar if clearing price drops below this
curtailed_count = 0      # running count of curtailed events"""

if OLD_CONST not in src:
    # Try alternate constant name
    OLD_CONST = 'AMEREN_TOLL = 0.025'
    NEW_CONST = """AMEREN_TOLL = 0.025
CURTAIL_FLOOR  = 0.005   # $/kWh — curtail solar if clearing price drops below this
curtailed_count = 0      # running count of curtailed events"""

if OLD_CONST not in src:
    print("  ❌ Patch 1 failed — AMEREN_TOLL constant not found")
    exit(1)

src = src.replace(OLD_CONST, NEW_CONST, 1)
print("  ✅ Patch 1: curtailment constants added")

# ── Patch 2: Add curtailment check in run_trade() ──────────
# Find the global declaration line and add curtailed_count
OLD_GLOBAL = "def run_trade():\n    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events"
NEW_GLOBAL = "def run_trade():\n    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events, curtailed_count"

if OLD_GLOBAL not in src:
    print("  ❌ Patch 2 failed — run_trade global declaration not found")
    exit(1)

src = src.replace(OLD_GLOBAL, NEW_GLOBAL, 1)
print("  ✅ Patch 2: curtailed_count added to global declaration")

# ── Patch 3: Add curtailment check before trade settlement ──
OLD_TRADE_CHECK = """    if bid_price >= ask_price:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += profit
        total_mwh_traded += mwh
        town_trades[seller["town"]] += 1
        town_mwh[seller["town"]] += mwh
        town_profit[seller["town"]] += profit
    else:
        status = "REJECTED"
        rejected_count += 1
        settled = 0.0
        profit = 0.0"""

NEW_TRADE_CHECK = """    # ── Automated curtailment ──────────────────────────────
    # If the clearing price is below the floor, curtail solar sellers.
    # Batteries are exempt — they just stop discharging (handled by VPP).
    projected_clearing = round((ask_price + bid_price) / 2, 4)
    is_solar = seller.get("type") not in ("battery",) and not seller.get("is_ev", False)
    if is_solar and projected_clearing < CURTAIL_FLOOR:
        curtailed_count += 1
        status = "CURTAILED"
        settled = 0.0
        profit = 0.0
        mwh = 0.0
    elif bid_price >= ask_price:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += profit
        total_mwh_traded += mwh
        town_trades[seller["town"]] += 1
        town_mwh[seller["town"]] += mwh
        town_profit[seller["town"]] += profit
    else:
        status = "REJECTED"
        rejected_count += 1
        settled = 0.0
        profit = 0.0"""

if OLD_TRADE_CHECK not in src:
    print("  ❌ Patch 3 failed — trade settlement block not found")
    exit(1)

src = src.replace(OLD_TRADE_CHECK, NEW_TRADE_CHECK, 1)
print("  ✅ Patch 3: curtailment check added before trade settlement")

# ── Patch 4: Add curtailed count to scoreboard printout ────
OLD_SCOREBOARD = '        print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")'
NEW_SCOREBOARD = '''        print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")
        print(f"  ║  Curtailed events:  {curtailed_count:>6}                                           ║")'''

if OLD_SCOREBOARD not in src:
    print("  ⚠️  Patch 4: scoreboard line not found — skipping (non-critical)")
else:
    src = src.replace(OLD_SCOREBOARD, NEW_SCOREBOARD, 1)
    print("  ✅ Patch 4: curtailed count added to scoreboard")

TARGET.write_text(src, encoding="utf-8")

# ── Patch dashboard.html for CURTAILED status styling ──────
DASH = Path("templates/dashboard.html")
dsrc = DASH.read_text(encoding="utf-8")

OLD_STATUS_CSS = ".trade-status.bridge { color: var(--purple); }"
NEW_STATUS_CSS = ".trade-status.bridge { color: var(--purple); } .trade-status.curtailed { color: #ff6b6b; }"

if OLD_STATUS_CSS in dsrc:
    dsrc = dsrc.replace(OLD_STATUS_CSS, NEW_STATUS_CSS, 1)
    print("  ✅ Patch 5: CURTAILED CSS style added to dashboard")
else:
    print("  ⚠️  Patch 5: CSS line not found — skipping")

OLD_SCLASS = "function sClass(s) { if (s==='SETTLED') return 'settled'; if (s==='ISLAND_SETTLED') return 'island'; if (s==='BRIDGE_LISTED') return 'bridge'; return 'rejected'; }"
NEW_SCLASS = "function sClass(s) { if (s==='SETTLED') return 'settled'; if (s==='ISLAND_SETTLED') return 'island'; if (s==='BRIDGE_LISTED') return 'bridge'; if (s==='CURTAILED') return 'curtailed'; return 'rejected'; }"

if OLD_SCLASS in dsrc:
    dsrc = dsrc.replace(OLD_SCLASS, NEW_SCLASS, 1)
    print("  ✅ Patch 6: CURTAILED class added to sClass()")
else:
    print("  ⚠️  Patch 6: sClass() not found — skipping")

OLD_SICON = "function sIcon(s) { if (s==='SETTLED') return '⚡'; if (s==='ISLAND_SETTLED') return '🏝️'; if (s==='BRIDGE_LISTED') return '🌉'; if (s==='FALLBACK') return '🔌'; return '❌'; }"
NEW_SICON = "function sIcon(s) { if (s==='SETTLED') return '⚡'; if (s==='ISLAND_SETTLED') return '🏝️'; if (s==='BRIDGE_LISTED') return '🌉'; if (s==='FALLBACK') return '🔌'; if (s==='CURTAILED') return '✂️'; return '❌'; }"

if OLD_SICON in dsrc:
    dsrc = dsrc.replace(OLD_SICON, NEW_SICON, 1)
    print("  ✅ Patch 7: CURTAILED icon ✂️ added to sIcon()")
else:
    print("  ⚠️  Patch 7: sIcon() not found — skipping")

DASH.write_text(dsrc, encoding="utf-8")

print()
print("  ✅ Automated curtailment complete.")
print("     Solar sellers are curtailed when P2P clearing price < $0.005/kWh")
print("     Batteries are exempt — VPP handles their discharge decisions.")
print("     Dashboard shows ✂️ CURTAILED trades in the live feed.")
print()
print("  Restart marketplace + dashboard to apply.")
