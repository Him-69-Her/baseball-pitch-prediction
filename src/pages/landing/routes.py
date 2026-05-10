from flask import Blueprint, render_template, redirect

landing_bp = Blueprint('landing', __name__, template_folder='.')

@landing_bp.route("/")
def index():
    return render_template("landing.html")

@landing_bp.route("/login", methods=["GET", "POST"])
def login():
    return redirect("/")

@landing_bp.route("/logout")
def logout():
    from flask import session
    session.clear()
    return redirect("/")
