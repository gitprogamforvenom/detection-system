import subprocess
import os
import sys
import time

print("Starting production services manager...")

# 1. Start FraudGuard internally on port 5000
print("Launching FraudGuard backend on port 5000...")
fg_proc = subprocess.Popen([
    "gunicorn",
    "--chdir", "pbi card",
    "--bind", "127.0.0.1:5000",
    "--workers", "1",
    "--timeout", "120",
    "app:app"
])

# 2. Start SpamShield internally on port 5001
print("Launching SpamShield backend on port 5001...")
ss_proc = subprocess.Popen([
    "gunicorn",
    "--chdir", "Spam-Detection-Classifier-main/Spam-Detection-Classifier-main/spam_detection",
    "--bind", "127.0.0.1:5001",
    "--workers", "1",
    "--timeout", "120",
    "spam_detection.wsgi:application"
])

# 3. Start Gateway publicly on Render-assigned port
port = os.environ.get("PORT", "8000")
print(f"Launching SentinelLedger Gateway on public port {port}...")

try:
    # Boot the gateway in the foreground
    subprocess.run([
        "gunicorn",
        "--chdir", "launcher",
        "--bind", f"0.0.0.0:{port}",
        "--workers", "2",
        "--timeout", "120",
        "serve:app"
    ], check=True)
except KeyboardInterrupt:
    print("Shutting down production manager...")
finally:
    fg_proc.terminate()
    ss_proc.terminate()
    fg_proc.wait()
    ss_proc.wait()
    print("All backend processes stopped.")
