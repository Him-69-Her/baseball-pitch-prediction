#!/usr/bin/env python3
"""Make sun band gaps transparent instead of solid black."""
from pathlib import Path

for template in ["templates/landing.html", "templates/about.html", "templates/how_it_works.html"]:
    f = Path(template)
    if not f.exists():
        continue
    src = f.read_text()
    orig = src

    # Replace the clipPath and band approach:
    # Instead of black rects ON TOP of the gradient, use a clipPath that
    # cuts the bands out of the dome shape itself

    old_clip = '''<clipPath id="domeClip"><path d="M 0,100 A 100,100 0 0 1 200,100 Z"/></clipPath>'''
    new_clip = '''<clipPath id="domeClip">
          <!-- Dome shape with horizontal gaps cut out -->
          <path d="M 0,100 A 100,100 0 0 1 200,100 Z"/>
        </clipPath>
        <clipPath id="bandClip">
          <!-- Only the solid band areas (gaps are excluded) -->
          <rect x="0" y="0" width="200" height="16"/>
          <rect x="0" y="18" width="200" height="14"/>
          <rect x="0" y="34.5" width="200" height="13.5"/>
          <rect x="0" y="51" width="200" height="13"/>
          <rect x="0" y="67.5" width="200" height="12.5"/>
          <rect x="0" y="84.5" width="200" height="8.5"/>
          <rect x="0" y="96" width="200" height="4"/>
        </clipPath>'''

    # Replace the g element to use both clips
    old_g = '''<g clip-path="url(#domeClip)">
        <rect x="0" y="0" width="200" height="100" fill="url(#sunBands)"/>
        <rect x="0" y="16" width="200" height="2" fill="#000"/>
        <rect x="0" y="32" width="200" height="2.5" fill="#000"/>
        <rect x="0" y="48" width="200" height="3" fill="#000"/>
        <rect x="0" y="64" width="200" height="3.5" fill="#000"/>
        <rect x="0" y="80" width="200" height="4.5" fill="#000"/>
        <rect x="0" y="93" width="200" height="3" fill="#000"/>
      </g>'''

    new_g = '''<g clip-path="url(#domeClip)">
        <g clip-path="url(#bandClip)">
          <rect x="0" y="0" width="200" height="100" fill="url(#sunBands)"/>
        </g>
      </g>'''

    if old_clip in src and old_g in src:
        src = src.replace(old_clip, new_clip)
        src = src.replace(old_g, new_g)
        f.write_text(src)
        print(f"[OK] {template} — sun bands now transparent")
    else:
        print(f"[SKIP] {template} — pattern not found")
