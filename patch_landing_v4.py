#!/usr/bin/env python3
"""Rename nav: six-item header."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

old_nav = '''  <ul class="nav-links">
    <li><a href="#how">Protocol</a></li>
    <li><a href="#thesis">Thesis</a></li>
    <li><a href="#pilot">Pilot</a></li>
    <li><a href="/dashboard">Demo \u2192</a></li>
  </ul>'''
new_nav = '''  <ul class="nav-links">
    <li><a href="#about">About</a></li>
    <li><a href="#how">How It Works</a></li>
    <li><a href="#suppliers">Clean Energy Suppliers</a></li>
    <li><a href="#consumers">Energy Consumers</a></li>
    <li><a href="#investors">Investors</a></li>
    <li><a href="/dashboard">Live Demo \u2192</a></li>
  </ul>'''
assert old_nav in src, "nav block not found"
src = src.replace(old_nav, new_nav)

# Nav is now long \u2014 tighten the gap between links so it fits
old_nav_css = '.nav-links{display:flex;gap:2rem;list-style:none}'
new_nav_css = '.nav-links{display:flex;gap:1.4rem;list-style:none;flex-wrap:wrap;justify-content:flex-end}'
assert old_nav_css in src, "nav-links css not found"
src = src.replace(old_nav_css, new_nav_css)

# Shrink link font a touch so six items fit cleanly
old_link_css = '''  .nav-links a{
    color:var(--cyan);text-decoration:none;font-size:.75rem;letter-spacing:.2em;
    text-transform:uppercase;transition:all .2s;
    text-shadow:0 0 4px var(--cyan-dim);
  }'''
new_link_css = '''  .nav-links a{
    color:var(--cyan);text-decoration:none;font-size:.7rem;letter-spacing:.18em;
    text-transform:uppercase;transition:all .2s;
    text-shadow:0 0 4px var(--cyan-dim);white-space:nowrap;
  }'''
assert old_link_css in src, "nav link css not found"
src = src.replace(old_link_css, new_link_css)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] nav renamed to 6 items")
