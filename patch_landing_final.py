#!/usr/bin/env python3
"""Landing v-final: clean up nav, strip to pure hero, half-sun, big wordmark."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

# ────────────────────────────────────────────────────────────
# 1) NAV RENAME: "Clean Energy Suppliers" -> "Suppliers", same for Consumers
# ────────────────────────────────────────────────────────────
old_nav = '''  <ul class="nav-links">
    <li><a href="#about">About</a></li>
    <li><a href="#how">How It Works</a></li>
    <li><a href="#suppliers">Clean Energy Suppliers</a></li>
    <li><a href="#consumers">Energy Consumers</a></li>
    <li><a href="#investors">Investors</a></li>
    <li><a href="/dashboard">Live Demo \u2192</a></li>
  </ul>'''
new_nav = '''  <ul class="nav-links">
    <li><a href="#about">About</a></li>
    <li><a href="#how">How It Works</a></li>
    <li><a href="#suppliers">Suppliers</a></li>
    <li><a href="#consumers">Consumers</a></li>
    <li><a href="#investors">Investors</a></li>
    <li><a href="/dashboard">Live Demo \u2192</a></li>
  </ul>'''
assert old_nav in src, "nav block not found"
src = src.replace(old_nav, new_nav)

# ────────────────────────────────────────────────────────────
# 2) HALF-SUN: clip the bottom of the sun at the horizon,
#    enlarge, push up so top arc sits below nav (nav ~4rem tall)
# ────────────────────────────────────────────────────────────
old_sun = '''  .sun{
    position:absolute;bottom:48vh;left:50%;transform:translateX(-50%);
    width:min(420px,52vw);aspect-ratio:1/1;
    z-index:3;'''
new_sun = '''  .sun{
    position:absolute;bottom:50vh;left:50%;transform:translateX(-50%);
    width:min(640px,72vw);aspect-ratio:1/1;
    /* clip off the bottom half so only the top arc shows above horizon */
    clip-path:inset(0 0 50% 0);
    z-index:3;'''
assert old_sun in src, "sun block not found"
src = src.replace(old_sun, new_sun)

# ────────────────────────────────────────────────────────────
# 3) WORDMARK: scale up to fill the dark band (edge-to-edge feel)
# ────────────────────────────────────────────────────────────
old_wm_css = '''  .wordmark{
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
new_wm_css = '''  .wordmark{
    font-family:'Monoton',cursive;
    font-size:clamp(3rem,10.5vw,9.5rem);
    letter-spacing:.08em;line-height:1;
    color:var(--sun-1);
    text-shadow:
      0 0 14px var(--sun-2),
      0 0 36px var(--sun-3),
      0 2px 0 rgba(0,0,0,0.6);
    animation:flicker 5s infinite;
    white-space:nowrap;
  }'''
assert old_wm_css in src, "wordmark css not found"
src = src.replace(old_wm_css, new_wm_css)

# ────────────────────────────────────────────────────────────
# 4) STRIP EVERYTHING BELOW THE HERO: stats, how-it-works, thesis,
#    pilot, footer, and the inline <script> reveal observer.
# ────────────────────────────────────────────────────────────
import re

# Find everything from "<div class=\"stats\">" through "</footer>" and kill it,
# plus the trailing reveal <script>.
start_marker = '<div class="stats">'
end_marker = '</footer>'
assert start_marker in src, "stats strip start not found"
assert end_marker in src, "footer end not found"

start_idx = src.index(start_marker)
end_idx = src.index(end_marker) + len(end_marker)
src = src[:start_idx] + src[end_idx:]

# Remove the reveal observer script (no longer any .reveal elements)
old_script = '''<script>
  // Scroll reveal
  const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && e.target.classList.add('in')), {threshold:0.1});
  document.querySelectorAll('.reveal').forEach(el => io.observe(el));
</script>
'''
if old_script in src:
    src = src.replace(old_script, '')

# ────────────────────────────────────────────────────────────
# 5) Hero height: lock to full viewport since it IS the page now
# ────────────────────────────────────────────────────────────
old_hero_size = '''  .hero{
    position:relative;height:100vh;min-height:720px;overflow:hidden;
    display:flex;flex-direction:column;justify-content:center;align-items:center;
  }'''
new_hero_size = '''  .hero{
    position:relative;height:100vh;min-height:640px;overflow:hidden;
    display:flex;flex-direction:column;align-items:center;
  }'''
assert old_hero_size in src, "hero size block not found"
src = src.replace(old_hero_size, new_hero_size)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] landing-final patch applied")
