#!/usr/bin/env python3
"""
TINY-HUB — Add login page + auth gate to dashboard

Blocks all dashboard routes behind a login page.
Users must enter credentials to access any page or API.

Default credentials (change in .env):
    TINYHUB_ADMIN_USER=admin
    TINYHUB_ADMIN_PASS=tinyhub2026

Run from project root:
    python3 add_auth.py
"""

from pathlib import Path

# ══════════════════════════════════════════════════════════════
# STEP 1: Create login template
# ══════════════════════════════════════════════════════════════
TEMPLATE_DIR = Path("templates")
TEMPLATE_DIR.mkdir(exist_ok=True)

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tiny-Hub Network — Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #0a0e14;
            font-family: 'JetBrains Mono', monospace;
            overflow: hidden;
        }
        .bg-grid {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background-image:
                linear-gradient(rgba(0,255,157,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,255,157,0.03) 1px, transparent 1px);
            background-size: 60px 60px;
            z-index: 0;
        }
        .login-card {
            position: relative; z-index: 1;
            background: rgba(15,20,30,0.95);
            border: 1px solid rgba(0,255,157,0.15);
            border-radius: 8px;
            padding: 48px 40px;
            width: 420px;
            box-shadow: 0 0 80px rgba(0,255,157,0.05), 0 20px 60px rgba(0,0,0,0.5);
        }
        .logo {
            font-family: 'Outfit', sans-serif;
            font-weight: 900; font-size: 1.6rem;
            letter-spacing: 3px; color: #fff;
            text-align: center; margin-bottom: 4px;
        }
        .logo span { color: #00ff9d; }
        .subtitle {
            text-align: center; font-size: 0.6rem;
            color: rgba(0,255,157,0.5); letter-spacing: 2px;
            text-transform: uppercase; margin-bottom: 36px;
        }
        .field { margin-bottom: 20px; }
        .field label {
            display: block; font-size: 0.55rem;
            color: rgba(255,255,255,0.4); letter-spacing: 1.5px;
            text-transform: uppercase; margin-bottom: 8px;
        }
        .field input {
            width: 100%; padding: 12px 16px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 4px; color: #fff;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem; outline: none;
            transition: border-color 0.2s;
        }
        .field input:focus {
            border-color: #00ff9d;
            box-shadow: 0 0 0 2px rgba(0,255,157,0.1);
        }
        .field input::placeholder { color: rgba(255,255,255,0.15); }
        .btn {
            width: 100%; padding: 14px;
            background: #00ff9d; color: #0a0e14;
            border: none; border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700; font-size: 0.8rem;
            letter-spacing: 2px; text-transform: uppercase;
            cursor: pointer; transition: all 0.2s;
            margin-top: 8px;
        }
        .btn:hover { background: #00cc7d; transform: translateY(-1px); }
        .btn:active { transform: translateY(0); }
        .error {
            background: rgba(255,62,95,0.1);
            border: 1px solid rgba(255,62,95,0.3);
            color: #ff3e5f; padding: 10px 14px;
            border-radius: 4px; font-size: 0.7rem;
            margin-bottom: 20px; text-align: center;
            display: {% if error %}block{% else %}none{% endif %};
        }
        .stats {
            margin-top: 28px; padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.06);
            display: flex; justify-content: center; gap: 24px;
        }
        .stat {
            text-align: center;
        }
        .stat-val {
            font-size: 1rem; font-weight: 700; color: #00ff9d;
        }
        .stat-label {
            font-size: 0.45rem; color: rgba(255,255,255,0.3);
            letter-spacing: 1.5px; text-transform: uppercase;
            margin-top: 2px;
        }
        .pulse-dot {
            display: inline-block; width: 6px; height: 6px;
            background: #00ff9d; border-radius: 50%;
            box-shadow: 0 0 8px #00ff9d;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
    </style>
</head>
<body>
    <div class="bg-grid"></div>
    <div class="login-card">
        <div class="logo">TINY-HUB <span>NETWORK</span></div>
        <div class="subtitle">P2P Energy Marketplace</div>

        <div class="error" id="error-msg">{{ error or "Invalid credentials" }}</div>

        <form method="POST" action="/login">
            <div class="field">
                <label>Username</label>
                <input type="text" name="username" placeholder="Enter username" autocomplete="username" autofocus required>
            </div>
            <div class="field">
                <label>Password</label>
                <input type="password" name="password" placeholder="Enter password" autocomplete="current-password" required>
            </div>
            <button type="submit" class="btn">Access Dashboard</button>
        </form>

        <div class="stats">
            <div class="stat"><div class="stat-val">18,336</div><div class="stat-label">Buildings</div></div>
            <div class="stat"><div class="stat-val">720K</div><div class="stat-label">MWh/Year</div></div>
            <div class="stat"><div class="stat-val"><span class="pulse-dot"></span></div><div class="stat-label">Network Live</div></div>
            <div class="stat"><div class="stat-val">2</div><div class="stat-label">Districts</div></div>
        </div>
    </div>
</body>
</html>'''

LOGIN_PATH = TEMPLATE_DIR / "login.html"
LOGIN_PATH.write_text(LOGIN_HTML, encoding="utf-8")
print("  ✅ templates/login.html created")


# ══════════════════════════════════════════════════════════════
# STEP 2: Patch app.py — add auth
# ══════════════════════════════════════════════════════════════
APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Patch 1: Add imports and auth config
OLD_APP_LINE = "app = Flask(__name__)"

AUTH_SETUP = '''import os as _os
import functools
import hashlib
import secrets

# ── Auth Config ─────────────────────────────────────────────
ADMIN_USER = _os.environ.get("TINYHUB_ADMIN_USER", "admin")
ADMIN_PASS = _os.environ.get("TINYHUB_ADMIN_PASS", "tinyhub2026")
SECRET_KEY = _os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

app = Flask(__name__)
app.secret_key = SECRET_KEY'''

if "ADMIN_USER" not in src:
    if OLD_APP_LINE in src:
        src = src.replace(OLD_APP_LINE, AUTH_SETUP, 1)
        print("  ✅ app.py Patch 1: Auth config added")
    else:
        print("  ❌ Patch 1 failed — app = Flask() not found")
        exit(1)
else:
    print("  ⏭️  Patch 1: Auth already configured")

# Patch 2: Add session import to flask imports
OLD_FLASK_IMPORT = "from flask import Flask, render_template, jsonify, Response, request"
NEW_FLASK_IMPORT = "from flask import Flask, render_template, jsonify, Response, request, session, redirect, url_for"

if "session" not in src.split("\n")[0:20].__repr__():
    if OLD_FLASK_IMPORT in src:
        src = src.replace(OLD_FLASK_IMPORT, NEW_FLASK_IMPORT, 1)
        print("  ✅ app.py Patch 2: session/redirect imports added")
    else:
        print("  ⚠️  Patch 2: Flask import line not found exactly")
else:
    print("  ⏭️  Patch 2: session already imported")

# Patch 3: Add login routes and auth decorator before existing routes
ANCHOR = 'app.register_blueprint(oadr_bp)'

LOGIN_ROUTES = '''app.register_blueprint(oadr_bp)

# ── Auth Routes + Decorator ─────────────────────────────────
def login_required(f):
    """Decorator to require authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def check_auth():
    """Check auth on every request except login and static files."""
    open_paths = ["/login", "/static", "/favicon.ico"]
    if any(request.path.startswith(p) for p in open_paths):
        return None
    if not session.get("authenticated"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
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
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("login"))'''

if "login_required" not in src:
    if ANCHOR in src:
        src = src.replace(ANCHOR, LOGIN_ROUTES, 1)
        print("  ✅ app.py Patch 3: Login routes + auth gate added")
    else:
        print("  ❌ Patch 3 failed — blueprint anchor not found")
else:
    print("  ⏭️  Patch 3: Auth routes already exist")


# Patch 4: Add TINYHUB_ADMIN vars to .env
ENV = Path(".env")
if ENV.exists():
    env_src = ENV.read_text(encoding="utf-8")
    if "TINYHUB_ADMIN" not in env_src:
        env_src = env_src.rstrip() + "\nTINYHUB_ADMIN_USER=admin\nTINYHUB_ADMIN_PASS=tinyhub2026\n"
        ENV.write_text(env_src, encoding="utf-8")
        print("  ✅ .env: default admin credentials added")
    else:
        print("  ⏭️  .env: admin credentials already set")
else:
    print("  ⚠️  .env not found — using defaults (admin/tinyhub2026)")


APP.write_text(src, encoding="utf-8")

print()
print("  ✅ Auth gate complete.")
print()
print("  Login page: /login")
print("  Logout:     /logout")
print()
print("  Default credentials (change in .env):")
print("    Username: admin")
print("    Password: tinyhub2026")
print()
print("  To change credentials:")
print("    Edit .env → TINYHUB_ADMIN_USER and TINYHUB_ADMIN_PASS")
print()
print("  Rebuild: sudo docker-compose up -d --build")
print()
