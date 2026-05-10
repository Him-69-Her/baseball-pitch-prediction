#!/usr/bin/env python3
"""Fix: sun back above horizon, wordmark below horizon, rename to Energy."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Revert hero to center justification (sun sits up top via its own top:10%)
old_hero = '''  .hero{
    justify-content:flex-end;
  }
  .hero-content{
    position:relative;z-index:6;text-align:center;
    /* sits in the dark band just below the horizon line */
    margin-bottom:calc(50vh - 5rem);
  }'''
new_hero = '''  .hero{
    justify-content:flex-start;
    padding:0;
  }
  /* Position the wordmark absolutely in the dark band between
     the horizon line (bottom:50vh) and the visible grid start */
  .hero-content{
    position:absolute;left:50%;transform:translateX(-50%);
    top:calc(100vh - 50vh - 5.5rem);
    z-index:6;text-align:center;
    width:100%;
  }'''
assert old_hero in src, "hero block not found"
src = src.replace(old_hero, new_hero)

# 2) Rename wordmark
old_wm = '<h1 class="wordmark">TINY&nbsp;HUB&nbsp;NETWORK</h1>'
new_wm = '<h1 class="wordmark">TINY&nbsp;HUB&nbsp;ENERGY</h1>'
assert old_wm in src, "wordmark not found"
src = src.replace(old_wm, new_wm)

# 3) Update page <title> too
old_title = '<title>TINY-HUB NETWORK // Peer-to-Peer Energy Grid</title>'
new_title = '<title>TINY-HUB ENERGY // Peer-to-Peer Energy Grid</title>'
assert old_title in src, "page title not found"
src = src.replace(old_title, new_title)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] wordmark repositioned below horizon, renamed to ENERGY")
