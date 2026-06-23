import mysql.connector
import socket
import urllib.request

print('=' * 52)
print('  SENTINELLEDGER - CONNECTION DIAGNOSTICS')
print('=' * 52)

all_ok = True

# 1. MySQL
print('\n[1] MySQL Database (localhost:3306)')
try:
    conn = mysql.connector.connect(
        host='mysql-kuif.railway.internal', port=3306,
        user='root', password='smbIROLNRlRhchdzTGuNaqNWdHkBKaay',
        database='railway'
    )
    cur = conn.cursor()
    cur.execute('SHOW TABLES')
    tables = [r[0] for r in cur.fetchall()]
    cur.execute('SELECT COUNT(*) FROM users')
    uc = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM activity_logs')
    ac = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM login_sessions')
    lc = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM failed_logins')
    fc = cur.fetchone()[0]
    cur.close()
    conn.close()
    print('    Status   : OK - CONNECTED')
    print('    Database : sentinelledger')
    print('    Tables   :', ', '.join(tables))
    print('    Users    :', uc)
    print('    Logins   :', lc)
    print('    Activity :', ac)
    print('    Failed   :', fc)
except Exception as e:
    print('    Status   : FAILED -', e)
    all_ok = False

# 2. Flask auth app port 4999
print('\n[2] Auth App / Admin Panel (localhost:4999)')
s = socket.socket()
s.settimeout(1)
r = s.connect_ex(('127.0.0.1', 4999))
s.close()
if r == 0:
    print('    Status   : OK - RUNNING')
    print('    Admin    : http://localhost:4999/admin')
    print('    Login    : http://localhost:4999/login')
else:
    print('    Status   : NOT RUNNING')
    print('    Fix      : cd auth && python app.py')
    all_ok = False

# 3. Launcher serve.py port 8000
print('\n[3] Launcher / Gateway (localhost:8000)')
s = socket.socket()
s.settimeout(1)
r = s.connect_ex(('127.0.0.1', 8000))
s.close()
if r == 0:
    print('    Status   : OK - RUNNING')
    print('    URL      : http://localhost:8000')
else:
    print('    Status   : NOT RUNNING')
    print('    Fix      : cd launcher && python serve.py')
    all_ok = False

# 4. FraudGuard port 5000
print('\n[4] FraudGuard ML App (localhost:5000)')
s = socket.socket()
s.settimeout(1)
r = s.connect_ex(('127.0.0.1', 5000))
s.close()
if r == 0:
    print('    Status   : OK - RUNNING')
    print('    URL      : http://localhost:5000')
else:
    print('    Status   : NOT RUNNING')
    print('    Fix      : cd "pbi card" && python app.py')
    all_ok = False

# 5. SpamShield port 5001
print('\n[5] SpamShield ML App (localhost:5001)')
s = socket.socket()
s.settimeout(1)
r = s.connect_ex(('127.0.0.1', 5001))
s.close()
if r == 0:
    print('    Status   : OK - RUNNING')
    print('    URL      : http://localhost:5001')
else:
    print('    Status   : NOT RUNNING')
    print('    Fix      : cd Spam-Detection-Classifier-main\\Spam-Detection-Classifier-main\\spam_detection && python manage.py runserver 5001')
    all_ok = False

# 6. Internet
print('\n[6] Internet / CDN Connectivity')
try:
    urllib.request.urlopen('https://fonts.googleapis.com', timeout=3)
    print('    Status   : OK - ONLINE')
    print('    CDN      : Google Fonts reachable')
except Exception:
    print('    Status   : OFFLINE - Google Fonts unreachable')
    print('    Note     : UI fonts may not load correctly')

print('\n' + '=' * 52)
if all_ok:
    print('  RESULT: ALL CHECKS PASSED')
else:
    print('  RESULT: SOME SERVICES NOT RUNNING - see above')
print('=' * 52 + '\n')
