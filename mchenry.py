"""
McHenry County demo · static bundle.
Serves /mchenry/* from static/mchenry/ as a self-contained subsite.
Forces trailing slash so relative asset paths resolve correctly.
Provides /mchenry/api/config.js · runtime injection of the Maps API key.
"""
from flask import Blueprint, send_from_directory, redirect, Response
import os
import json

mchenry_bp = Blueprint('mchenry', __name__)

DEMO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'mchenry'
)


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


@mchenry_bp.route('/mchenry/')
@mchenry_bp.route('/mchenry/<path:filename>')
def serve(filename='index.html'):
    return send_from_directory(DEMO_DIR, filename)
