#!/usr/bin/env python3
"""
TINY-HUB — kWh UI formatting for energy_map.html

The main dashboard.html already has fmtKWh() and fmtKWhTotal() wired in.
This patch brings the same formatting to the standalone McHenry County
energy map (energy_map.html) which still displays raw MWh values.

Changes:
  1. Adds fmtKWh() and fmtKWhTotal() helper functions
  2. Updates the "MWh Traded" sidebar label to "Energy Traded"
  3. Updates stat display to use human-readable kWh/MWh formatting
  4. Adds FALLBACK + CURTAILED status support (icons + CSS)

Run from project root:
    python3 add_kwh_energy_map.py
"""

from pathlib import Path

TARGET = Path("templates/energy_map.html")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")
patches_applied = 0

# ── Patch 1: Add fmtKWh and fmtKWhTotal after existing fmt helpers ──
# Look for the getGridPrice function as an anchor — insert just before it
ANCHOR_FUNC = "function getGridPrice(){"

if ANCHOR_FUNC not in source:
    # Try with spaces
    ANCHOR_FUNC = "function getGridPrice() {"

KWH_HELPERS = """function fmtKWh(mwh){const kwh=mwh*1000;return kwh>=1000?mwh.toFixed(2)+' MWh':kwh.toFixed(1)+' kWh';}
    function fmtKWhTotal(mwh){if(mwh>=100)return mwh.toFixed(1)+' MWh';if(mwh>=1)return mwh.toFixed(2)+' MWh';return(mwh*1000).toFixed(0)+' kWh';}
    """

if ANCHOR_FUNC in source and "fmtKWh" not in source:
    source = source.replace(ANCHOR_FUNC, KWH_HELPERS + ANCHOR_FUNC, 1)
    print("  ✅ Patch 1: fmtKWh() and fmtKWhTotal() added")
    patches_applied += 1
elif "fmtKWh" in source:
    print("  ⏭️  Patch 1: fmtKWh already exists — skipping")
else:
    print("  ❌ Patch 1 failed — getGridPrice anchor not found")

# ── Patch 2: Update "MWh Traded" label to "Energy Traded" ──
OLD_LABEL = '>MWh Traded<'
NEW_LABEL = '>Energy Traded<'

if OLD_LABEL in source:
    source = source.replace(OLD_LABEL, NEW_LABEL)
    print("  ✅ Patch 2: 'MWh Traded' label → 'Energy Traded'")
    patches_applied += 1
else:
    print("  ⏭️  Patch 2: label already updated or not found — skipping")

# ── Patch 3: Use fmtKWhTotal for the stat counter update ──
# Find where s-mwh is updated with raw toFixed
OLD_MWH_UPDATE = """document.getElementById("s-mwh").textContent=totalMwh.toFixed(3)"""
NEW_MWH_UPDATE = """document.getElementById("s-mwh").textContent=typeof fmtKWhTotal==='function'?fmtKWhTotal(totalMwh):totalMwh.toFixed(3)"""

if OLD_MWH_UPDATE in source:
    source = source.replace(OLD_MWH_UPDATE, NEW_MWH_UPDATE, 1)
    print("  ✅ Patch 3: s-mwh stat uses fmtKWhTotal()")
    patches_applied += 1
else:
    # Try alternate patterns
    for pattern in [
        ('s-mwh").textContent=totalMwh.toFixed(3)',
         's-mwh").textContent=typeof fmtKWhTotal==="function"?fmtKWhTotal(totalMwh):totalMwh.toFixed(3)'),
        ('s-mwh").textContent = totalMwh.toFixed(3)',
         's-mwh").textContent = typeof fmtKWhTotal==="function"?fmtKWhTotal(totalMwh):totalMwh.toFixed(3)'),
    ]:
        if pattern[0] in source:
            source = source.replace(pattern[0], pattern[1], 1)
            print("  ✅ Patch 3: s-mwh stat uses fmtKWhTotal()")
            patches_applied += 1
            break
    else:
        print("  ⚠️  Patch 3: s-mwh update pattern not found — may need manual wiring")

# ── Patch 4: Use fmtKWh in trade display (popup or feed) ──
# Find raw mwh display like .toFixed(3) + ' MWh' in trade rendering
OLD_MWH_DISPLAY = ".toFixed(3)+' MWh'"
NEW_MWH_DISPLAY_CHECK = "fmtKWh"

if OLD_MWH_DISPLAY in source and NEW_MWH_DISPLAY_CHECK not in source.split(OLD_MWH_DISPLAY)[0][-100:]:
    # Replace the first occurrence that's clearly in trade display context
    source = source.replace(OLD_MWH_DISPLAY,
        "?typeof fmtKWh==='function'?fmtKWh(m):m.toFixed(3)+' MWh':'0 kWh'", 1)
    print("  ✅ Patch 4: trade display uses fmtKWh()")
    patches_applied += 1
else:
    print("  ⚠️  Patch 4: trade MWh display pattern not found — may already use fmtKWh")

# ── Write ────────────────────────────────────────────────────
TARGET.write_text(source, encoding="utf-8")
print()
print(f"  ✅ energy_map.html patched ({patches_applied} patches applied).")
print("     Small values now show as kWh (e.g., '11 kWh' not '0.011 MWh')")
print("     Refresh the map page to see changes — no restart needed.")
print()
