#!/usr/bin/env python3
"""Fix the sun: proper half-dome sitting on horizon line."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

old = '''  .sun{
    position:absolute;bottom:50vh;left:50%;transform:translateX(-50%);
    width:min(640px,72vw);aspect-ratio:1/1;
    /* clip off the bottom half so only the top arc shows above horizon */
    clip-path:inset(0 0 50% 0);
    z-index:3;'''
new = '''  .sun{
    position:absolute;bottom:50vh;left:50%;transform:translateX(-50%);
    width:min(560px,55vw);height:min(280px,27.5vw);
    /* half-dome: flat bottom sits on horizon, curved top rises */
    border-radius:999px 999px 0 0;
    overflow:hidden;
    z-index:3;'''
assert old in src, "broken sun block not found"
src = src.replace(old, new)

# Also remove aspect-ratio from sun since we now set explicit width+height.
# Also remove filter drop-shadows that are now clipping weird with overflow:hidden
# by moving the glow to the element itself via box-shadow.
old_pulse = '''  @keyframes sun-pulse{
    0%,100%{filter:drop-shadow(0 0 40px var(--sun-2)) drop-shadow(0 0 80px var(--sun-3))}
    50%{filter:drop-shadow(0 0 60px var(--sun-1)) drop-shadow(0 0 120px var(--sun-2))}
  }'''
new_pulse = '''  @keyframes sun-pulse{
    0%,100%{box-shadow:0 0 40px var(--sun-2), 0 0 90px var(--sun-3), 0 -20px 60px var(--sun-2)}
    50%{box-shadow:0 0 60px var(--sun-1), 0 0 130px var(--sun-2), 0 -30px 80px var(--sun-1)}
  }'''
assert old_pulse in src, "sun-pulse keyframes not found"
src = src.replace(old_pulse, new_pulse)

# Strip the filter line from the sun rule since we moved glow to box-shadow
old_filter = '''    filter:drop-shadow(0 0 40px var(--sun-2)) drop-shadow(0 0 80px var(--sun-3));
    animation:sun-pulse 4s ease-in-out infinite;'''
new_filter = '''    box-shadow:0 0 40px var(--sun-2), 0 0 90px var(--sun-3), 0 -20px 60px var(--sun-2);
    animation:sun-pulse 4s ease-in-out infinite;'''
assert old_filter in src, "sun filter line not found"
src = src.replace(old_filter, new_filter)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] sun reshaped to half-dome sitting on horizon")
