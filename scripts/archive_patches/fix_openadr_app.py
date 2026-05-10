#!/usr/bin/env python3
"""Wire OpenADR VTN into app.py — fixed version."""
from pathlib import Path

APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

# Patch 1: imports
OLD_IMPORT = "from flask import Flask, render_template, jsonify, Response"
NEW_IMPORT = "from flask import Flask, render_template, jsonify, Response, request\nfrom openadr_vtn import oadr_bp, init_vtn"
if OLD_IMPORT not in src:
    print("  ❌ Flask import not found"); exit(1)
src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)
print("  ✅ Patch 1: imports")

# Patch 2: register blueprint
OLD_APP = "app = Flask(__name__)"
NEW_APP = "app = Flask(__name__)\napp.register_blueprint(oadr_bp)"
if OLD_APP not in src:
    print("  ❌ Flask app not found"); exit(1)
src = src.replace(OLD_APP, NEW_APP, 1)
print("  ✅ Patch 2: blueprint registered")

# Patch 3: init VTN — target the CALL SITE inside __main__ block, not the def
# The call site is: start_subscribers() followed by if __name__ == "__main__":
OLD_CALL = """start_subscribers()

if __name__ == "__main__":"""
NEW_CALL = """start_subscribers()

# ── OpenADR VTN init ─────────────────────────────────────────
try:
    from google.cloud import pubsub_v1 as _psv1
    _vtn_pub = _psv1.PublisherClient()
    init_vtn(_vtn_pub, PROJECT_ID, "market-ticks")
    print("  ✅ OpenADR VTN active")
    print("     POST /oadr/event/create  — issue DR event")
    print("     GET  /oadr/status        — VTN health")
except Exception as _e:
    print(f"  ⚠️  OpenADR VTN init failed: {_e}")

if __name__ == "__main__":"""

if OLD_CALL not in src:
    print("  ❌ start_subscribers() call site not found"); exit(1)
src = src.replace(OLD_CALL, NEW_CALL, 1)
print("  ✅ Patch 3: VTN init added after start_subscribers() call")

APP.write_text(src, encoding="utf-8")
print()
print("  ✅ app.py patched cleanly.")
