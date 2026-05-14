#!/usr/bin/env python3
"""How It Works: Basic Flow heading + McHenry update + PJM LMP accuracy."""
from pathlib import Path

p = Path("templates/how_it_works.html")
src = p.read_text()

# ─── 1. Add "Basic Flow Overview" H3 heading above flow paragraph ───
old_flow = '''    <div class="prose">
      <p>A rooftop generates surplus solar. The matching engine finds the nearest buyer. The trade settles on Arbitrum L2 in a 5-minute batch. The electrons flow over the existing ComEd or Ameren wire. The neighborhood keeps the profit.</p>'''
new_flow = '''    <div class="prose">
      <h3 class="flow-overview-heading">Basic Flow Overview</h3>
      <p>A rooftop generates surplus solar. The matching engine finds the nearest buyer. The trade settles on Arbitrum L2 in a 5-minute batch. The electrons flow over the existing ComEd or Ameren wire. The neighborhood keeps the profit.</p>'''
assert old_flow in src, "flow paragraph not found"
src = src.replace(old_flow, new_flow)
print("[OK] 1/3 'Basic Flow Overview' H3 added")

heading_css = '''
/* Basic Flow Overview heading */
.flow-overview-heading{
  font-family:'Orbitron',sans-serif;
  font-size:clamp(1.1rem,1.8vw,1.4rem);
  font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--sun-1);text-shadow:0 0 8px var(--sun-3);
  margin:0 0 1rem 0;
}
'''
src = src.replace("</style>", heading_css + "\n</style>", 1)
print("[OK] heading CSS injected")

# ─── 2. District 91 (Ameren / MISO) → McHenry County (ComEd / PJM) ───
old_d91 = "digital twin of District 91 (Ameren / MISO territory) with over a thousand real buildings"
new_mchenry = "digital twin of McHenry County (ComEd / PJM territory) with over a thousand real buildings"
assert old_d91 in src, "D91 digital twin sentence not found"
src = src.replace(old_d91, new_mchenry)
print("[OK] 2/3 District 91 → McHenry County")

# ─── 3. Line 257: MISO LMP (live) → PJM LMP (live) ───
old_lmp = "Open-Meteo DNI + MISO LMP (live)"
new_lmp = "Open-Meteo DNI + PJM LMP (live)"
assert old_lmp in src, "MISO LMP data source line not found"
src = src.replace(old_lmp, new_lmp)
print("[OK] 3/3 MISO LMP → PJM LMP (live data accuracy)")

p.write_text(src)
print("\n[DONE] how_it_works.html patched")
