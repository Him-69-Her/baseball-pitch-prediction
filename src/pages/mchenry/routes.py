from flask import Blueprint, render_template

mchenry_bp = Blueprint('mchenry', __name__, template_folder='.')

@mchenry_bp.route("/mchenry")
def mchenry():
    return render_template("mchenry.html")
