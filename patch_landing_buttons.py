#!/usr/bin/env python3
"""Add four CTA buttons below the TINY HUB ENERGY wordmark on landing page."""
from pathlib import Path

p = Path("templates/landing.html")
src = p.read_text()

old = '''  <div class="hero-content">
    <h1 class="wordmark">TINY&nbsp;HUB&nbsp;ENERGY</h1>
  </div>'''

new = '''  <div class="hero-content">
    <h1 class="wordmark">TINY&nbsp;HUB&nbsp;ENERGY</h1>
    <div class="cta-row">
      <a href="/login" class="btn primary">Sign In</a>
      <a href="#" class="btn">Apply for New Account</a>
      <a href="#" class="btn">Partner With Us</a>
      <a href="#" class="btn">Career Opportunities</a>
    </div>
  </div>'''

if old not in src:
    print("[ERROR] hero-content block not found")
else:
    src = src.replace(old, new)
    p.write_text(src)
    print("[OK] Added 4 CTA buttons below wordmark")
