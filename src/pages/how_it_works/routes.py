from flask import Blueprint, render_template

how_it_works_bp = Blueprint('how_it_works', __name__, template_folder='.')

@how_it_works_bp.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")
