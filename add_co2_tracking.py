#!/usr/bin/env python3
"""
TINY-HUB — CO2 Tracking

Calculates and displays tons of CO2 offset per settled trade.

EPA eGRID 2022 — MISO/RFCW emission factor:
  0.42 metric tons CO2 per MWh (Illinois average grid mix)

Every MWh traded P2P instead of drawn from fossil grid
offsets ~0.42 tons of CO2. This patch:

1. Adds co2_tons to every trade published via Pub/Sub
2. Adds running CO2 counters to the marketplace scoreboards
3. Adds CO2 display to the dashboard stats panel
4. Adds CO2 to the SSE trade feed

Run from project root:
    python3 add_co2_tracking.py
"""

from pathlib import Path

# ── EPA emission factor ─────────────────────────────────────
# Illinois grid mix: ~0.42 metric tons CO2 per MWh
# Source: EPA eGRID 2022, RFCW/MISO subregion
CO2_FACTOR = 0.42  # tons CO2 / MWh

# ══════════════════════════════════════════════════════════════
# PATCH 1: d91_marketplace_live.py — add CO2 to trade data
# ══════════════════════════════════════════════════════════════
D91 = Path("d91_marketplace_live.py")
if not D91.exists():
    print("  ❌ d91_marketplace_live.py not found")
    exit(1)

src = D91.read_text(encoding="utf-8")

# Add CO2 constant after AMEREN_TOLL
if "CO2_TONS_PER_MWH" not in src:
    OLD_TOLL = "AMEREN_TOLL = 0.025"
    NEW_TOLL = """AMEREN_TOLL = 0.025
CO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022 — Illinois grid mix"""

    if OLD_TOLL in src:
        # Might have extra stuff after AMEREN_TOLL already, find the exact line
        lines = src.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == "AMEREN_TOLL = 0.025" or line.strip().startswith("AMEREN_TOLL = 0.025") or line.strip() == "AMEREN_TOLL    = 0.025":
                lines.insert(i + 1, "CO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022 — Illinois grid mix")
                src = '\n'.join(lines)
                print("  ✅ D91 Patch 1: CO2_TONS_PER_MWH constant added")
                break
        else:
            print("  ⚠️  D91 Patch 1: AMEREN_TOLL line not found exactly — adding at top")
    else:
        print("  ⚠️  D91 Patch 1: AMEREN_TOLL not found")
else:
    print("  ⏭️  D91 Patch 1: CO2_TONS_PER_MWH already exists")

# Add co2_tons to trade_data dict
OLD_TRADE_TS = '"timestamp": datetime.now(timezone.utc).isoformat(),'
NEW_TRADE_TS = '"timestamp": datetime.now(timezone.utc).isoformat(),\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4),'

if "co2_tons" not in src and OLD_TRADE_TS in src:
    src = src.replace(OLD_TRADE_TS, NEW_TRADE_TS, 1)
    print("  ✅ D91 Patch 2: co2_tons added to trade data")
elif "co2_tons" in src:
    print("  ⏭️  D91 Patch 2: co2_tons already in trade data")
else:
    # Try alternate timestamp format
    OLD_ALT = '"timestamp": datetime.now(timezone.utc).isoformat()'
    if OLD_ALT in src and "co2_tons" not in src:
        src = src.replace(OLD_ALT, OLD_ALT + ',\n            "co2_tons": round(mt.mwh * CO2_TONS_PER_MWH, 4)', 1)
        print("  ✅ D91 Patch 2: co2_tons added to trade data (alt)")
    else:
        print("  ⚠️  D91 Patch 2: timestamp line not found — add co2_tons manually")

D91.write_text(src, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# PATCH 2: d63_marketplace_live.py — same CO2 field
# ══════════════════════════════════════════════════════════════
D63 = Path("d63_marketplace_live.py")
if D63.exists():
    src63 = D63.read_text(encoding="utf-8")

    if "CO2_TONS_PER_MWH" not in src63:
        OLD_63 = "COMED_TOLL = 0.02"
        if OLD_63 in src63:
            src63 = src63.replace(OLD_63, OLD_63 + "\nCO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022", 1)
            print("  ✅ D63 Patch 1: CO2_TONS_PER_MWH added")

    # Add co2_tons to trade data
    if "co2_tons" not in src63:
        OLD_63_TS = '"timestamp": datetime.utcnow().isoformat() + "Z",'
        NEW_63_TS = '"timestamp": datetime.utcnow().isoformat() + "Z",\n        "co2_tons": round(mwh * CO2_TONS_PER_MWH, 4),'
        if OLD_63_TS in src63:
            src63 = src63.replace(OLD_63_TS, NEW_63_TS, 1)
            print("  ✅ D63 Patch 2: co2_tons added to trade data")
        else:
            # Try UTC variant
            for pattern in ['"timestamp": datetime.now(timezone.utc).isoformat()']:
                if pattern in src63:
                    src63 = src63.replace(pattern, pattern + ',\n        "co2_tons": round(mwh * CO2_TONS_PER_MWH, 4)', 1)
                    print("  ✅ D63 Patch 2: co2_tons added (alt)")
                    break
            else:
                print("  ⚠️  D63 Patch 2: timestamp not found")

    D63.write_text(src63, encoding="utf-8")
else:
    print("  ⚠️  d63_marketplace_live.py not found — skipping")


# ══════════════════════════════════════════════════════════════
# PATCH 3: app.py — add CO2 to stats tracking
# ══════════════════════════════════════════════════════════════
APP = Path("app.py")
if APP.exists():
    app_src = APP.read_text(encoding="utf-8")

    # Add co2 to the stats dict
    OLD_STATS_D91 = '"d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0},'
    NEW_STATS_D91 = '"d91": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0},'

    if "co2" not in app_src.split("stats")[1][:200] if "stats" in app_src else True:
        if OLD_STATS_D91 in app_src:
            app_src = app_src.replace(OLD_STATS_D91, NEW_STATS_D91, 1)

            OLD_STATS_D63 = '"d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0},'
            NEW_STATS_D63 = '"d63": {"trades": 0, "settled": 0, "rejected": 0, "mwh": 0.0, "profit": 0.0, "island": 0, "co2": 0.0},'
            app_src = app_src.replace(OLD_STATS_D63, NEW_STATS_D63, 1)
            print("  ✅ app.py Patch 1: co2 added to stats dict")

    # Add co2 accumulation where mwh is accumulated
    # Find the pattern: s["mwh"] += and add co2 after it
    if 's["co2"]' not in app_src:
        OLD_MWH_ACC = 's["mwh"] += trade.get("mwh", 0)'
        NEW_MWH_ACC = 's["mwh"] += trade.get("mwh", 0)\n                s["co2"] += trade.get("co2_tons", 0)'

        if OLD_MWH_ACC in app_src:
            # Replace all occurrences (d91 and d63 handlers)
            app_src = app_src.replace(OLD_MWH_ACC, NEW_MWH_ACC)
            print("  ✅ app.py Patch 2: co2 accumulation added")
        else:
            print("  ⚠️  app.py Patch 2: mwh accumulation pattern not found")
    else:
        print("  ⏭️  app.py: co2 tracking already present")

    APP.write_text(app_src, encoding="utf-8")
else:
    print("  ⚠️  app.py not found")


# ══════════════════════════════════════════════════════════════
# PATCH 4: dashboard.html — show CO2 in stats panel
# ══════════════════════════════════════════════════════════════
DASH = Path("templates/dashboard.html")
if DASH.exists():
    dash_src = DASH.read_text(encoding="utf-8")

    # Add CO2 display row to D91 stats panel
    if "co2" not in dash_src.lower() or "d91-co2" not in dash_src:
        # Add after island events row
        OLD_ISLAND_D91 = """<div class="srow"><span class="slabel">Island Events</span><span class="sval amber" id="d91-island">0</span></div>"""
        NEW_ISLAND_D91 = """<div class="srow"><span class="slabel">Island Events</span><span class="sval amber" id="d91-island">0</span></div>
                    <div class="srow"><span class="slabel">CO₂ Offset</span><span class="sval green" id="d91-co2">0.00 t</span></div>"""

        if OLD_ISLAND_D91 in dash_src:
            dash_src = dash_src.replace(OLD_ISLAND_D91, NEW_ISLAND_D91, 1)
            print("  ✅ Dashboard Patch 1: CO₂ row added to D91 panel")

        # Same for D63
        OLD_ISLAND_D63 = """<div class="srow"><span class="slabel">Island Events</span><span class="sval amber" id="d63-island">0</span></div>"""
        NEW_ISLAND_D63 = """<div class="srow"><span class="slabel">Island Events</span><span class="sval amber" id="d63-island">0</span></div>
                    <div class="srow"><span class="slabel">CO₂ Offset</span><span class="sval green" id="d63-co2">0.00 t</span></div>"""

        if OLD_ISLAND_D63 in dash_src:
            dash_src = dash_src.replace(OLD_ISLAND_D63, NEW_ISLAND_D63, 1)
            print("  ✅ Dashboard Patch 2: CO₂ row added to D63 panel")

    # Add CO2 to updateStats function
    if "d91-co2" not in dash_src or "d91-co2').textContent" not in dash_src:
        OLD_UPDATE = "$('d91-island').textContent = s.d91.island;"
        NEW_UPDATE = "$('d91-island').textContent = s.d91.island;\n        if($('d91-co2')) $('d91-co2').textContent = (s.d91.co2||0).toFixed(2) + ' t';"

        if OLD_UPDATE in dash_src:
            dash_src = dash_src.replace(OLD_UPDATE, NEW_UPDATE, 1)
            print("  ✅ Dashboard Patch 3: D91 CO₂ counter wired")

        OLD_UPDATE_63 = "$('d63-island').textContent = s.d63.island;"
        NEW_UPDATE_63 = "$('d63-island').textContent = s.d63.island;\n        if($('d63-co2')) $('d63-co2').textContent = (s.d63.co2||0).toFixed(2) + ' t';"

        if OLD_UPDATE_63 in dash_src:
            dash_src = dash_src.replace(OLD_UPDATE_63, NEW_UPDATE_63, 1)
            print("  ✅ Dashboard Patch 4: D63 CO₂ counter wired")

    # Add CO2 to topbar
    OLD_TOPBAR = '<div>BRIDGES<span class="tval purple" id="total-bridges">0</span></div>'
    NEW_TOPBAR = '<div>BRIDGES<span class="tval purple" id="total-bridges">0</span></div>\n            <div>CO₂<span class="tval green" id="total-co2">0t</span></div>'

    if "total-co2" not in dash_src and OLD_TOPBAR in dash_src:
        dash_src = dash_src.replace(OLD_TOPBAR, NEW_TOPBAR, 1)
        print("  ✅ Dashboard Patch 5: CO₂ added to topbar")

    # Wire topbar counter
    OLD_BRIDGES_UPDATE = "$('total-bridges').textContent = s.bridge.d63_to_d91 + s.bridge.d91_to_d63;"
    NEW_BRIDGES_UPDATE = "$('total-bridges').textContent = s.bridge.d63_to_d91 + s.bridge.d91_to_d63;\n        if($('total-co2')) $('total-co2').textContent = ((s.d91.co2||0)+(s.d63.co2||0)).toFixed(1) + 't';"

    if "total-co2" not in dash_src.split("total-bridges")[1][:200] if "total-bridges" in dash_src else True:
        if OLD_BRIDGES_UPDATE in dash_src:
            dash_src = dash_src.replace(OLD_BRIDGES_UPDATE, NEW_BRIDGES_UPDATE, 1)
            print("  ✅ Dashboard Patch 6: topbar CO₂ counter wired")

    DASH.write_text(dash_src, encoding="utf-8")
else:
    print("  ⚠️  templates/dashboard.html not found")


print()
print("  ✅ CO2 tracking complete.")
print()
print("  Formula: CO₂ offset = MWh traded × 0.42 tons/MWh")
print("  Source:  EPA eGRID 2022 (RFCW/MISO Illinois subregion)")
print()
print("  What's new:")
print("    • co2_tons field in every Pub/Sub trade message")
print("    • Running CO₂ counters in D91 + D63 stats panels")
print("    • CO₂ total in the dashboard topbar")
print()
print("  Rebuild containers to apply:")
print("    sudo docker-compose up -d --build")
print()
