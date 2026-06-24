import mysql.connector
import os

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "mysql-kuif.railway.internal"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "smbIROLNRlRhchdzTGuNaqNWdHkBKaay")
}

def setup():
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    db_name = os.environ.get("DB_DATABASE", "railway")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE {db_name}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            username   VARCHAR(80)  NOT NULL UNIQUE,
            email      VARCHAR(120) NOT NULL UNIQUE,
            password   VARCHAR(255) NOT NULL,
            role       ENUM('analyst','admin','auditor') DEFAULT 'analyst',
            is_active  TINYINT(1) DEFAULT 1,
            last_login DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_sessions (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT NOT NULL,
            ip_address VARCHAR(45),
            login_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_logins (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            email        VARCHAR(120),
            ip_address   VARCHAR(45),
            attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT,
            action     VARCHAR(120) NOT NULL,
            detail     TEXT,
            ip_address VARCHAR(45),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            alert_type      ENUM('email','transaction') NOT NULL,
            decision        VARCHAR(20) NOT NULL,
            score           FLOAT NOT NULL,
            blockchain_hash VARCHAR(64),
            user_id         INT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    # Upgrade existing DB: add last_login if missing
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_login DATETIME NULL AFTER is_active")
    except Exception:
        pass

    # Upgrade existing DB: add user_id to alerts if missing
    try:
        cursor.execute("ALTER TABLE alerts ADD COLUMN user_id INT NULL")
    except Exception:
        pass

    # Add FK constraint on alerts.user_id if not already there (safe to fail if exists)
    try:
        cursor.execute("ALTER TABLE alerts ADD CONSTRAINT fk_alerts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL")
    except Exception:
        pass

    conn.commit()
    cursor.close()
    conn.close()
    print("[OK] Database 'railway' and all tables are ready.")

if __name__ == "__main__":
    setup()
