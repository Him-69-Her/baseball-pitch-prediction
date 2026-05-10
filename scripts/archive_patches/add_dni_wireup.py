#!/usr/bin/env python3
"""
TINY-HUB — Wire real Open-Meteo DNI into solar_output()

Currently solar_output() calculates irradiance as:
    irradiance = math.sin(math.radians(alt_deg))

This is a geometric approximation. Open-Meteo already returns real
Direct Normal Irradiance (DNI) in W/m² via get_weather(). This patch
replaces the sin(altitude) approximation with actual DNI data.

DNI typically ranges 0-1000 W/m², so we normalize to 0-1 by dividing
by 1000. The sun altitude check is kept as a safety net (DNI should be
0 at night anyway, but belt-and-suspenders).

Patches both:
  - d91_marketplace_live.py (Peoria/Ameren)
  - d63_marketplace_live.py (McHenry/ComEd)

Run from project root:
    python3 add_dni_wireup.py
"""

from pathlib import Path

# ══════════════════════════════════════════════════════════════
# PATCH D91
# ══════════════════════════════════════════════════════════════
D91 = Path("d91_marketplace_live.py")
if not D91.exists():
    print(f"  ❌ {D91} not found. Run from your project root.")
    exit(1)

src = D91.read_text(encoding="utf-8")

OLD_D91 = """    # Irradiance factor: 0 at horizon, 1 at 90°
    irradiance = math.sin(math.radians(alt_deg))

    # Cloud cover: real weather from Open-Meteo
    weather = get_weather(lat, lng)
    cloud = cloud_factor(weather["cloud_cover"])

    # Panel efficiency (degrades slightly at very high/low angles)
    efficiency = 0.85 if alt_deg > 15 else 0.65

    # Output
    mwh = capacity_mwh * irradiance * cloud * efficiency * random.uniform(0.2, 0.4)"""

NEW_D91 = """    # Real DNI from Open-Meteo (W/m², 0-1000 typical range)
    weather = get_weather(lat, lng)
    dni = weather.get("dni", 0.0)

    if dni <= 0 and alt_deg <= 2:
        # Night / deep twilight — no output
        if random.random() < 0.15:
            return round(capacity_mwh * random.uniform(0.05, 0.15), 3)
        return 0.0

    # Normalize DNI to 0-1 (1000 W/m² = clear sky peak)
    irradiance = min(dni / 1000.0, 1.0)

    # If Open-Meteo returned 0 DNI but sun is up, fall back to sin(altitude)
    if irradiance < 0.01 and alt_deg > 5:
        irradiance = math.sin(math.radians(alt_deg))
        cloud = cloud_factor(weather["cloud_cover"])
        irradiance *= cloud

    # Panel efficiency (degrades at low sun angles)
    efficiency = 0.85 if alt_deg > 15 else 0.65

    # Output — DNI already accounts for cloud cover, no double-dipping
    mwh = capacity_mwh * irradiance * efficiency * random.uniform(0.2, 0.4)"""

if OLD_D91 not in src:
    print("  ❌ D91 patch failed — solar_output irradiance block not found.")
    print("     The code may have already been patched or manually edited.")
    exit(1)

src = src.replace(OLD_D91, NEW_D91, 1)
D91.write_text(src, encoding="utf-8")
print("  ✅ d91_marketplace_live.py — solar_output() now uses real DNI from Open-Meteo")


# ══════════════════════════════════════════════════════════════
# PATCH D63
# ══════════════════════════════════════════════════════════════
D63 = Path("d63_marketplace_live.py")
if not D63.exists():
    print(f"  ⚠️  {D63} not found — skipping D63 patch")
else:
    src63 = D63.read_text(encoding="utf-8")

    OLD_D63 = """    irradiance = math.sin(math.radians(alt_deg))
    weather = get_weather(lat, lng)
    cloud = cloud_factor(weather["cloud_cover"])
    efficiency = 0.85 if alt_deg > 15 else 0.65
    mwh = capacity_mwh * irradiance * cloud * efficiency * random.uniform(0.2, 0.4)"""

    NEW_D63 = """    # Real DNI from Open-Meteo (W/m², 0-1000 typical range)
    weather = get_weather(lat, lng)
    dni = weather.get("dni", 0.0)

    if dni <= 0 and alt_deg <= 2:
        return 0.0

    # Normalize DNI to 0-1 (1000 W/m² = clear sky peak)
    irradiance = min(dni / 1000.0, 1.0)

    # Fallback to sin(altitude) if DNI is 0 but sun is up
    if irradiance < 0.01 and alt_deg > 5:
        irradiance = math.sin(math.radians(alt_deg))
        cloud = cloud_factor(weather["cloud_cover"])
        irradiance *= cloud

    efficiency = 0.85 if alt_deg > 15 else 0.65
    # DNI already includes atmospheric conditions — no cloud double-dip
    mwh = capacity_mwh * irradiance * efficiency * random.uniform(0.2, 0.4)"""

    if OLD_D63 not in src63:
        print("  ⚠️  D63 patch — irradiance block not found (may differ slightly)")
        print("     You may need to patch d63_marketplace_live.py manually.")
    else:
        src63 = src63.replace(OLD_D63, NEW_D63, 1)
        D63.write_text(src63, encoding="utf-8")
        print("  ✅ d63_marketplace_live.py — solar_output() now uses real DNI from Open-Meteo")


print()
print("  ✅ Open-Meteo DNI wire-up complete.")
print()
print("  What changed:")
print("    BEFORE: irradiance = sin(sun_altitude)  ← geometric estimate")
print("    AFTER:  irradiance = DNI / 1000          ← real W/m² from Open-Meteo")
print()
print("  Safety nets:")
print("    - Falls back to sin(altitude) if DNI=0 but sun is above 5°")
print("    - Keeps nighttime battery discharge logic unchanged")
print("    - No cloud_factor double-dip (DNI already factors in atmosphere)")
print()
print("  Restart both marketplaces to apply.")
print()
