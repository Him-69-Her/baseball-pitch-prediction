#!/usr/bin/env python3
"""
Fix: move EV SELLERS.extend / BUYERS.extend to after BUYERS list is fully built.
"""
from pathlib import Path

MKT = Path("d91_marketplace_live.py")
src = MKT.read_text(encoding="utf-8")

# Remove the premature extend calls from where they were inserted
OLD_EXTEND = """SELLERS.extend(EV_SELLERS)
BUYERS.extend(EV_BUYERS)
print(f"  EV battery homes: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")"""

src = src.replace(OLD_EXTEND, 'print(f"  EV battery homes staged: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")', 1)

# Add the extend calls after the anchor buyers block (after BUYERS is fully built)
OLD_ANCHOR_END = 'print(f"  TOTAL BUYERS: {len(BUYERS)}")'
NEW_ANCHOR_END = '''# Add EV battery homes to main lists
SELLERS.extend(EV_SELLERS)
BUYERS.extend(EV_BUYERS)
print(f"  EV battery homes: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")
print(f"  TOTAL BUYERS: {len(BUYERS)}")'''

if OLD_ANCHOR_END not in src:
    print("  ❌ Could not find TOTAL BUYERS print — check file manually")
    exit(1)

src = src.replace(OLD_ANCHOR_END, NEW_ANCHOR_END, 1)
MKT.write_text(src, encoding="utf-8")
print("  ✅ Fixed: EV extend() calls moved after BUYERS is fully built")
