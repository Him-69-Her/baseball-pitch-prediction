#!/usr/bin/env python3
"""
Patch: Move dashboard from werkzeug dev server to gunicorn + gevent-websocket
for Cloud Run production. Fixes Socket.IO 500 errors that block building render.
"""
from pathlib import Path

REPO = Path(__file__).parent

# --- 1. requirements.txt: add gunicorn + gevent-websocket ---
req_path = REPO / "requirements.txt"
req = req_path.read_text().splitlines()
needed = {
    "gunicorn": "gunicorn>=21.2.0",
    "gevent": "gevent>=24.2.1",
    "gevent-websocket": "gevent-websocket>=0.10.1",
}
existing = {line.split(">=")[0].split("==")[0].strip().lower() for line in req if line.strip()}
for pkg, pin in needed.items():
    if pkg not in existing:
        req.append(pin)
req_path.write_text("\n".join(req) + "\n")
print(f"[OK] requirements.txt updated -> {req_path}")

# --- 2. Dockerfile: swap CMD from python3 app.py -> gunicorn geventwebsocket worker ---
dockerfile_path = REPO / "Dockerfile"
dockerfile = dockerfile_path.read_text()
old_cmd = 'CMD ["python3", "-u", "app.py"]'
new_cmd = (
    'CMD exec gunicorn '
    '--worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker '
    '--workers 1 '
    '--threads 8 '
    '--timeout 0 '
    '--bind 0.0.0.0:${PORT:-8080} '
    'app:app'
)
if old_cmd in dockerfile:
    dockerfile = dockerfile.replace(old_cmd, new_cmd)
    dockerfile_path.write_text(dockerfile)
    print(f"[OK] Dockerfile CMD swapped -> {dockerfile_path}")
else:
    print(f"[WARN] old CMD not found in Dockerfile, inspect manually")

# --- 3. docker-entrypoint-cloudrun.sh: make sure it execs CMD ---
entry_path = REPO / "docker-entrypoint-cloudrun.sh"
entry = entry_path.read_text()
print(f"[INFO] current entrypoint:\n{entry}")
if 'exec "$@"' not in entry:
    print("[WARN] entrypoint may not forward to CMD — review manually")

# --- 4. cloudbuild.yaml: port 8080, session affinity, longer timeout ---
cb_path = REPO / "cloudbuild.yaml"
cb = cb_path.read_text()
cb = cb.replace("'--port'\n      - '5000'", "'--port'\n      - '8080'")
# Insert extra flags before `--project` line (only once)
extra_flags = """      - '--session-affinity'
      - '--timeout'
      - '3600'
      - '--min-instances'
      - '1'
      - '--max-instances'
      - '1'
      - '--project'"""
if "'--session-affinity'" not in cb:
    cb = cb.replace("      - '--project'", extra_flags, 1)
cb_path.write_text(cb)
print(f"[OK] cloudbuild.yaml patched -> {cb_path}")

print("\n[DONE] Review diffs, then commit + push to main to trigger Cloud Build.")
