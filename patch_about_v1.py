#!/usr/bin/env python3
"""About page: 7 content changes + grid background + dark panels."""
from pathlib import Path

p = Path("templates/about.html")
src = p.read_text()

# ─── 1. Mission statement wording ───
old_mission = "Providing grid upgrades for the future of energy through an affordable, sustainable, and transparent marketplace where communities generate, share, and profit from their own power."
new_mission = "We aim to provide grid upgrades and place real power in the hands of the people for the future of energy through an affordable, sustainable, and transparent marketplace."
assert old_mission in src, "mission text not found"
src = src.replace(old_mission, new_mission)
print("[OK] 1/7 mission statement updated")

# ─── 2. Remove vestigial left accent line ───
old_rail = '''/* Vertical accent rail running down the left margin */
main::before{
  content:"";position:absolute;top:0;bottom:0;left:2rem;width:1px;
  background:linear-gradient(to bottom,transparent,var(--cyan) 8%,var(--cyan) 92%,transparent);
  opacity:.35;
  box-shadow:0 0 8px var(--cyan-dim);
  z-index:-1;
}
@media(max-width:900px){main::before{display:none}}'''
src = src.replace(old_rail, "/* (left accent rail removed) */")
print("[OK] 2/7 left accent rail removed")

# ─── 3. Problem intro paragraph ───
old_intro = '''The grid was built to move power one way, from centralized plants to passive customers. <strong>That model is breaking down.</strong> Data centers are driving record load growth, old generation is retiring, and severe weather is straining infrastructure that was never designed for any of it. To cover the gap, utilities are raising rates faster than their customers can absorb them.'''
new_intro = '''The grid was built to move power one way, from centralized plants to passive customers. <strong>That model prioritizes the success of large corporations who have failed to update grid structure alongside new technology.</strong> Data centers are driving record load growth and straining our infrastructure that was never designed to support such heavy volumes. To cover the gap, utilities are raising rates and placing the results of their failures in the hands of every American business and resident.'''
assert old_intro in src, "problem intro not found"
src = src.replace(old_intro, new_intro)
print("[OK] 3/7 problem intro rewritten")

# ─── 4. Stack stats vertically with alternating glow boxes ───
old_stats = '''.stat-row{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:1.5rem;margin:2.5rem 0 3rem;
  border-top:1px solid rgba(0,240,255,0.18);
  border-bottom:1px solid rgba(0,240,255,0.18);
  padding:1.8rem 0;
}
.stat{text-align:center;padding:0 .5rem}
.stat-num{
  font-family:'Orbitron',sans-serif;
  font-size:clamp(2rem,3.6vw,2.8rem);
  color:var(--sun-1);text-shadow:0 0 8px var(--sun-2);letter-spacing:.02em;
  line-height:1;margin-bottom:.4rem;
}
.stat-label{
  font-family:'JetBrains Mono',monospace;
  font-size:.78rem;letter-spacing:.2em;text-transform:uppercase;color:var(--cyan-dim);
  line-height:1.5;
}'''
new_stats = '''.stat-row{
  display:flex;flex-direction:column;gap:1rem;margin:2.5rem 0 3rem;max-width:440px;
}
.stat{
  display:flex;align-items:center;justify-content:space-between;gap:1.5rem;
  padding:1.4rem 1.8rem;border:1.5px solid;position:relative;transition:all .3s;
  background:linear-gradient(90deg,rgba(0,0,0,0.65),rgba(0,0,0,0.35));
}
.stat:nth-child(odd){
  border-color:var(--sun-2);
  box-shadow:0 0 14px rgba(255,149,0,0.35),inset 0 0 20px rgba(255,149,0,0.08);
}
.stat:nth-child(odd):hover{box-shadow:0 0 22px rgba(255,149,0,0.6),inset 0 0 28px rgba(255,149,0,0.14)}
.stat:nth-child(odd) .stat-num{color:var(--sun-1);text-shadow:0 0 10px var(--sun-2),0 0 24px var(--sun-3)}
.stat:nth-child(odd) .stat-label{color:var(--sun-1);opacity:.85}
.stat:nth-child(even){
  border-color:var(--cyan);
  box-shadow:0 0 14px rgba(0,240,255,0.3),inset 0 0 20px rgba(0,240,255,0.06);
}
.stat:nth-child(even):hover{box-shadow:0 0 22px rgba(0,240,255,0.55),inset 0 0 28px rgba(0,240,255,0.12)}
.stat:nth-child(even) .stat-num{color:var(--cyan);text-shadow:0 0 10px var(--cyan-dim),0 0 22px var(--cyan-dim)}
.stat:nth-child(even) .stat-label{color:var(--cyan);opacity:.85}
.stat-num{
  font-family:'Orbitron',sans-serif;font-size:clamp(1.8rem,3vw,2.4rem);letter-spacing:.02em;line-height:1;flex-shrink:0;
}
.stat-label{
  font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.18em;
  text-transform:uppercase;line-height:1.4;text-align:right;
}'''
assert old_stats in src, "stat-row css not found"
src = src.replace(old_stats, new_stats)
print("[OK] 4/7 stats stacked with alternating gold/cyan glow")

# Also clean up the inline <br> in stat labels so they lay out on one line
src = src.replace("Ameren Rate<br>5-Year Rise", "Ameren Rate 5-Year Rise")
src = src.replace("ComEd Delivery<br>Rate Hike", "ComEd Delivery Rate Hike")
src = src.replace("PJM Capacity<br>Price Surge", "PJM Capacity Price Surge")
src = src.replace("MISO Auction<br>Price Spike", "MISO Auction Price Spike")

# ─── 5. Orange glowing callout on "neighbor's rooftop solar" paragraph ───
old_toll = '''<p>If your neighbor's rooftop solar powers your EV 500 feet away, you still pay the utility a toll for the trip. ComEd charges about $0.02/kWh for this. Ameren charges $0.025/kWh. Neighborhoods are subsidizing a long-distance grid they aren't using.</p>'''
new_toll = '''<p class="callout-orange">If your neighbor's rooftop solar powers your EV 500 feet away, you still pay the utility a toll for the trip. ComEd charges about $0.02/kWh for this. Ameren charges $0.025/kWh. Neighborhoods are subsidizing a long-distance grid they aren't using.</p>'''
assert old_toll in src, "toll paragraph not found"
src = src.replace(old_toll, new_toll)
print("[OK] 5/7 orange callout wrapped around toll paragraph")

# Add callout CSS after .problem-sub p rule
callout_css = '''
.callout-orange{
  padding:1.3rem 1.6rem !important;margin:1.2rem 0 !important;border-left:none !important;
  border:1.5px solid var(--sun-2) !important;
  background:linear-gradient(90deg,rgba(255,149,0,0.15),rgba(255,149,0,0.04)) !important;
  box-shadow:0 0 18px rgba(255,149,0,0.35),inset 0 0 24px rgba(255,149,0,0.08) !important;
  color:var(--ink) !important;font-weight:400 !important;position:relative;
}
.callout-orange::before{
  content:"";position:absolute;top:-1px;left:-1px;width:14px;height:14px;
  border-top:2px solid var(--sun-1);border-left:2px solid var(--sun-1);
}
.callout-orange::after{
  content:"";position:absolute;bottom:-1px;right:-1px;width:14px;height:14px;
  border-bottom:2px solid var(--sun-1);border-right:2px solid var(--sun-1);
}
'''
src = src.replace("/* ─── THESIS ─── */", callout_css + "\n/* ─── THESIS ─── */")
print("[OK] callout CSS injected")

# ─── 6. Delete the entire "hardware that could fix this" subsection ───
hardware_block = '''    <div class="problem-sub">
      <h3>The hardware that could fix this is already installed</h3>
      <p>Most neighborhoods are already sitting on thousands of EV batteries capable of acting as a virtual power plant. They're mostly idle. Inverter manufacturers like Enphase, SolarEdge, and Tesla treat the hardware their customers own as proprietary. High-frequency polling triggers rate limits or outright bans. A single policy change from a manufacturer can shut down an entire distributed sensor network overnight.</p>
      <p>Utility data infrastructure has the same problem in reverse. Grid prices update every five minutes. The standard Green Button API delivers 15-minute interval data in trailing 24 to 48 hour batches. You can't balance a real-time grid with two-day-old data, and you can't optimize a home battery without knowing what it costs to discharge it.</p>
    </div>

    '''
assert hardware_block in src, "hardware subsection not found"
src = src.replace(hardware_block, "")
print("[OK] 6/7 hardware subsection deleted")

# ─── 7. Add new 2-sentence intro above "local capital" paragraph ───
old_local = '''<div class="problem-sub">
      <h3>Local capital is leaving the neighborhood</h3>
      <p>A typical Illinois community'''
new_local = '''<div class="problem-sub">
      <h3>Local capital is leaving the neighborhood</h3>
      <p><strong>We put real power in the hands of communities. Every dollar saved by cutting out unnecessary logistics becomes capital a town can reinvest in education, infrastructure, or any other community improvement.</strong></p>
      <p>A typical Illinois community'''
assert old_local in src, "local capital block not found"
src = src.replace(old_local, new_local)
print("[OK] 7/7 community reinvestment intro added")

# ─── 8. Global grid background + dark content panels ───
bg_css = '''
/* ─── GLOBAL SYNTHWAVE BACKGROUND + CONTENT PANELS ─── */
body{
  background:linear-gradient(to bottom,#000 0%,#020a18 20%,#0a1628 40%,#0d1a2d 65%,#020a18 90%,#000 100%);
  position:relative;
}
body::after{
  content:"";position:fixed;bottom:0;left:0;right:0;height:45vh;
  background-image:
    linear-gradient(to right, var(--cyan) 2px, transparent 2px),
    linear-gradient(to bottom, var(--cyan) 2px, transparent 2px);
  background-size:80px 80px;
  transform:perspective(400px) rotateX(70deg);
  transform-origin:50% 100%;
  animation:bg-grid 6s linear infinite;
  filter:drop-shadow(0 0 5px var(--cyan-dim));
  opacity:.5;
  z-index:-1;pointer-events:none;
  mask-image:linear-gradient(to top,black 20%,transparent 85%);
  -webkit-mask-image:linear-gradient(to top,black 20%,transparent 85%);
}
@keyframes bg-grid{0%{background-position:0 0}100%{background-position:0 80px}}

/* Dark semi-transparent content panels for readability over grid */
section.block{
  background:rgba(5,8,14,0.72);
  backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);
  border:1px solid rgba(0,240,255,0.12);
  padding:3rem 3rem 3rem 4rem;border-radius:4px;
  box-shadow:0 4px 30px rgba(0,0,0,0.5);
}
@media(max-width:700px){section.block{padding:2rem 1.4rem}}
'''
# inject right before the closing </style>
src = src.replace("</style>", bg_css + "\n</style>", 1)
print("[OK] 8/? grid background + dark panels injected")

p.write_text(src)
print("\n[DONE] About page fully patched")
