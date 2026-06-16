CREATE DATABASE IF NOT EXISTS sentinelledger CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sentinelledger;

CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(80)  NOT NULL UNIQUE,
    email       VARCHAR(120) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    role        ENUM('analyst','admin','auditor') DEFAULT 'analyst',
    is_active   TINYINT(1) DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_sessions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    ip_address  VARCHAR(45),
    login_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    alert_type      ENUM('email','transaction') NOT NULL,
    decision        VARCHAR(20) NOT NULL,
    score           FLOAT NOT NULL,
    blockchain_hash VARCHAR(64),
    user_id         INT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

SHOW TABLES;
