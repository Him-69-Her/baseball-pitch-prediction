#!/usr/bin/env python3
"""Defer start_subscribers() + VTN init — v2, uses line numbers."""
from pathlib import Path

p = Path("app.py")
lines = p.read_text().splitlines(keepends=True)

replacement = '''print()

def _deferred_startup():
    """Run blocking subscribers + VTN init AFTER gunicorn is serving."""
    import time as _t
    _t.sleep(2)
    try:
        start_subscribers()
        print("  ✅ Pub/Sub subscribers started")
    except Exception as _e:
        print(f"  ⚠️  start_subscribers failed: {_e}")
    try:
        from google.cloud import pubsub_v1 as _psv1
        _vtn_pub = _psv1.PublisherClient()
        init_vtn(_vtn_pub, PROJECT_ID, "market-ticks")
        print("  ✅ OpenADR VTN active")
    except Exception as _e:
        print(f"  ⚠️  OpenADR VTN init failed: {_e}")

try:
    import gevent as _gevent
    _gevent.spawn(_deferred_startup)
    print("  ⏳ Deferred startup scheduled (subscribers + VTN)")
except ImportError:
    import threading as _th
    _th.Thread(target=_deferred_startup, daemon=True).start()
    print("  ⏳ Deferred startup scheduled via thread (local dev)")
'''

new_lines = lines[:380] + [replacement] + lines[394:]
p.write_text("".join(new_lines))
print("[OK] Replaced lines 381-394 with deferred startup")

print("\n--- app.py (lines 378-420) ---")
for i, line in enumerate(Path("app.py").read_text().splitlines()[377:420], 378):
    print(f"{i:3d}  {line}")
