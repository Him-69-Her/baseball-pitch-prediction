#!/usr/bin/env python3
"""Atmospheric wash: full-width horizon glow, shrink sun, drop localized glows."""
from pathlib import Path
import re

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# ────────────────────────────────────────────────────────────
# 1) Replace entire sun CSS block with shrunk sun + atmosphere
# ────────────────────────────────────────────────────────────
old_css_pattern = re.compile(
    r'  /\* Half-sun \u2014 SVG-rendered hero \*/\s*\.sun-wrap\{.*?@keyframes sun-flicker\{.*?\}\s*',
    re.DOTALL
)
match = old_css_pattern.search(src)
assert match, "old sun CSS block not found"

new_css = '''  /* Full-width atmospheric wash \u2014 the sky glowing at the horizon */
  .atmosphere{
    position:absolute;left:0;right:0;bottom:50vh;height:35vh;
    z-index:1;pointer-events:none;
    background:
      radial-gradient(ellipse 50% 70% at 50% 100%,
        rgba(255,204,0,0.4) 0%,
        rgba(255,149,0,0.28) 20%,
        rgba(255,85,0,0.15) 45%,
        transparent 70%),
      linear-gradient(to top,
        rgba(255,149,0,0.3) 0%,
        rgba(255,85,0,0.18) 25%,
        rgba(199,44,0,0.1) 50%,
        rgba(199,44,0,0.04) 75%,
        transparent 100%);
    filter:blur(4px);
    animation:atmos-breathe 8s ease-in-out infinite;
  }
  @keyframes atmos-breathe{
    0%,100%{opacity:.85}
    50%{opacity:1}
  }

  /* Half-sun \u2014 SVG-rendered hero (atmosphere carries the glow) */
  .sun-wrap{
    position:absolute;bottom:50vh;left:50%;
    width:min(520px,48vw);aspect-ratio:2/1;
    z-index:3;pointer-events:none;
    transform:translateX(-50%);
    animation:sun-breathe 5s ease-in-out infinite, sun-flicker 6s infinite;
  }
  .sun-wrap svg{width:100%;height:100%;display:block;overflow:visible;
    filter:drop-shadow(0 0 12px rgba(255,149,0,0.6));}
  @keyframes sun-breathe{
    0%,100%{transform:translateX(-50%) scale(1)}
    50%{transform:translateX(-50%) scale(1.025)}
  }
  @keyframes sun-flicker{
    0%,92%,100%{opacity:1}
    93%{opacity:.88}
    94%{opacity:1}
    95%{opacity:.92}
    96%{opacity:1}
  }
'''
src = src[:match.start()] + new_css + src[match.end():]

# ────────────────────────────────────────────────────────────
# 2) Simplify SVG markup: remove corona, glow, haze divs,
#    keep only the dome itself (atmosphere replaces all of them)
# ────────────────────────────────────────────────────────────
old_markup_pattern = re.compile(
    r'<div class="sun-wrap">\s*<div class="sun-corona"></div>.*?</div>\s*</div>',
    re.DOTALL
)
m2 = old_markup_pattern.search(src)
assert m2, "sun-wrap markup not found"

new_markup = '''<div class="sun-wrap">
    <svg viewBox="0 0 200 100" preserveAspectRatio="xMidYMax meet" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="sunBands" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#fff07a"/>
          <stop offset="15%" stop-color="#ffe54a"/>
          <stop offset="35%" stop-color="#ffcc00"/>
          <stop offset="60%" stop-color="#ff9500"/>
          <stop offset="82%" stop-color="#ff5500"/>
          <stop offset="100%" stop-color="#c72c00"/>
        </linearGradient>
        <clipPath id="domeClip">
          <path d="M 0,100 A 100,100 0 0 1 200,100 Z"/>
        </clipPath>
        <pattern id="sunScan" width="1" height="2" patternUnits="userSpaceOnUse">
          <rect width="1" height="1" fill="rgba(0,0,0,0.2)"/>
        </pattern>
      </defs>
      <g clip-path="url(#domeClip)">
        <rect x="0" y="0" width="200" height="100" fill="url(#sunBands)"/>
        <rect x="0" y="16" width="200" height="2" fill="#000"/>
        <rect x="0" y="32" width="200" height="2.5" fill="#000"/>
        <rect x="0" y="48" width="200" height="3" fill="#000"/>
        <rect x="0" y="64" width="200" height="3.5" fill="#000"/>
        <rect x="0" y="80" width="200" height="4.5" fill="#000"/>
        <rect x="0" y="93" width="200" height="3" fill="#000"/>
        <rect x="0" y="-4" width="200" height="108" fill="url(#sunScan)" opacity="0.4"/>
      </g>
    </svg>
  </div>'''
src = src[:m2.start()] + new_markup + src[m2.end():]

# ────────────────────────────────────────────────────────────
# 3) Add atmosphere div to hero markup (before sun-wrap)
# ────────────────────────────────────────────────────────────
# The hero currently has: sun-wrap, horizon, grid-wrap, grid-mask
# We want atmosphere to come first (lowest z, behind everything)
old_hero = '<section class="hero">\n  <div class="sun-wrap">'
new_hero = '<section class="hero">\n  <div class="atmosphere"></div>\n  <div class="sun-wrap">'
assert old_hero in src, "hero opening not found"
src = src.replace(old_hero, new_hero)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] atmospheric wash added, sun shrunk, localized glows removed")
