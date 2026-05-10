#!/usr/bin/env python3
"""Defer start_subscribers() and VTN init so they don't block gunicorn worker import."""
from pathlib import Path

p = Path("app.py")
src = p.read_text()

old_block = '''print()
start_subscribers()
# ── OpenADR VTN init ─────────────────────────────────────────
try:
    from google.cloud import pubsub_v1 as _psv1
    _vtn_pub = _psv1.PublisherClient()
    init_vtn(_vtn_pub, PROJECT_ID, "market-ticks")
    print("  ✅ OpenADR VTN active")
    print("     POST /oadr/event/create  — issue DR event")
    print("     GET  /oadr/status        — VTN health")
except Exception as _e:
    print(f"  ⚠️  OpenADR VTN init failed: {_e}")'''

new_block = '''print()

def _deferred_startup():
    """Run blocking subscribers + VTN init AFTER gunicorn is serving.

    Pub/Sub StreamingPull and gRPC init block the gevent event loop during
    module import, causing the worker to hang before it can accept requests.
    Running this in a greenlet after app import lets gunicorn mark the worker
    ready and start serving HTTP immediately.
    """
    import time as _t
    _t.sleep(2)  # let gunicorn flush boot and open the listen socket
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
    # No gevent (local dev with python3 app.py) — fall back to a thread
    import threading as _th
    _th.Thread(target=_deferred_startup, daemon=True).start()
    print("  ⏳ Deferred startup scheduled via thread (local dev)")'''

if old_block not in src:
    print("[ERROR] old block not found — inspect app.py manually")
    print("Expected to match lines around 381-393")
else:
    src = src.replace(old_block, new_block)
    p.write_text(src)
    print("[OK] Deferred start_subscribers() + VTN init into a gevent greenlet")

# Show the patched region
print("\n--- app.py (lines 380-420) ---")
for i, line in enumerate(Path("app.py").read_text().splitlines()[379:420], 380):
    print(f"{i:3d}  {line}")
