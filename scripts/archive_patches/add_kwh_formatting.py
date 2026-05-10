#!/usr/bin/env python3
"""
TINY-HUB — kWh UI formatting + FALLBACK status patch for dashboard.html

1. sClass() — adds 'fallback' CSS class for FALLBACK trades
2. sIcon()  — adds 🔌 icon for FALLBACK trades
3. makeTradeEl — already uses fmtKWh(), just ensure FALLBACK is handled

Run from project root:
    python3 add_kwh_formatting.py
"""

from pathlib import Path

TARGET = Path("templates/dashboard.html")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add fallback to sClass() ───────────────────────
OLD_SCLASS = "function sClass(s) { return s === 'SETTLED' ? 'settled' : s === 'ISLAND_SETTLED' ? 'island' : s === 'REJECTED' ? 'rejected' : s === 'BRIDGE_LISTED' ? 'bridge' : ''; }"
NEW_SCLASS = "function sClass(s) { return s === 'SETTLED' ? 'settled' : s === 'ISLAND_SETTLED' ? 'island' : s === 'REJECTED' ? 'rejected' : s === 'BRIDGE_LISTED' ? 'bridge' : s === 'FALLBACK' ? 'fallback' : ''; }"

if OLD_SCLASS not in source:
    print("  ❌ Patch 1 failed — sClass() not found.")
    exit(1)

source = source.replace(OLD_SCLASS, NEW_SCLASS, 1)
print("  ✅ Patch 1: FALLBACK added to sClass()")

# ── Patch 2: Add fallback to sIcon() ────────────────────────
OLD_SICON = "function sIcon(s) { return s === 'SETTLED' ? '⚡' : s === 'ISLAND_SETTLED' ? '🏝️' : s === 'REJECTED' ? '❌' : s === 'BRIDGE_LISTED' ? '🌉' : '·'; }"
NEW_SICON = "function sIcon(s) { return s === 'SETTLED' ? '⚡' : s === 'ISLAND_SETTLED' ? '🏝️' : s === 'REJECTED' ? '❌' : s === 'BRIDGE_LISTED' ? '🌉' : s === 'FALLBACK' ? '🔌' : '·'; }"

if OLD_SICON not in source:
    print("  ❌ Patch 2 failed — sIcon() not found.")
    exit(1)

source = source.replace(OLD_SICON, NEW_SICON, 1)
print("  ✅ Patch 2: 🔌 icon added for FALLBACK trades")

# ── Patch 3: Add .fallback CSS class ────────────────────────
OLD_CSS = ".trade-status.settled { color: var(--green); } .trade-status.rejected { color: var(--red); } .trade-status.island { color: var(--amber); } .trade-status.bridge { color: var(--purple); }"
NEW_CSS = ".trade-status.settled { color: var(--green); } .trade-status.rejected { color: var(--red); } .trade-status.island { color: var(--amber); } .trade-status.bridge { color: var(--purple); } .trade-status.fallback { color: #94a3b8; }"

if OLD_CSS not in source:
    print("  ❌ Patch 3 failed — CSS trade-status classes not found.")
    exit(1)

source = source.replace(OLD_CSS, NEW_CSS, 1)
print("  ✅ Patch 3: .fallback CSS class added (slate gray)")

# ── Write result ────────────────────────────────────────────
TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ dashboard.html patched.")
print("     - Trade feed shows kWh/MWh automatically (fmtKWh already in use)")
print("     - FALLBACK trades show 🔌 icon in slate gray")
print("     Refresh the dashboard to see changes — no restart needed.")
print()
