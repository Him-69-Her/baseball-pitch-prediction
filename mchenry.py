"""
McHenry County demo · static bundle.
Serves /mchenry/* from static/mchenry/ as a self-contained subsite.
"""
from flask import Blueprint, send_from_directory
import os

mchenry_bp = Blueprint('mchenry', __name__)

DEMO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'mchenry'
)

@mchenry_bp.route('/mchenry')
@mchenry_bp.route('/mchenry/')
@mchenry_bp.route('/mchenry/<path:filename>')
def serve(filename='index.html'):
    return send_from_directory(DEMO_DIR, filename)
