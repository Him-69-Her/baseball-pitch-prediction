#!/usr/bin/env python3
"""Fix app.py Pub/Sub config to point at new org projects."""
from pathlib import Path

f = Path("app.py")
src = f.read_text()
orig = src

# Fix project ID
src = src.replace(
    'PROJECT_ID = "tiny-hub-network"',
    'PROJECT_ID = "tinyhub-data-dev"'
)

# Fix D91 subscription name
src = src.replace(
    'D91_SUB = "district91-energy-dashboard-sub"',
    'D91_SUB = "d91-dashboard-sub"'
)

# Fix D91 topic name
src = src.replace(
    'D91_TOPIC = "district91-energy"',
    'D91_TOPIC = "d91-trades"'
)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] app.py Pub/Sub config updated")
print("  PROJECT_ID: tinyhub-data-dev")
print("  D91_SUB: d91-dashboard-sub")
print("  D91_TOPIC: d91-trades")
