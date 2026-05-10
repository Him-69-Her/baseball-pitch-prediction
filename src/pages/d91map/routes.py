from flask import Blueprint, render_template

d91map_bp = Blueprint('d91map', __name__, template_folder='.')

@d91map_bp.route("/d91map")
def d91map():
    return render_template("district91_map.html")
