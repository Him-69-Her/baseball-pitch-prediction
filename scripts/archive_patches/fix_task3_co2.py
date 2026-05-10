#!/usr/bin/env python3
"""
TINY-HUB — Task #3 Fix: CO₂ Counter Stuck at 0.00
===================================================
Root cause:
  1. app.py Pub/Sub callbacks accumulate mwh and profit but
     never accumulate co2_tons into stats["d63"]["co2"] / stats["d91"]["co2"]
  2. The previous add_co2_tracking.py patch searched for s["mwh"]
     but actual code uses stats["d63"]["mwh"] — pattern mismatch

Fix:
  1. Add co2 accumulation in app.py d63_callback and d91_callback
  2. Verify co2_tons field is published from marketplaces
  3. Add fallback calculation (mwh * 0.42) if co2_tons missing

Run from project root:
    python3 fix_task3_co2.py
"""
from pathlib import Path

patches = 0

# ══════════════════════════════════════════════════════════════
# FIX 1: app.py — add co2 accumulation to both callbacks
# ══════════════════════════════════════════════════════════════
APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Fix D63 callback — add co2 after profit accumulation
OLD_D63_PROFIT = '''                stats["d63"]["mwh"] += trade.get("mwh", 0)
                stats["d63"]["profit"] += trade.get("net_profit", 0)'''

NEW_D63_PROFIT = '''                stats["d63"]["mwh"] += trade.get("mwh", 0)
                stats["d63"]["profit"] += trade.get("net_profit", 0)
                stats["d63"]["co2"] += trade.get("co2_tons", trade.get("mwh", 0) * 0.42)'''

if 'stats["d63"]["co2"]' not in src:
    if OLD_D63_PROFIT in src:
        src = src.replace(OLD_D63_PROFIT, NEW_D63_PROFIT, 1)
        patches += 1
        print("  ✅ Fix 1a: co2 accumulation added to d63_callback")
    else:
        print("  ⚠️  Fix 1a: D63 profit pattern not found — check manually")
else:
    print("  ⏭️  Fix 1a: D63 co2 already accumulating")

# Fix D91 callback — same pattern
OLD_D91_PROFIT = '''                stats["d91"]["mwh"] += trade.get("mwh", 0)
                stats["d91"]["profit"] += trade.get("net_profit", 0)'''

NEW_D91_PROFIT = '''                stats["d91"]["mwh"] += trade.get("mwh", 0)
                stats["d91"]["profit"] += trade.get("net_profit", 0)
                stats["d91"]["co2"] += trade.get("co2_tons", trade.get("mwh", 0) * 0.42)'''

if 'stats["d91"]["co2"]' not in src:
    if OLD_D91_PROFIT in src:
        src = src.replace(OLD_D91_PROFIT, NEW_D91_PROFIT, 1)
        patches += 1
        print("  ✅ Fix 1b: co2 accumulation added to d91_callback")
    else:
        print("  ⚠️  Fix 1b: D91 profit pattern not found — check manually")
else:
    print("  ⏭️  Fix 1b: D91 co2 already accumulating")

# Ensure co2 is in the stats dict (should already be from add_co2_tracking.py)
if '"co2": 0.0' not in src:
    # Add it to both district dicts
    OLD_D63_STATS = '"d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0}'
    NEW_D63_STATS = '"d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0}'

    OLD_D91_STATS = '"d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0}'
    NEW_D91_STATS = '"d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0}'

    if OLD_D63_STATS in src:
        src = src.replace(OLD_D63_STATS, NEW_D63_STATS, 1)
        print("  ✅ Fix 1c: co2 field added to d63 stats dict")
    if OLD_D91_STATS in src:
        src = src.replace(OLD_D91_STATS, NEW_D91_STATS, 1)
        print("  ✅ Fix 1d: co2 field added to d91 stats dict")
else:
    print("  ⏭️  Stats dict already has co2 field")

# Also add co2 to the /api/stats rate calculation section
# so the stats endpoint includes the district-level rate field
# (already served as full dict, so just need the accumulation)

APP.write_text(src, encoding="utf-8")
print()

# ══════════════════════════════════════════════════════════════
# FIX 2: d91_marketplace_live.py — ensure co2_tons in trade payload
# ══════════════════════════════════════════════════════════════
D91 = Path("d91_marketplace_live.py")
if D91.exists():
    d91_src = D91.read_text(encoding="utf-8")

    if "co2_tons" not in d91_src:
        # Find where trade_data dict is built and add co2_tons
        # The trade payload should have co2_tons = mwh * 0.42
        OLD_TS = '"timestamp": datetime.now(timezone.utc).isoformat(),'
        NEW_TS = '"timestamp": datetime.now(timezone.utc).isoformat(),\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4),'

        if OLD_TS in d91_src:
            d91_src = d91_src.replace(OLD_TS, NEW_TS, 1)
            patches += 1
            print("  ✅ Fix 2a: co2_tons added to D91 trade payload")
        else:
            # Try without trailing comma
            OLD_TS2 = '"timestamp": datetime.now(timezone.utc).isoformat()'
            if OLD_TS2 in d91_src:
                d91_src = d91_src.replace(
                    OLD_TS2,
                    OLD_TS2 + ',\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4)',
                    1
                )
                patches += 1
                print("  ✅ Fix 2a: co2_tons added to D91 trade payload (alt)")
            else:
                print("  ⚠️  Fix 2a: D91 timestamp pattern not found")

        # Ensure CO2_TONS_PER_MWH constant exists
        if "CO2_TONS_PER_MWH" not in d91_src:
            d91_src = d91_src.replace(
                "AMEREN_TOLL = 0.025",
                "AMEREN_TOLL = 0.025\nCO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022 — Illinois grid mix",
                1
            )
            print("  ✅ Fix 2b: CO2_TONS_PER_MWH constant added to D91")

        D91.write_text(d91_src, encoding="utf-8")
    else:
        print("  ⏭️  D91 already publishes co2_tons")
else:
    print("  ⚠️  d91_marketplace_live.py not found")

# ══════════════════════════════════════════════════════════════
# FIX 3: d63_marketplace_live.py — same fix
# ══════════════════════════════════════════════════════════════
D63 = Path("d63_marketplace_live.py")
if D63.exists():
    d63_src = D63.read_text(encoding="utf-8")

    if "co2_tons" not in d63_src:
        # D63 might use different variable names
        for ts_pattern in [
            '"timestamp": datetime.now(timezone.utc).isoformat(),',
            '"timestamp": datetime.utcnow().isoformat() + "Z",',
            '"timestamp": datetime.now(timezone.utc).isoformat()',
        ]:
            if ts_pattern in d63_src:
                if ts_pattern.endswith(","):
                    new_line = ts_pattern + '\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4),'
                else:
                    new_line = ts_pattern + ',\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4)'
                d63_src = d63_src.replace(ts_pattern, new_line, 1)
                patches += 1
                print(f"  ✅ Fix 3a: co2_tons added to D63 trade payload")
                break
        else:
            print("  ⚠️  Fix 3a: D63 timestamp pattern not found")

        # Ensure constant exists
        if "CO2_TONS_PER_MWH" not in d63_src:
            for toll_pattern in ["COMED_TOLL = 0.02", "COMED_TOLL  = 0.02"]:
                if toll_pattern in d63_src:
                    d63_src = d63_src.replace(
                        toll_pattern,
                        toll_pattern + "\nCO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022",
                        1
                    )
                    print("  ✅ Fix 3b: CO2_TONS_PER_MWH constant added to D63")
                    break

        D63.write_text(d63_src, encoding="utf-8")
    else:
        print("  ⏭️  D63 already publishes co2_tons")
else:
    print("  ⚠️  d63_marketplace_live.py not found")

# ══════════════════════════════════════════════════════════════
# FIX 4: Verify dashboard HTML has CO2 elements
# ══════════════════════════════════════════════════════════════
DASH = Path("templates/dashboard.html")
if DASH.exists():
    dash_src = DASH.read_text(encoding="utf-8")

    if "d91-co2" in dash_src and "d63-co2" in dash_src:
        print("  ✅ Dashboard HTML: CO₂ elements present")
    else:
        print("  ⚠️  Dashboard HTML: CO₂ elements missing — run add_co2_tracking.py first")

    if "s.d91.co2" in dash_src:
        print("  ✅ Dashboard JS: updateStats reads co2")
    else:
        print("  ⚠️  Dashboard JS: co2 not wired in updateStats")

    # Check topbar
    if "total-co2" in dash_src:
        print("  ✅ Dashboard: topbar CO₂ counter present")
    else:
        print("  ⚠️  Dashboard: topbar CO₂ counter missing")
else:
    print("  ⚠️  templates/dashboard.html not found")


print()
print(f"  ✅ Task #3 complete — {patches} patches applied")
print()
print("  Data flow (fixed):")
print("    d91_marketplace → Pub/Sub {co2_tons: 0.42 * mwh}")
print("    app.py d91_callback → stats['d91']['co2'] += co2_tons")
print("    /api/stats → {d91: {co2: 1.23}}")
print("    dashboard.js → $('d91-co2').textContent = '1.23 t'")
print()
print("  Fallback: if co2_tons missing from old trades,")
print("  app.py uses mwh * 0.42 as default.")
print()
print("  Rebuild:")
print("    sudo docker-compose up -d --build d91 d63 dashboard")
print()
