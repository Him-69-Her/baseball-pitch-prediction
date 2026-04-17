#!/usr/bin/env python3
"""Refine landing.html: sun-hero layout, subtler grid, no VHS noise."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# 1) Remove VHS noise: body::after block
old_noise = '''  /* VHS noise */
  body::after{
    content:"";position:fixed;inset:0;pointer-events:none;z-index:998;opacity:.06;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.9'/></svg>");
    animation:noise 0.5s steps(2) infinite;
  }
  @keyframes noise{
    0%{transform:translate(0,0)}25%{transform:translate(-1%,1%)}50%{transform:translate(1%,-1%)}75%{transform:translate(-1%,-1%)}100%{transform:translate(1%,1%)}
  }
'''
new_noise = '''  /* (VHS noise removed for cleaner texture) */
'''
assert old_noise in src, "VHS noise block not found"
src = src.replace(old_noise, new_noise)

# 2) Slow the grid scroll: 3s -> 8s, lower opacity
old_grid = '''  .grid-floor{
    position:absolute;bottom:0;left:50%;transform:translateX(-50%);
    width:300vw;height:60vh;
    background-image:
      linear-gradient(to right, var(--cyan) 1px, transparent 1px),
      linear-gradient(to bottom, var(--cyan) 1px, transparent 1px);
    background-size:80px 80px;
    transform:perspective(300px) rotateX(60deg) translateZ(0);
    transform-origin:center bottom;
    animation:grid-scroll 3s linear infinite;
    box-shadow:0 0 60px var(--cyan) inset;
    filter:drop-shadow(0 0 6px var(--cyan));
  }
  @keyframes grid-scroll{
    0%{background-position:0 0}
    100%{background-position:0 80px}
  }
  /* fade grid top */
  .grid-mask{
    position:absolute;bottom:0;left:0;right:0;height:60vh;pointer-events:none;
    background:linear-gradient(to top,transparent 40%, #000 100%);
  }'''
new_grid = '''  .grid-floor{
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
assert old_grid in src, "grid-floor block not found"
src = src.replace(old_grid, new_grid)

# 3) Sun becomes hero: bigger, top-center, full visibility
old_sun = '''  /* Banded sun */
  .sun{
    position:absolute;top:20%;left:50%;transform:translateX(-50%);
    width:min(520px,70vw);aspect-ratio:1/1;'''
new_sun = '''  /* Banded sun \u2014 the hero */
  .sun{
    position:absolute;top:14%;left:50%;transform:translateX(-50%);
    width:min(460px,62vw);aspect-ratio:1/1;
    z-index:3;'''
assert old_sun in src, "sun block not found"
src = src.replace(old_sun, new_sun)

# 4) Hero content: move below sun, smaller wordmark, clean stacking
old_hero_content = '''  .hero-content{
    position:relative;z-index:5;text-align:center;padding-bottom:8vh;
  }
  .wordmark{
    font-family:'Monoton',cursive;
    font-size:clamp(2.8rem,9vw,7rem);
    letter-spacing:.08em;line-height:.95;
    background:linear-gradient(to bottom,var(--sun-1) 0%,var(--sun-2) 50%,var(--sun-3) 100%);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 20px var(--sun-2));
    animation:flicker 4s infinite;
  }'''
new_hero_content = '''  .hero{
    justify-content:flex-end;
  }
  .hero-content{
    position:relative;z-index:5;text-align:center;
    padding-bottom:min(18vh,14rem);
    /* sits below the sun, above the grid horizon */
  }
  .wordmark{
    font-family:'Monoton',cursive;
    font-size:clamp(1.8rem,5.2vw,4rem);
    letter-spacing:.14em;line-height:1;
    color:var(--sun-1);
    text-shadow:
      0 0 12px var(--sun-2),
      0 0 28px var(--sun-3),
      0 2px 0 rgba(0,0,0,0.6);
    animation:flicker 5s infinite;
    white-space:nowrap;
  }'''
assert old_hero_content in src, "hero-content block not found"
src = src.replace(old_hero_content, new_hero_content)

# 5) Wordmark HTML: single line, no <br>
old_wm_html = '<h1 class="wordmark">TINY HUB<br>NETWORK</h1>'
new_wm_html = '<h1 class="wordmark">TINY&nbsp;HUB&nbsp;NETWORK</h1>'
assert old_wm_html in src, "wordmark html not found"
src = src.replace(old_wm_html, new_wm_html)

# 6) Inject horizon element into hero markup
old_hero_markup = '''<section class="hero">
  <div class="sun"></div>
  <div class="grid-floor"></div>
  <div class="grid-mask"></div>'''
new_hero_markup = '''<section class="hero">
  <div class="sun"></div>
  <div class="horizon"></div>
  <div class="grid-floor"></div>
  <div class="grid-mask"></div>'''
assert old_hero_markup in src, "hero markup not found"
src = src.replace(old_hero_markup, new_hero_markup)

# 7) Tighten tagline margin (since it sits right under wordmark)
old_tagline = '''  .tagline{
    margin-top:1.2rem;font-size:clamp(.72rem,1.2vw,.95rem);letter-spacing:.35em;
    color:var(--cyan);text-transform:uppercase;
    text-shadow:0 0 6px var(--cyan-dim);
  }'''
new_tagline = '''  .tagline{
    margin-top:1rem;font-size:clamp(.7rem,1vw,.85rem);letter-spacing:.4em;
    color:var(--cyan);text-transform:uppercase;
    text-shadow:0 0 6px var(--cyan-dim);
  }'''
assert old_tagline in src, "tagline block not found"
src = src.replace(old_tagline, new_tagline)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] landing.html refined")
