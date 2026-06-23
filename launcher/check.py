import os, sys

print("\n" + "="*60)
print("  SENTINELLEDGER - FULL DIAGNOSTICS")
print("="*60)

BASE    = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
TMPL    = os.path.join(PROJECT, 'auth', 'templates')
IDX     = os.path.join(BASE, 'index.html')

print("\n[1] FOLDER & FILE PATHS")
checks = [
    ("launcher/",            BASE),
    ("project/",             PROJECT),
    ("auth/templates/",      TMPL),
    ("launcher/index.html",  IDX),
    ("auth/app.py",          os.path.join(PROJECT,'auth','app.py')),
    ("auth/db_setup.py",     os.path.join(PROJECT,'auth','db_setup.py')),
    ("run_all.bat",          os.path.join(PROJECT,'run_all.bat')),
    ("templates/login.html", os.path.join(TMPL,'login.html')),
    ("templates/register",   os.path.join(TMPL,'register.html')),
    ("templates/dashboard",  os.path.join(TMPL,'dashboard.html')),
]
all_ok = True
for label, path in checks:
    ok = os.path.exists(path)
    status = "OK  " if ok else "MISSING"
    print(f"  {status}  {label}")
    if not ok:
        all_ok = False

print("\n[2] MYSQL CONNECTION")
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host="mysql-kuif.railway.internal", port=3306,
        user="root", password="Vem12345@",
        database="railway"
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    print(f"  OK   Connected to MySQL port 3306")
    print(f"  OK   Database: railway")
    print(f"  OK   Tables: {tables}")

    # check columns
    cur.execute("SHOW COLUMNS FROM users")
    cols = [r[0] for r in cur.fetchall()]
    needed = ['id','username','email','password','role','is_active','created_at']
    for col in needed:
        status = "OK  " if col in cols else "MISSING"
        print(f"       users.{col} -> {status}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"  FAIL  MySQL error: {e}")
    all_ok = False

print("\n[3] PYTHON PACKAGES")
packages = ['flask','flask_bcrypt','mysql.connector','requests']
for pkg in packages:
    try:
        __import__(pkg)
        print(f"  OK   {pkg}")
    except ImportError:
        print(f"  MISSING  {pkg}  --> run: pip install {pkg}")
        all_ok = False

print("\n[4] PORT AVAILABILITY")
import socket
for port, name in [(8000,'Gateway'),(5000,'FraudGuard'),(5001,'SpamShield')]:
    s = socket.socket()
    s.settimeout(1)
    result = s.connect_ex(('127.0.0.1', port))
    s.close()
    status = "RUNNING" if result == 0 else "NOT running"
    print(f"  {status}  Port {port} ({name})")

print("\n[5] SERVE.PY IMPORT TEST")
try:
    sys.path.insert(0, BASE)
    import serve
    print(f"  OK   serve.py imports without errors")
    print(f"  OK   template_folder = {serve.app.template_folder}")
    print(f"  OK   secret_key set  = {'yes' if serve.app.secret_key else 'NO'}")
except Exception as e:
    print(f"  FAIL  {e}")
    all_ok = False

print("\n" + "="*60)
print("  RESULT:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED - see above")
print("="*60 + "\n")
