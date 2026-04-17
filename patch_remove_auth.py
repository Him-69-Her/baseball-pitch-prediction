#!/usr/bin/env python3
"""Patch app.py to remove auth gate and swap landing page."""
import re
from pathlib import Path

app_py = Path("app.py")
src = app_py.read_text()
orig = src

# 1) Neuter login_required decorator -> pass-through
old_decorator = '''def login_required(f):
    """Decorator to require authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated'''
new_decorator = '''def login_required(f):
    """No-op: auth disabled for public demo mode."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated'''
assert old_decorator in src, "login_required block not found"
src = src.replace(old_decorator, new_decorator)

# 2) Neuter before_request auth check
old_before = '''@app.before_request
def check_auth():
    """Check auth on every request except login and static files."""
    open_paths = ["/login", "/static", "/favicon.ico", "/api/", "/oadr/"]
    if any(request.path.startswith(p) for p in open_paths):
        return None
    if not session.get("authenticated"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))'''
new_before = '''@app.before_request
def check_auth():
    """No-op: auth disabled for public demo mode."""
    return None'''
assert old_before in src, "before_request block not found"
src = src.replace(old_before, new_before)

# 3) /login route -> redirect to /
old_login = '''@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page."""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["authenticated"] = True
            session["user"] = username
            return redirect("/")
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")'''
new_login = '''@app.route("/login", methods=["GET", "POST"])
def login():
    """Auth disabled \u2014 public demo mode. Redirect to landing."""
    return redirect("/")'''
assert old_login in src, "login route block not found"
src = src.replace(old_login, new_login)

# 4) /logout -> redirect to /
old_logout = '''@app.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("login"))'''
new_logout = '''@app.route("/logout")
def logout():
    """Auth disabled \u2014 public demo mode."""
    session.clear()
    return redirect("/")'''
assert old_logout in src, "logout route block not found"
src = src.replace(old_logout, new_logout)

# 5) Swap / to render landing.html, move old dashboard to /dashboard
old_index = '''@app.route("/")
def index():
    return render_template("dashboard.html")'''
new_index = '''@app.route("/")
def index():
    return render_template("landing.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")'''
assert old_index in src, "index route block not found"
src = src.replace(old_index, new_index)

assert src != orig, "No changes applied"
app_py.write_text(src)
print("[OK] app.py patched")
