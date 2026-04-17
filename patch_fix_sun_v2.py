#!/usr/bin/env python3
"""Proper half-sun: full circle, clip bottom half, remap gradient."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Fix the sun shape: full circle, clip bottom half, position flat edge on horizon
old_shape = '''  .sun{
    position:absolute;bottom:50vh;left:50%;transform:translateX(-50%);
    width:min(560px,55vw);height:min(280px,27.5vw);
    /* half-dome: flat bottom sits on horizon, curved top rises */
    border-radius:999px 999px 0 0;
    overflow:hidden;
    z-index:3;'''
new_shape = '''  .sun{
    position:absolute;bottom:50vh;left:50%;
    width:min(560px,55vw);aspect-ratio:1/1;
    transform:translate(-50%, 50%);
    border-radius:50%;
    clip-path:inset(0 0 50% 0);
    z-index:3;'''
assert old_shape in src, "sun shape block not found"
src = src.replace(old_shape, new_shape)

# 2) Remap gradient: compress all bands into top 50% of circle
#    so the full color range (yellow -> deep red) is visible in the dome
old_gradient = '''    background:linear-gradient(
      to bottom,
      var(--sun-1) 0%, var(--sun-1) 18%,
      transparent 18%, transparent 22%,
      var(--sun-2) 22%, var(--sun-2) 38%,
      transparent 38%, transparent 43%,
      var(--sun-2) 43%, var(--sun-2) 56%,
      transparent 56%, transparent 62%,
      var(--sun-3) 62%, var(--sun-3) 74%,
      transparent 74%, transparent 80%,
      var(--sun-3) 80%, var(--sun-3) 90%,
      transparent 90%, transparent 94%,
      var(--sun-4) 94%, var(--sun-4) 100%
    );'''
new_gradient = '''    background:linear-gradient(
      to bottom,
      var(--sun-1) 0%, var(--sun-1) 9%,
      transparent 9%, transparent 11%,
      var(--sun-2) 11%, var(--sun-2) 19%,
      transparent 19%, transparent 22%,
      var(--sun-2) 22%, var(--sun-2) 28%,
      transparent 28%, transparent 31%,
      var(--sun-3) 31%, var(--sun-3) 37%,
      transparent 37%, transparent 40%,
      var(--sun-3) 40%, var(--sun-3) 45%,
      transparent 45%, transparent 47%,
      var(--sun-4) 47%, var(--sun-4) 50%,
      transparent 50%
    );'''
assert old_gradient in src, "sun gradient not found"
src = src.replace(old_gradient, new_gradient)

# 3) Switch glow from box-shadow to drop-shadow (works with clip-path)
old_shadow = '''    box-shadow:0 0 40px var(--sun-2), 0 0 90px var(--sun-3), 0 -20px 60px var(--sun-2);
    animation:sun-pulse 4s ease-in-out infinite;'''
new_shadow = '''    filter:drop-shadow(0 -10px 40px var(--sun-2)) drop-shadow(0 -20px 80px var(--sun-3));
    animation:sun-pulse 4s ease-in-out infinite;'''
assert old_shadow in src, "sun shadow not found"
src = src.replace(old_shadow, new_shadow)

# 4) Update pulse keyframes to use filter instead of box-shadow
old_pulse = '''  @keyframes sun-pulse{
    0%,100%{box-shadow:0 0 40px var(--sun-2), 0 0 90px var(--sun-3), 0 -20px 60px var(--sun-2)}
    50%{box-shadow:0 0 60px var(--sun-1), 0 0 130px var(--sun-2), 0 -30px 80px var(--sun-1)}
  }'''
new_pulse = '''  @keyframes sun-pulse{
    0%,100%{filter:drop-shadow(0 -10px 40px var(--sun-2)) drop-shadow(0 -20px 80px var(--sun-3))}
    50%{filter:drop-shadow(0 -15px 60px var(--sun-1)) drop-shadow(0 -25px 120px var(--sun-2))}
  }'''
assert old_pulse in src, "sun-pulse not found"
src = src.replace(old_pulse, new_pulse)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] half-sun with remapped gradient")
