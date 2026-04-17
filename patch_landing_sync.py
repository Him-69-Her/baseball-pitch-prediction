#!/usr/bin/env python3
"""Sync landing page with about page: Orbitron font, stars, pink grid glow."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Swap Monoton for Orbitron in Google Fonts import
src = src.replace(
    "family=Monoton&",
    "family=Orbitron:wght@400;500;600;700;800;900&"
)

# 2) Replace all Monoton font-family references
src = src.replace("'Monoton',cursive", "'Orbitron',sans-serif")

# 3) Add stars CSS before the sun-wrap CSS
stars_css = '''  /* Stars */
  .stars{
    position:absolute;inset:0;z-index:0;pointer-events:none;
    background:
      radial-gradient(1px 1px at 10% 15%, #fff 50%, transparent 100%),
      radial-gradient(1px 1px at 25% 8%, rgba(255,255,255,0.8) 50%, transparent 100%),
      radial-gradient(1.5px 1.5px at 40% 22%, #fff 50%, transparent 100%),
      radial-gradient(1px 1px at 55% 5%, rgba(255,255,255,0.7) 50%, transparent 100%),
      radial-gradient(1px 1px at 70% 18%, #fff 50%, transparent 100%),
      radial-gradient(1.5px 1.5px at 85% 12%, rgba(255,255,255,0.9) 50%, transparent 100%),
      radial-gradient(1px 1px at 15% 35%, rgba(255,255,255,0.6) 50%, transparent 100%),
      radial-gradient(1px 1px at 30% 28%, #fff 50%, transparent 100%),
      radial-gradient(1.5px 1.5px at 50% 32%, rgba(255,255,255,0.8) 50%, transparent 100%),
      radial-gradient(1px 1px at 65% 25%, rgba(255,255,255,0.7) 50%, transparent 100%),
      radial-gradient(1px 1px at 80% 30%, #fff 50%, transparent 100%),
      radial-gradient(1px 1px at 92% 20%, rgba(255,255,255,0.6) 50%, transparent 100%),
      radial-gradient(1px 1px at 5% 10%, rgba(255,255,255,0.5) 50%, transparent 100%),
      radial-gradient(2px 2px at 48% 12%, rgba(255,255,255,0.9) 50%, transparent 100%),
      radial-gradient(1px 1px at 35% 42%, rgba(255,255,255,0.5) 50%, transparent 100%),
      radial-gradient(1px 1px at 72% 38%, rgba(255,255,255,0.7) 50%, transparent 100%),
      radial-gradient(1.5px 1.5px at 18% 45%, rgba(255,255,255,0.6) 50%, transparent 100%),
      radial-gradient(1px 1px at 88% 8%, #fff 50%, transparent 100%),
      radial-gradient(1px 1px at 95% 35%, rgba(255,255,255,0.5) 50%, transparent 100%),
      radial-gradient(1px 1px at 3% 25%, rgba(255,255,255,0.8) 50%, transparent 100%),
      radial-gradient(1.5px 1.5px at 60% 10%, rgba(255,255,255,0.7) 50%, transparent 100%),
      radial-gradient(1px 1px at 45% 40%, rgba(255,255,255,0.4) 50%, transparent 100%);
    animation:twinkle 4s ease-in-out infinite alternate;
  }
  @keyframes twinkle{0%{opacity:.8}100%{opacity:1}}

'''

# Insert stars CSS before the atmosphere CSS
assert '.atmosphere{' in src, "atmosphere CSS not found"
src = src.replace('  .atmosphere{', stars_css + '  .atmosphere{')

# 4) Add grid-glow CSS after grid-mask CSS
grid_glow_css = '''
  /* Pink/magenta overlay fading from horizon into cyan grid */
  .grid-glow{
    position:absolute;bottom:0;left:0;right:0;height:50vh;z-index:2;pointer-events:none;
    background:linear-gradient(to bottom,
      rgba(255,45,149,0.45) 0%,
      rgba(255,45,149,0.28) 15%,
      rgba(180,30,120,0.15) 35%,
      rgba(100,20,80,0.06) 55%,
      transparent 75%);
  }
'''
# Find the grid-mask closing brace area and insert after it
assert '.grid-mask{' in src, "grid-mask CSS not found"
# Insert grid-glow CSS right after the grid-mask rule
import re
mask_match = re.search(r'\.grid-mask\{[^}]+\}', src)
assert mask_match, "grid-mask rule not found"
insert_pos = mask_match.end()
src = src[:insert_pos] + grid_glow_css + src[insert_pos:]

# 5) Add stars div to hero HTML (before atmosphere div)
assert '<div class="atmosphere"></div>' in src, "atmosphere div not found"
src = src.replace(
    '<div class="atmosphere"></div>',
    '<div class="stars"></div>\n  <div class="atmosphere"></div>'
)

# 6) Add grid-glow div to hero HTML (after grid-wrap, before grid-mask)
assert '<div class="grid-mask"></div>' in src, "grid-mask div not found"
src = src.replace(
    '<div class="grid-mask"></div>',
    '<div class="grid-glow"></div>\n  <div class="grid-mask"></div>'
)

# 7) Clean up any remaining Monoton comments
src = src.replace('Monoton', 'Orbitron')

assert src != orig, "No changes applied"
f.write_text(src)
print(f"[OK] landing.html synced ({len(src)} bytes)")
print(f"  - Font: Orbitron")
print(f"  - Stars: added")
print(f"  - Grid glow: added")
