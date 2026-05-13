"""
McHenry County demo · static bundle.
Serves /mchenry/* from static/mchenry/ as a self-contained subsite.
Forces trailing slash so relative asset paths resolve correctly.

Endpoints:
  /mchenry/             -> static index
  /mchenry/<file>       -> any static asset
  /mchenry/api/config.js -> runtime API key injection
  /mchenry/api/pilot    -> pilot start/stop control (GET reads, POST toggles)
"""
from flask import Blueprint, send_from_directory, redirect, Response, request, jsonify
import os
import json
import threading
from datetime import datetime, timezone

mchenry_bp = Blueprint('mchenry', __name__)

DEMO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'mchenry'
)

# ───────────────────────────────────────────────────────────────
# Pilot state · in-memory for demo
#
# TODO · upgrade to Firestore for multi-instance + persistent state:
#   from google.cloud import firestore
#   db = firestore.Client()
#   pilot_ref = db.collection('pilot').document('mchenry')
#   def read():   doc = pilot_ref.get(); return doc.to_dict() if doc.exists else default
#   def write(s): pilot_ref.set(s, merge=True)
#
# TODO · gate POST with @login_required when going beyond demo mode.
# Auth scaffold already exists in app.py (currently no-op).
# ───────────────────────────────────────────────────────────────
_pilot_lock = threading.Lock()
_pilot_state = {
    'running': False,
    'startedAt': None,
    'stoppedAt': None,
    'lastActor': None
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@mchenry_bp.route('/mchenry')
def mchenry_redirect():
    return redirect('/mchenry/', code=301)


@mchenry_bp.route('/mchenry/api/config.js')
def mchenry_config():
    """Inject runtime config (API keys, env) into the browser as JS."""
    config = {
        'mapsApiKey': os.environ.get('GOOGLE_MAPS_API_KEY', ''),
        'env': os.environ.get('FLASK_ENV', 'production')
    }
    body = f'window.TINYHUB_CONFIG = {json.dumps(config)};'
    return Response(
        body,
        mimetype='application/javascript',
        headers={'Cache-Control': 'no-store, must-revalidate'}
    )


@mchenry_bp.route('/mchenry/api/pilot', methods=['GET'])
def pilot_get():
    """Read the current pilot state."""
    with _pilot_lock:
        return jsonify(dict(_pilot_state))


@mchenry_bp.route('/mchenry/api/pilot', methods=['POST'])
def pilot_post():
    """
    Toggle pilot state.
    Body: {"action": "start"} or {"action": "stop"}

    NOTE: This currently flips a UI flag only. Wire to real services
    (matching engine kickoff, Pub/Sub subscribers, etc.) inside the
    `if action == 'start'` / `'stop'` branches when ready.
    """
    body = request.get_json(silent=True) or {}
    action = body.get('action', '').lower()
    if action not in ('start', 'stop'):
        return jsonify({'error': 'action must be "start" or "stop"'}), 400

    with _pilot_lock:
        if action == 'start':
            _pilot_state['running'] = True
            _pilot_state['startedAt'] = _now_iso()
            _pilot_state['lastActor'] = request.headers.get('X-Forwarded-For', 'unknown')
            # TODO: kick off real services here
            #   e.g. matching_engine.start(), pubsub_subscribers.start(), ...
        else:
            _pilot_state['running'] = False
            _pilot_state['stoppedAt'] = _now_iso()
            _pilot_state['lastActor'] = request.headers.get('X-Forwarded-For', 'unknown')
            # TODO: gracefully stop real services here

        return jsonify(dict(_pilot_state))


@mchenry_bp.route('/mchenry/')
@mchenry_bp.route('/mchenry/<path:filename>')
def serve(filename='index.html'):
    return send_from_directory(DEMO_DIR, filename)
