from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import timedelta
import mysql.connector
import csv, io

app = Flask(__name__)
app.secret_key = "sentinelledger_secret_2025"
app.permanent_session_lifetime = timedelta(hours=8)
bcrypt = Bcrypt(app)

DB_CONFIG = {
    "host":     "mysql-kuif.railway.internal",
    "port":     3306,
    "user":     "root",
    "password": "smbIROLNRlRhchdzTGuNaqNWdHkBKaay",
    "database": "railway"
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def log_activity(user_id, action, detail=""):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO activity_logs (user_id, action, detail, ip_address) VALUES (%s,%s,%s,%s)",
            (user_id, action, detail, request.remote_addr)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "danger")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Access denied. Admins only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

# ── Public ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("home") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        email    = request.form["email"].strip()
        password = request.form["password"]
        conn     = get_db()
        cursor   = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and bcrypt.check_password_hash(user["password"], password):
            if not user["is_active"]:
                flash("Account suspended. Contact admin.", "danger")
                cursor.close(); conn.close()
                return render_template("login.html")
            session.permanent  = True
            session["user_id"] = user["id"]
            session["username"]= user["username"]
            session["role"]    = user["role"]
            cursor.execute("INSERT INTO login_sessions (user_id, ip_address) VALUES (%s,%s)",
                           (user["id"], request.remote_addr))
            cursor.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user["id"],))
            conn.commit(); cursor.close(); conn.close()
            log_activity(user["id"], "LOGIN", f"IP: {request.remote_addr}")
            flash(f"Welcome, {user['username']}!", "success")
            if user["role"] == "admin":
                return redirect(url_for("admin"))
            return redirect(url_for("home"))

        try:
            cursor.execute("INSERT INTO failed_logins (email, ip_address) VALUES (%s,%s)",
                           (email, request.remote_addr))
            conn.commit()
        except Exception:
            pass
        cursor.close(); conn.close()
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
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
            conn   = get_db()
            cursor = conn.cursor()
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
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    log_activity(session.get("user_id"), "LOGOUT", "User logged out")
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

# ── User ──────────────────────────────────────────────────────────────────────

@app.route("/home")
@login_required
def home():
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM alerts WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",
                   (session["user_id"],))
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
        username=session["username"], role=session["role"])

@app.route("/dashboard")
@login_required
def dashboard():
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM alerts WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",
                   (session["user_id"],))
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
        username=session["username"], role=session["role"])

# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin():
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS c FROM users")
    total_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM users WHERE is_active=1")
    active_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM users WHERE DATE(created_at)=CURDATE()")
    new_today = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM login_sessions WHERE DATE(login_at)=CURDATE()")
    logins_today = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM failed_logins WHERE DATE(attempted_at)=CURDATE()")
    failed_today = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM login_sessions")
    total_logins = cursor.fetchone()["c"]

    cursor.execute("""
        SELECT al.*, u.username FROM activity_logs al
        LEFT JOIN users u ON al.user_id=u.id
        ORDER BY al.created_at DESC LIMIT 15
    """)
    recent_activity = cursor.fetchall()

    search   = request.args.get("search", "").strip()
    role_f   = request.args.get("role_filter", "")
    status_f = request.args.get("status_filter", "")
    q = "SELECT * FROM users WHERE 1=1"
    p = []
    if search:
        q += " AND (username LIKE %s OR email LIKE %s)"
        p += [f"%{search}%", f"%{search}%"]
    if role_f:
        q += " AND role=%s"; p.append(role_f)
    if status_f != "":
        q += " AND is_active=%s"; p.append(int(status_f))
    q += " ORDER BY created_at DESC"
    cursor.execute(q, p)
    users = cursor.fetchall()

    cursor.execute("""
        SELECT DATE(created_at) AS day, COUNT(*) AS cnt FROM users
        WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
        GROUP BY DATE(created_at) ORDER BY day
    """)
    reg_chart = cursor.fetchall()

    cursor.execute("""
        SELECT DATE(login_at) AS day, COUNT(*) AS cnt FROM login_sessions
        WHERE login_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
        GROUP BY DATE(login_at) ORDER BY day
    """)
    login_chart = cursor.fetchall()

    cursor.execute("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
    role_chart = cursor.fetchall()

    cursor.execute("""
        SELECT ls.*, u.username FROM login_sessions ls
        LEFT JOIN users u ON ls.user_id=u.id
        ORDER BY ls.login_at DESC LIMIT 20
    """)
    login_history = cursor.fetchall()

    cursor.execute("SELECT * FROM failed_logins ORDER BY attempted_at DESC LIMIT 20")
    failed_logins = cursor.fetchall()

    cursor.close(); conn.close()
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
    role     = request.form.get("role", "analyst")
    hashed   = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        conn   = get_db(); cursor = conn.cursor()
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
    conn     = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET username=%s, email=%s, role=%s WHERE id=%s",
                   (username, email, role, uid))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_EDIT_USER", f"Edited user id={uid}")
    flash("User updated.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/toggle/<int:uid>")
@admin_required
def admin_toggle_user(uid):
    if uid == session["user_id"]:
        flash("Cannot suspend your own account.", "danger")
        return redirect(url_for("admin"))
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT is_active, username FROM users WHERE id=%s", (uid,))
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
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
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
    conn   = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (hashed, uid))
    conn.commit(); cursor.close(); conn.close()
    log_activity(session["user_id"], "ADMIN_RESET_PW", f"Reset password uid={uid}")
    flash("Password reset successfully.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/export/users")
@admin_required
def admin_export_users():
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id,username,email,role,is_active,last_login,created_at FROM users ORDER BY created_at DESC")
    rows   = cursor.fetchall(); cursor.close(); conn.close()
    si     = io.StringIO()
    cw     = csv.DictWriter(si, fieldnames=["id","username","email","role","is_active","last_login","created_at"])
    cw.writeheader(); cw.writerows(rows)
    log_activity(session["user_id"], "EXPORT_USERS", "CSV export")
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=users_export.csv"})

@app.route("/admin/export/activity")
@admin_required
def admin_export_activity():
    conn   = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT al.id, u.username, al.action, al.detail, al.ip_address, al.created_at
        FROM activity_logs al LEFT JOIN users u ON al.user_id=u.id
        ORDER BY al.created_at DESC
    """)
    rows   = cursor.fetchall(); cursor.close(); conn.close()
    si     = io.StringIO()
    cw     = csv.DictWriter(si, fieldnames=["id","username","action","detail","ip_address","created_at"])
    cw.writeheader(); cw.writerows(rows)
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=activity_export.csv"})

if __name__ == "__main__":
    print("\n" + "="*52)
    print("  SentinelLedger  →  http://localhost:4999")
    print("  Admin Panel     →  http://localhost:4999/admin")
    print("  Login           →  http://localhost:4999/login")
    print("="*52 + "\n")
    app.run(debug=True, port=4999)
