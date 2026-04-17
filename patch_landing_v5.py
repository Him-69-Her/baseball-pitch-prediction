#!/usr/bin/env python3
"""Move wordmark into the space between horizon and grid."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

old = '''  .hero{
    justify-content:center;
  }
  .hero-content{
    position:relative;z-index:5;text-align:center;
    margin-top:auto;margin-bottom:calc(50vh + 2rem);
  }'''
new = '''  .hero{
    justify-content:flex-end;
  }
  .hero-content{
    position:relative;z-index:6;text-align:center;
    /* sits in the dark band just below the horizon line */
    margin-bottom:calc(50vh - 5rem);
  }'''
assert old in src, "hero-content block not found"
src = src.replace(old, new)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] wordmark repositioned")
