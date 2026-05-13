"""
McHenry County demo · static bundle.
Serves /mchenry/* from static/mchenry/ as a self-contained subsite.
Forces trailing slash so relative asset paths resolve correctly.

Endpoints:
  /mchenry/                  -> static index
  /mchenry/<file>            -> any static asset
  /mchenry/api/config.js     -> runtime API key injection
  /mchenry/api/pilot         -> pilot state · GET reads, POST toggles (password-gated)
  /mchenry/api/pilot/auth    -> "is auth required + verify password" endpoint
"""
from flask import Blueprint, send_from_directory, redirect, Response, request, jsonify
import os
import json
import hmac
import threading
from datetime import datetime, timezone

mchenry_bp = Blueprint('mchenry', __name__)

DEMO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'mchenry'
)

# ───────────────────────────────────────────────────────────────
# Admin auth · env var `TINYHUB_ADMIN_PASSWORD`
# Mounted via Cloud Run secret `tinyhub-admin-password:latest`.
# If env unset (e.g. local dev), endpoint is open · "fail open".
# ───────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get('TINYHUB_ADMIN_PASSWORD', '')


def _password_required():
    """True if auth gating is active."""
    return bool(ADMIN_PASSWORD)


def _check_password(provided):
    """Constant-time comparison · returns True if password matches."""
    if not _password_required():
        return True  # fail open for local dev
    if not provided:
        return False
    return hmac.compare_digest(provided, ADMIN_PASSWORD)


# ───────────────────────────────────────────────────────────────
# Pilot state · in-memory for demo
# TODO · upgrade to Firestore for multi-instance + persistent state.
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


@mchenry_bp.route('/mchenry/api/pilot/auth', methods=['GET'])
def pilot_auth_status():
    """Tells the frontend whether the pilot control needs a password."""
    return jsonify({'required': _password_required()})


@mchenry_bp.route('/mchenry/api/pilot/auth', methods=['POST'])
def pilot_auth_verify():
    """Verify a password without changing pilot state."""
    body = request.get_json(silent=True) or {}
    provided = body.get('password', '')
    if _check_password(provided):
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'invalid password'}), 403


@mchenry_bp.route('/mchenry/api/pilot', methods=['GET'])
def pilot_get():
    """Read current pilot state · no auth required for read."""
    with _pilot_lock:
        return jsonify(dict(_pilot_state))


@mchenry_bp.route('/mchenry/api/pilot', methods=['POST'])
def pilot_post():
    """
    Toggle pilot state · password-gated when TINYHUB_ADMIN_PASSWORD is set.
    Body: { "action": "start"|"stop", "password": "..." }
    Password preferred via X-Admin-Password header.
    """
    if _password_required():
        provided = request.headers.get('X-Admin-Password', '')
        if not provided:
            body = request.get_json(silent=True) or {}
            provided = body.get('password', '')
        if not provided:
            return jsonify({'error': 'auth required'}), 401
        if not _check_password(provided):
            return jsonify({'error': 'invalid password'}), 403

    body = request.get_json(silent=True) or {}
    action = body.get('action', '').lower()
    if action not in ('start', 'stop'):
        return jsonify({'error': 'action must be "start" or "stop"'}), 400

    with _pilot_lock:
        if action == 'start':
            _pilot_state['running'] = True
            _pilot_state['startedAt'] = _now_iso()
            _pilot_state['lastActor'] = request.headers.get('X-Forwarded-For', 'unknown')
            # TODO: kick off real services here · matching_engine.start(), etc.
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
