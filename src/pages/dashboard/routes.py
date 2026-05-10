from flask import Blueprint, render_template

dashboard_bp = Blueprint('dashboard', __name__, template_folder='.')

@dashboard_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")
