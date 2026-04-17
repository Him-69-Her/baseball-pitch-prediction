#!/usr/bin/env python3
"""Replace CSS sun with SVG half-sun: no box, real bands, atmospheric glow."""
from pathlib import Path
import re

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# ────────────────────────────────────────────────────────────
# 1) Replace the entire .sun CSS rule + gradient + keyframes
#    with a new block for .sun-wrap / .sun-glow / .sun-haze
# ────────────────────────────────────────────────────────────
# Find and delete the old .sun{...} rule (from "/* Banded sun */" through the closing brace of sun-pulse)
# We'll pattern-match with regex to be robust.

old_sun_block_pattern = re.compile(
    r'  /\* Banded sun \u2014 the hero \*/\s*\.sun\{.*?\}\s*@keyframes sun-pulse\{.*?\}\s*',
    re.DOTALL
)
match = old_sun_block_pattern.search(src)
assert match, "old sun CSS block not found"

new_sun_css = '''  /* Half-sun — SVG-rendered hero */
  .sun-wrap{
    position:absolute;bottom:50vh;left:50%;transform:translateX(-50%);
    width:min(560px,55vw);aspect-ratio:2/1;
    z-index:3;pointer-events:none;
  }
  .sun-wrap svg{width:100%;height:100%;display:block;overflow:visible}
  .sun-glow{
    position:absolute;inset:-60% -30% 0 -30%;
    background:radial-gradient(ellipse at 50% 100%,
      rgba(255,149,0,0.55) 0%,
      rgba(255,85,0,0.25) 25%,
      transparent 60%);
    filter:blur(10px);z-index:-1;pointer-events:none;
    animation:sun-pulse 4s ease-in-out infinite;
  }
  .sun-haze{
    position:absolute;bottom:-2px;left:-15%;right:-15%;height:40%;
    background:linear-gradient(to top,rgba(255,149,0,0.35),transparent);
    filter:blur(8px);z-index:2;pointer-events:none;
  }
  @keyframes sun-pulse{
    0%,100%{opacity:.85;transform:scale(1)}
    50%{opacity:1;transform:scale(1.03)}
  }
'''
src = src[:match.start()] + new_sun_css + src[match.end():]

# ────────────────────────────────────────────────────────────
# 2) Replace the <div class="sun"></div> markup with the SVG sun
# ────────────────────────────────────────────────────────────
old_markup = '<div class="sun"></div>'
new_markup = '''<div class="sun-wrap">
    <div class="sun-glow"></div>
    <svg viewBox="0 0 200 100" preserveAspectRatio="xMidYMax meet" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="sunBands" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ffe54a"/>
          <stop offset="30%" stop-color="#ffcc00"/>
          <stop offset="60%" stop-color="#ff9500"/>
          <stop offset="85%" stop-color="#ff5500"/>
          <stop offset="100%" stop-color="#c72c00"/>
        </linearGradient>
        <clipPath id="domeClip">
          <path d="M 0,100 A 100,100 0 0 1 200,100 Z"/>
        </clipPath>
        <pattern id="sunScan" width="1" height="2" patternUnits="userSpaceOnUse">
          <rect width="1" height="1" fill="rgba(0,0,0,0.18)"/>
        </pattern>
      </defs>
      <g clip-path="url(#domeClip)">
        <rect x="0" y="0" width="200" height="100" fill="url(#sunBands)"/>
        <rect x="0" y="18" width="200" height="2.5" fill="#000"/>
        <rect x="0" y="36" width="200" height="2.5" fill="#000"/>
        <rect x="0" y="52" width="200" height="3" fill="#000"/>
        <rect x="0" y="68" width="200" height="3.5" fill="#000"/>
        <rect x="0" y="84" width="200" height="4" fill="#000"/>
        <rect x="0" y="0" width="200" height="100" fill="url(#sunScan)" opacity="0.35"/>
      </g>
    </svg>
    <div class="sun-haze"></div>
  </div>'''
assert old_markup in src, "<div class='sun'></div> markup not found"
src = src.replace(old_markup, new_markup)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] CSS sun replaced with SVG half-sun")
