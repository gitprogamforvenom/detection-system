# -*- coding: utf-8 -*-
import os, sys, csv, io
import requests
import mysql.connector
from flask import Flask, request, Response, redirect, url_for, session, render_template, flash
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR  = os.path.dirname(BASE_DIR)
TEMPLATE_DIR = os.path.join(PROJECT_DIR, 'auth', 'templates')

FRAUD_BASE = os.environ.get("FRAUD_BASE", "http://127.0.0.1:5000")
SPAM_BASE  = os.environ.get("SPAM_BASE", "http://127.0.0.1:5001")

HOP_HEADERS = {
    'content-encoding','transfer-encoding','connection','keep-alive',
    'proxy-authenticate','proxy-authorization','te','trailers','upgrade',
    'x-frame-options','content-security-policy'
}

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = "sentinelledger_secret_2025"
app.permanent_session_lifetime = timedelta(hours=8)
bcrypt = Bcrypt(app)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "mysql-kuif.railway.internal"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "smbIROLNRlRhchdzTGuNaqNWdHkBKaay"),
    "database": os.environ.get("DB_DATABASE", "railway")
}

# Run database setup / migration on startup
try:
    import sys
    sys.path.insert(0, os.path.join(PROJECT_DIR, 'auth'))
    import db_setup
    print("Running database setup/migration...")
    db_setup.setup()
    print("Database setup/migration completed successfully.")
except Exception as _db_setup_err:
    print(f"Warning: Database setup/migration failed to run on startup: {_db_setup_err}")

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def logged_in():
    return "user_id" in session

def log_activity(user_id, action, detail=""):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO activity_logs (user_id,action,detail,ip_address) VALUES (%s,%s,%s,%s)",
            (user_id, action, detail, request.remote_addr)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

# ── Decorators ─────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not logged_in():
            flash("Please log in first.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not logged_in():
            flash("Please log in first.", "danger")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Access denied. Admins only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

# ==============================================================================
# AUTH ROUTES
# ==============================================================================

@app.route("/")
def index():
    if not logged_in():
        return redirect(url_for("login"))
    if session.get("role") == "admin":
        return redirect(url_for("admin"))
    return redirect(url_for("home"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if logged_in():
        return redirect(url_for("index"))
    if request.method == "POST":
        email    = request.form["email"].strip()
        password = request.form["password"]
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user   = cursor.fetchone()

            if user and bcrypt.check_password_hash(user["password"], password):
                if not user["is_active"]:
                    flash("Account suspended. Contact admin.", "danger")
                    cursor.close(); conn.close()
                    return render_template("login.html")

                session.permanent   = True
                session["user_id"]  = user["id"]
                session["username"] = user["username"]
                session["role"]     = user["role"]

                cursor.execute(
                    "INSERT INTO login_sessions (user_id, ip_address) VALUES (%s,%s)",
                    (user["id"], request.remote_addr)
                )
                cursor.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user["id"],))
                conn.commit(); cursor.close(); conn.close()
                log_activity(user["id"], "LOGIN", f"IP: {request.remote_addr}")
                flash(f"Welcome, {user['username']}!", "success")

                if user["role"] == "admin":
                    return redirect(url_for("admin"))
                return redirect(url_for("home"))

            # Failed login
            try:
                cursor.execute(
                    "INSERT INTO failed_logins (email, ip_address) VALUES (%s,%s)",
                    (email, request.remote_addr)
                )
                conn.commit()
            except Exception:
                pass
            cursor.close(); conn.close()
            flash("Invalid email or password.", "danger")

        except mysql.connector.Error as err:
            flash("Database error: " + str(err), "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if logged_in():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form["username"].strip()
        email    = request.form["email"].strip()
        password = request.form["password"]
        confirm  = request.form["confirm_password"]
        role     = request.form.get("role", "analyst")

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        try:
            conn   = get_db(); cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username,email,password,role) VALUES (%s,%s,%s,%s)",
                (username, email, hashed, role)
            )
            conn.commit()
            uid = cursor.lastrowid
            cursor.close(); conn.close()
            log_activity(uid, "REGISTER", f"{username} ({role})")
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.errors.IntegrityError:
            flash("Username or email already exists.", "danger")
        except mysql.connector.Error as err:
            flash("Database error: " + str(err), "danger")

    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    log_activity(session.get("user_id"), "LOGOUT", "User logged out")
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/home")
@login_required
def home():
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM alerts WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",
        (session["user_id"],)
    )
    alerts = cursor.fetchall()
    cursor.execute("""
        SELECT COUNT(*) AS total,
               SUM(decision IN ('fraud','spam')) AS threats,
               SUM(decision IN ('legitimate','ham')) AS safe
        FROM alerts WHERE user_id=%s
    """, (session["user_id"],))
    stats = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template("index.html",
        alerts=alerts, stats=stats,
        username=session.get("username",""), role=session.get("role","")
    )

@app.route("/dashboard")
@login_required
def dashboard():
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM alerts WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",
        (session["user_id"],)
    )
    alerts = cursor.fetchall()
    cursor.execute("""
        SELECT COUNT(*) AS total,
               SUM(decision IN ('fraud','spam')) AS threats,
               SUM(decision IN ('legitimate','ham')) AS safe
        FROM alerts WHERE user_id=%s
    """, (session["user_id"],))
    stats = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template("dashboard.html",
        alerts=alerts, stats=stats,
        username=session.get("username",""), role=session.get("role","")
    )

# ==============================================================================
# ADMIN ROUTES
# ==============================================================================

@app.route("/admin")
@admin_required
def admin():
    search   = request.args.get("search","").strip()
    role_f   = request.args.get("role_filter","")
    status_f = request.args.get("status_filter","")

    # Safe defaults in case DB fails
    total_users = active_users = new_today = logins_today = failed_today = total_logins = 0
    recent_activity = users = login_history = failed_logins = []
    reg_chart = login_chart = role_chart = []

    def _str(v):
        """Convert datetime/date/Decimal to JSON-safe string or number."""
        import datetime, decimal
        if isinstance(v, (datetime.datetime, datetime.date)):
            return str(v)
        if isinstance(v, decimal.Decimal):
            return int(v)
        return v

    def _safe_row(row):
        """Convert all values in a dict row to JSON-safe types."""
        return {k: _str(v) for k, v in row.items()}

    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS c FROM users")
        total_users = cursor.fetchone()["c"] or 0
        cursor.execute("SELECT COUNT(*) AS c FROM users WHERE is_active=1")
        active_users = cursor.fetchone()["c"] or 0
        cursor.execute("SELECT COUNT(*) AS c FROM users WHERE DATE(created_at)=CURDATE()")
        new_today = cursor.fetchone()["c"] or 0
        cursor.execute("SELECT COUNT(*) AS c FROM login_sessions WHERE DATE(login_at)=CURDATE()")
        logins_today = cursor.fetchone()["c"] or 0
        cursor.execute("SELECT COUNT(*) AS c FROM failed_logins WHERE DATE(attempted_at)=CURDATE()")
        failed_today = cursor.fetchone()["c"] or 0
        cursor.execute("SELECT COUNT(*) AS c FROM login_sessions")
        total_logins = cursor.fetchone()["c"] or 0

        cursor.execute("""
            SELECT al.*, u.username FROM activity_logs al
            LEFT JOIN users u ON al.user_id=u.id
            ORDER BY al.created_at DESC LIMIT 15
        """)
        recent_activity = [_safe_row(r) for r in cursor.fetchall()]

        q = "SELECT * FROM users WHERE 1=1"; p = []
        if search:
            q += " AND (username LIKE %s OR email LIKE %s)"; p += [f"%{search}%",f"%{search}%"]
        if role_f:
            q += " AND role=%s"; p.append(role_f)
        if status_f != "":
            q += " AND is_active=%s"; p.append(int(status_f))
        q += " ORDER BY created_at DESC"
        cursor.execute(q, p)
        users = [_safe_row(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt FROM users
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
            GROUP BY DATE(created_at) ORDER BY day
        """)
        reg_chart = [
            {"day": str(row["day"]) if row["day"] else "", "cnt": int(row["cnt"] or 0)}
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT DATE(login_at) AS day, COUNT(*) AS cnt FROM login_sessions
            WHERE login_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
            GROUP BY DATE(login_at) ORDER BY day
        """)
        login_chart = [
            {"day": str(row["day"]) if row["day"] else "", "cnt": int(row["cnt"] or 0)}
            for row in cursor.fetchall()
        ]

        cursor.execute("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
        role_chart = [
            {"role": str(row["role"] or ""), "cnt": int(row["cnt"] or 0)}
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT ls.*, u.username FROM login_sessions ls
            LEFT JOIN users u ON ls.user_id=u.id
            ORDER BY ls.login_at DESC LIMIT 20
        """)
        login_history = [_safe_row(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM failed_logins ORDER BY attempted_at DESC LIMIT 20")
        failed_logins = [_safe_row(r) for r in cursor.fetchall()]

        cursor.close(); conn.close()

    except Exception as e:
        flash(f"Database error loading admin panel: {e}", "danger")

    return render_template("admin.html",
        username=session["username"], role=session["role"],
        total_users=total_users, active_users=active_users,
        new_today=new_today, logins_today=logins_today,
        failed_today=failed_today, total_logins=total_logins,
        recent_activity=recent_activity, users=users,
        reg_chart=reg_chart, login_chart=login_chart, role_chart=role_chart,
        login_history=login_history, failed_logins=failed_logins,
        search=search, role_filter=role_f, status_filter=status_f
    )


@app.route("/admin/user/add", methods=["POST"])
@admin_required
def admin_add_user():
    username = request.form["username"].strip()
    email    = request.form["email"].strip()
    password = request.form["password"]
    role     = request.form.get("role","analyst")
    hashed   = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username,email,password,role) VALUES (%s,%s,%s,%s)",
                       (username, email, hashed, role))
        conn.commit(); cursor.close(); conn.close()
        log_activity(session["user_id"], "ADMIN_ADD_USER", f"Added: {username}")
        flash(f"User '{username}' created.", "success")
    except mysql.connector.errors.IntegrityError:
        flash("Username or email already exists.", "danger")
    return redirect(url_for("admin"))

@app.route("/admin/user/edit/<int:uid>", methods=["POST"])
@admin_required
def admin_edit_user(uid):
    username = request.form["username"].strip()
    email    = request.form["email"].strip()
    role     = request.form["role"]
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET username=%s,email=%s,role=%s WHERE id=%s",
                   (username, email, role, uid))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_EDIT_USER", f"Edited uid={uid}")
    flash("User updated.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/toggle/<int:uid>")
@admin_required
def admin_toggle_user(uid):
    if uid == session["user_id"]:
        flash("Cannot suspend your own account.", "danger")
        return redirect(url_for("admin"))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT is_active,username FROM users WHERE id=%s", (uid,))
    user = cursor.fetchone()
    new_s = 0 if user["is_active"] else 1
    cursor.execute("UPDATE users SET is_active=%s WHERE id=%s", (new_s, uid))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_TOGGLE_USER",
                 f"{'Activated' if new_s else 'Suspended'}: {user['username']}")
    flash(f"User {'activated' if new_s else 'suspended'}.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/delete/<int:uid>")
@admin_required
def admin_delete_user(uid):
    if uid == session["user_id"]:
        flash("Cannot delete your own account.", "danger")
        return redirect(url_for("admin"))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username FROM users WHERE id=%s", (uid,))
    user = cursor.fetchone()
    cursor.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_DELETE_USER", f"Deleted: {user['username']}")
    flash(f"User '{user['username']}' deleted.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/reset_password/<int:uid>", methods=["POST"])
@admin_required
def admin_reset_password(uid):
    new_pw = request.form["new_password"]
    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("admin"))
    hashed = bcrypt.generate_password_hash(new_pw).decode("utf-8")
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (hashed, uid))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_RESET_PW", f"Reset pw uid={uid}")
    flash("Password reset successfully.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/export/users")
@admin_required
def admin_export_users():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id,username,email,role,is_active,last_login,created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall(); cursor.close(); conn.close()
    si = io.StringIO()
    cw = csv.DictWriter(si, fieldnames=["id","username","email","role","is_active","last_login","created_at"])
    cw.writeheader(); cw.writerows(rows)
    log_activity(session["user_id"], "EXPORT_USERS", "CSV export")
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment;filename=users_export.csv"})

@app.route("/admin/export/activity")
@admin_required
def admin_export_activity():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT al.id, u.username, al.action, al.detail, al.ip_address, al.created_at
        FROM activity_logs al LEFT JOIN users u ON al.user_id=u.id
        ORDER BY al.created_at DESC
    """)
    rows = cursor.fetchall(); cursor.close(); conn.close()
    si = io.StringIO()
    cw = csv.DictWriter(si, fieldnames=["id","username","action","detail","ip_address","created_at"])
    cw.writeheader(); cw.writerows(rows)
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment;filename=activity_export.csv"})

# ==============================================================================
# PROXY HELPERS
# ==============================================================================

def _proxy(target_base, path):
    url = target_base + "/" + path.lstrip("/")
    if request.query_string:
        url += "?" + request.query_string.decode("utf-8")
    fwd = {k: v for k, v in request.headers
           if k.lower() not in ("host","content-length","origin","referer","x-user-id","x-user-role","x-user-username")}
    fwd["X-Forwarded-Host"]  = "mysql-kuif.railway.internal:8000"
    fwd["X-Forwarded-Proto"] = "http"
    if logged_in():
        fwd["X-User-Id"] = str(session["user_id"])
        fwd["X-User-Role"] = str(session.get("role", "analyst"))
        fwd["X-User-Username"] = str(session.get("username", ""))
    try:
        resp = requests.request(
            method=request.method, url=url,
            headers=fwd, data=request.get_data(),
            cookies=request.cookies, allow_redirects=False,
            timeout=60, stream=True
        )
    except requests.exceptions.ConnectionError:
        is_json = (
            ("Accept" in request.headers and "application/json" in request.headers["Accept"]) or
            ("upload" in path) or ("api" in path)
        )
        if is_json:
            import json
            err_json = json.dumps({"error": f"Service Unavailable: Cannot reach {target_base}. Make sure the backend service is running."})
            return Response(err_json, status=502, mimetype="application/json")
        html = (
            "<div style='font-family:sans-serif;padding:2rem;background:#0f0c29;color:#fff;min-height:100vh'>"
            "<h2 style='color:#f87171'>Service Unavailable</h2>"
            "<p>Cannot reach <b>" + target_base + "</b>. Make sure the app is running.</p>"
            "<a href='/' style='color:#a78bfa'>Back to Home</a>"
            "</div>"
        )
        return Response(html, status=502, mimetype="text/html")
    headers = [(k,v) for k,v in resp.headers.items() if k.lower() not in HOP_HEADERS]
    return Response(response=resp.content, status=resp.status_code, headers=headers)

def _blocked(app_name):
    html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="2;url=/login">
<title>Login Required</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63);
     min-height:100vh;display:flex;align-items:center;justify-content:center}
.c{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:20px;
   padding:48px 44px;text-align:center;max-width:420px;color:#fff}
.icon{font-size:56px;margin-bottom:20px}
h1{font-size:22px;font-weight:700;color:#f87171;margin-bottom:12px}
p{color:rgba(255,255,255,0.5);font-size:14px;line-height:1.7;margin-bottom:24px}
a{display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#7c3aed,#2563eb);
  color:#fff;text-decoration:none;border-radius:10px;font-weight:600}
</style></head>
<body><div class="c">
  <div class="icon">&#128274;</div>
  <h1>Login Required</h1>
  <p>You must be logged in to access<br><strong>""" + app_name + """</strong></p>
  <a href="/login">Sign In</a>
  <p style="font-size:12px;color:rgba(255,255,255,0.25);margin-top:16px">Redirecting in 2 seconds...</p>
</div></body></html>"""
    return Response(html, status=403, mimetype="text/html")

# ==============================================================================
# PROXY ROUTES
# ==============================================================================

@app.route("/fraud",             methods=["GET","POST","PUT","DELETE"])
@app.route("/fraud/",            methods=["GET","POST","PUT","DELETE"])
@app.route("/fraud/<path:path>", methods=["GET","POST","PUT","DELETE"])
def fraud_proxy(path=""):
    if not logged_in():
        return _blocked("FraudGuard - Financial Fraud Detection")
    return _proxy(FRAUD_BASE, path)

@app.route("/spam",             methods=["GET","POST","PUT","DELETE"])
@app.route("/spam/",            methods=["GET","POST","PUT","DELETE"])
@app.route("/spam/<path:path>", methods=["GET","POST","PUT","DELETE"])
def spam_proxy(path=""):
    if not logged_in():
        return _blocked("SpamShield - Email Spam Classifier")
    return _proxy(SPAM_BASE, path)

# ==============================================================================
if __name__ == "__main__":
    print("")
    print("=" * 52)
    print("  SentinelLedger  : http://localhost:8000")
    print("  Login           : http://localhost:8000/login")
    print("  Register        : http://localhost:8000/register")
    print("  Home            : http://localhost:8000/home")
    print("  Dashboard       : http://localhost:8000/dashboard")
    print("  Admin Panel     : http://localhost:8000/admin")
    print("  FraudGuard      : http://localhost:8000/fraud/")
    print("  SpamShield      : http://localhost:8000/spam/")
    print("=" * 52)
    print("")
    app.run(host="0.0.0.0", port=8000, debug=True, threaded=True)
