#!/usr/bin/env python3
"""Combined fix: sun sits on horizon, wordmark sits below horizon."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Anchor sun from bottom so it sits ON the horizon line (horizon is at bottom:50vh)
old_sun = '''  .sun{
    position:absolute;top:10%;left:50%;transform:translateX(-50%);
    width:min(420px,52vw);aspect-ratio:1/1;
    z-index:3;'''
new_sun = '''  .sun{
    position:absolute;bottom:48vh;left:50%;transform:translateX(-50%);
    width:min(420px,52vw);aspect-ratio:1/1;
    z-index:3;'''
assert old_sun in src, "sun block not found"
src = src.replace(old_sun, new_sun)

# 2) Anchor wordmark from bottom so it sits clearly BELOW the horizon line
old_wm = '''  /* Position the wordmark absolutely in the dark band between
     the horizon line (bottom:50vh) and the visible grid start */
  .hero-content{
    position:absolute;left:50%;transform:translateX(-50%);
    top:calc(100vh - 50vh - 5.5rem);
    z-index:6;text-align:center;
    width:100%;
  }'''
new_wm = '''  /* Position wordmark BELOW horizon, in dark band above grid */
  .hero-content{
    position:absolute;left:50%;
    bottom:34vh;
    transform:translateX(-50%);
    z-index:6;text-align:center;
    width:100%;
  }'''
assert old_wm in src, "hero-content block not found"
src = src.replace(old_wm, new_wm)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] sun + wordmark repositioned")
