#!/usr/bin/env python3
"""Revert wordmark font-size only, leave sun + everything else alone."""
from pathlib import Path

f = Path("templates/landing.html")
src = f.read_text()
orig = src

old = '''  .wordmark{
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
new = '''  .wordmark{
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
assert old in src, "oversized wordmark block not found"
src = src.replace(old, new)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] wordmark reverted to previous size")
