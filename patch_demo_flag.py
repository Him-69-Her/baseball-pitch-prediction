#!/usr/bin/env python3
"""Add --demo flag to shadow_simulator.py that forces daytime DNI."""
from pathlib import Path

f = Path("shadow_simulator.py")
src = f.read_text()
orig = src

# 1) Add DEMO_MODE detection near the top config
src = src.replace(
    'BUILDINGS_FILE = os.environ.get("BUILDINGS_FILE", "district91_buildings.json")',
    'BUILDINGS_FILE = os.environ.get("BUILDINGS_FILE", "district91_buildings.json")\nDEMO_MODE = "--demo" in sys.argv'
)

# 2) Modify get_current_dni to force simulated daytime when in demo mode
src = src.replace(
    'def get_current_dni() -> float:\n    """Fetch real-time DNI from Open-Meteo for Peoria, IL area."""',
    'def get_current_dni() -> float:\n    """Fetch real-time DNI from Open-Meteo for Peoria, IL area. In demo mode, simulates daytime."""'
)

# 3) Add demo override at the start of get_current_dni
src = src.replace(
    '    try:\n        import urllib.request\n        url = (',
    '    if DEMO_MODE:\n        # Simulate a sunny afternoon for demo purposes\n        simulated = random.uniform(550, 850)\n        print(f"  Weather (DEMO): DNI={simulated:.0f} W/m2 (simulated daytime)")\n        return simulated\n\n    try:\n        import urllib.request\n        url = ('
)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] --demo flag added to shadow_simulator.py")
