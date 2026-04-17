#!/usr/bin/env python3
"""Wider, more animated, richer SVG half-sun with layered glows."""
from pathlib import Path
import re

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# ────────────────────────────────────────────────────────────
# 1) Replace entire .sun-wrap CSS block + sun-pulse keyframes
# ────────────────────────────────────────────────────────────
old_css_pattern = re.compile(
    r'  /\* Half-sun \u2014 SVG-rendered hero \*/\s*\.sun-wrap\{.*?@keyframes sun-pulse\{.*?\}\s*',
    re.DOTALL
)
match = old_css_pattern.search(src)
assert match, "old sun CSS block not found"

new_css = '''  /* Half-sun \u2014 SVG-rendered hero */
  .sun-wrap{
    position:absolute;bottom:50vh;left:50%;
    width:min(820px,72vw);aspect-ratio:2.4/1;
    z-index:3;pointer-events:none;
    transform:translateX(-50%);
    animation:sun-breathe 5s ease-in-out infinite, sun-flicker 6s infinite;
  }
  .sun-wrap svg{width:100%;height:100%;display:block;overflow:visible;
    filter:drop-shadow(0 0 20px rgba(255,149,0,0.6));}
  .sun-glow{
    position:absolute;inset:-80% -40% -20% -40%;
    background:radial-gradient(ellipse at 50% 100%,
      rgba(255,204,0,0.55) 0%,
      rgba(255,149,0,0.4) 15%,
      rgba(255,85,0,0.2) 35%,
      transparent 65%);
    filter:blur(16px);z-index:-1;pointer-events:none;
    animation:sun-glow-pulse 4s ease-in-out infinite;
  }
  .sun-corona{
    position:absolute;inset:-100% -50% -10% -50%;
    background:radial-gradient(ellipse at 50% 100%,
      rgba(255,45,149,0.18) 0%,
      rgba(255,85,0,0.15) 30%,
      transparent 70%);
    filter:blur(24px);z-index:-2;pointer-events:none;
    animation:sun-corona-pulse 7s ease-in-out infinite;
  }
  .sun-haze{
    position:absolute;bottom:0;left:-20%;right:-20%;height:30%;
    background:linear-gradient(to top,
      rgba(255,149,0,0.4) 0%,
      rgba(255,85,0,0.2) 50%,
      transparent 100%);
    filter:blur(8px);z-index:2;pointer-events:none;
    animation:sun-haze-shimmer 3s ease-in-out infinite;
  }
  @keyframes sun-breathe{
    0%,100%{transform:translateX(-50%) scale(1)}
    50%{transform:translateX(-50%) scale(1.025)}
  }
  @keyframes sun-glow-pulse{
    0%,100%{opacity:.75;transform:scale(1)}
    50%{opacity:1;transform:scale(1.08)}
  }
  @keyframes sun-corona-pulse{
    0%,100%{opacity:.5}
    50%{opacity:.9}
  }
  @keyframes sun-haze-shimmer{
    0%,100%{transform:scaleX(1) scaleY(1);opacity:.8}
    50%{transform:scaleX(1.05) scaleY(1.1);opacity:1}
  }
  @keyframes sun-flicker{
    0%,92%,100%{opacity:1}
    93%{opacity:.85}
    94%{opacity:1}
    95%{opacity:.9}
    96%{opacity:1}
  }
'''
src = src[:match.start()] + new_css + src[match.end():]

# ────────────────────────────────────────────────────────────
# 2) Replace the SVG markup block with the richer version
# ────────────────────────────────────────────────────────────
old_markup_pattern = re.compile(
    r'<div class="sun-wrap">\s*<div class="sun-glow"></div>.*?</div>',
    re.DOTALL
)
m2 = old_markup_pattern.search(src)
assert m2, "sun-wrap markup not found"

new_markup = '''<div class="sun-wrap">
    <div class="sun-corona"></div>
    <div class="sun-glow"></div>
    <svg viewBox="0 0 240 100" preserveAspectRatio="xMidYMax meet" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
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
          <path d="M 0,100 A 120,100 0 0 1 240,100 Z"/>
        </clipPath>
        <pattern id="sunScan" width="1" height="2" patternUnits="userSpaceOnUse">
          <rect width="1" height="1" fill="rgba(0,0,0,0.2)"/>
        </pattern>
        <radialGradient id="sunHighlight" cx="50%" cy="100%" r="50%">
          <stop offset="0%" stop-color="rgba(255,255,255,0.15)"/>
          <stop offset="50%" stop-color="rgba(255,255,255,0.05)"/>
          <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
        </radialGradient>
      </defs>
      <g clip-path="url(#domeClip)">
        <rect x="0" y="0" width="240" height="100" fill="url(#sunBands)"/>
        <rect x="0" y="16" width="240" height="2" fill="#000"/>
        <rect x="0" y="32" width="240" height="2.5" fill="#000"/>
        <rect x="0" y="48" width="240" height="3" fill="#000"/>
        <rect x="0" y="64" width="240" height="3.5" fill="#000"/>
        <rect x="0" y="80" width="240" height="4.5" fill="#000"/>
        <rect x="0" y="93" width="240" height="3" fill="#000"/>
        <ellipse cx="120" cy="100" rx="100" ry="80" fill="url(#sunHighlight)"/>
        <rect x="0" y="-4" width="240" height="108" fill="url(#sunScan)" opacity="0.4"/>
      </g>
    </svg>
    <div class="sun-haze"></div>
  </div>'''
src = src[:m2.start()] + new_markup + src[m2.end():]

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] sun upgraded: wider, layered glows, breathing + flicker animations")
