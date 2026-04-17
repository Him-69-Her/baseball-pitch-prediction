#!/usr/bin/env python3
"""Hero minimalism: sun + wordmark + visible grid only."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Strip tagline, subline, and cta-row from hero markup
old_hero_inner = '''  <div class="hero-content">
    <h1 class="wordmark">TINY&nbsp;HUB&nbsp;NETWORK</h1>
    <div class="tagline">// Peer · to · Peer · Energy · Grid //</div>
    <p class="subline">
      A physics-aware, deterministic matching engine for neighborhood electricity.
      Solar producers trade directly with nearby consumers. Settled on-chain. Delivered over real wire.
    </p>
    <div class="cta-row">
      <a href="/dashboard" class="btn primary">Launch Live Demo →</a>
      <a href="#thesis" class="btn">Investor Brief</a>
    </div>
  </div>'''
new_hero_inner = '''  <div class="hero-content">
    <h1 class="wordmark">TINY&nbsp;HUB&nbsp;NETWORK</h1>
  </div>'''
assert old_hero_inner in src, "hero-inner markup not found"
src = src.replace(old_hero_inner, new_hero_inner)

# 2) Fix the grid so it's actually visible:
#    - Use a 2D CSS transform (translateX only) for container; do perspective inside
#    - Anchor grid so lines start below horizon, not behind sun
#    - Much brighter cyan at baseline; glowing but not washed out
old_grid_css = '''  .grid-floor{
    position:absolute;bottom:0;left:50%;transform:translateX(-50%);
    width:300vw;height:45vh;
    background-image:
      linear-gradient(to right, rgba(0,240,255,0.55) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(0,240,255,0.55) 1px, transparent 1px);
    background-size:90px 90px;
    transform:perspective(340px) rotateX(62deg) translateZ(0);
    transform-origin:center bottom;
    animation:grid-scroll 9s linear infinite;
    filter:drop-shadow(0 0 4px var(--cyan-dim));
    opacity:.75;
  }
  @keyframes grid-scroll{
    0%{background-position:0 0}
    100%{background-position:0 90px}
  }
  /* fade grid top into horizon */
  .grid-mask{
    position:absolute;bottom:0;left:0;right:0;height:45vh;pointer-events:none;
    background:linear-gradient(to top,transparent 55%, #000 100%);
  }
  /* Horizon line */
  .horizon{
    position:absolute;bottom:45vh;left:0;right:0;height:1px;
    background:linear-gradient(to right, transparent, var(--cyan) 30%, var(--cyan) 70%, transparent);
    box-shadow:0 0 10px var(--cyan), 0 0 24px var(--cyan-dim);
    z-index:2;
  }'''
new_grid_css = '''  /* Perspective wrapper keeps the grid pinned to the bottom */
  .grid-wrap{
    position:absolute;bottom:0;left:0;right:0;height:50vh;
    perspective:400px;perspective-origin:50% 0%;
    z-index:2;pointer-events:none;
    overflow:hidden;
  }
  .grid-floor{
    position:absolute;bottom:0;left:-50%;width:200%;height:100%;
    background-image:
      linear-gradient(to right, var(--cyan) 2px, transparent 2px),
      linear-gradient(to bottom, var(--cyan) 2px, transparent 2px);
    background-size:80px 80px;
    background-position:0 0;
    transform:rotateX(70deg);
    transform-origin:50% 100%;
    animation:grid-scroll 6s linear infinite;
    filter:drop-shadow(0 0 6px var(--cyan)) drop-shadow(0 0 14px var(--cyan-dim));
    opacity:.95;
  }
  @keyframes grid-scroll{
    0%{background-position:0 0}
    100%{background-position:0 80px}
  }
  /* Fade the far end of the grid into black (horizon haze) */
  .grid-mask{
    position:absolute;bottom:0;left:0;right:0;height:50vh;pointer-events:none;z-index:3;
    background:linear-gradient(to top, transparent 0%, transparent 30%, rgba(0,0,0,0.55) 70%, #000 100%);
  }
  /* Neon horizon line sitting on top of the grid */
  .horizon{
    position:absolute;bottom:50vh;left:0;right:0;height:2px;z-index:4;
    background:linear-gradient(to right, transparent, var(--cyan) 15%, var(--cyan) 85%, transparent);
    box-shadow:0 0 12px var(--cyan), 0 0 32px var(--cyan), 0 0 60px var(--cyan-dim);
  }'''
assert old_grid_css in src, "grid CSS block not found"
src = src.replace(old_grid_css, new_grid_css)

# 3) Update hero markup: wrap grid-floor in grid-wrap
old_grid_markup = '''<section class="hero">
  <div class="sun"></div>
  <div class="horizon"></div>
  <div class="grid-floor"></div>
  <div class="grid-mask"></div>'''
new_grid_markup = '''<section class="hero">
  <div class="sun"></div>
  <div class="horizon"></div>
  <div class="grid-wrap"><div class="grid-floor"></div></div>
  <div class="grid-mask"></div>'''
assert old_grid_markup in src, "grid markup not found"
src = src.replace(old_grid_markup, new_grid_markup)

# 4) Pull the sun up a touch so full circle sits above horizon
old_sun = '''  .sun{
    position:absolute;top:14%;left:50%;transform:translateX(-50%);
    width:min(460px,62vw);aspect-ratio:1/1;
    z-index:3;'''
new_sun = '''  .sun{
    position:absolute;top:10%;left:50%;transform:translateX(-50%);
    width:min(420px,52vw);aspect-ratio:1/1;
    z-index:3;'''
assert old_sun in src, "sun block not found"
src = src.replace(old_sun, new_sun)

# 5) Reposition hero-content so wordmark sits between sun and horizon
old_hero_content = '''  .hero{
    justify-content:flex-end;
  }
  .hero-content{
    position:relative;z-index:5;text-align:center;
    padding-bottom:min(18vh,14rem);
    /* sits below the sun, above the grid horizon */
  }'''
new_hero_content = '''  .hero{
    justify-content:center;
  }
  .hero-content{
    position:relative;z-index:5;text-align:center;
    margin-top:auto;margin-bottom:calc(50vh + 2rem);
  }'''
assert old_hero_content in src, "hero-content block not found"
src = src.replace(old_hero_content, new_hero_content)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] landing.html v3 applied")
