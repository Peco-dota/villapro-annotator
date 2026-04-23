"""SQLite user database for VisionQ authentication.

Schema:
    users(id, username, hashed_password, role, created_at)

Roles: 'admin' | 'customer'

On first startup, two default users are seeded:
    admin    / admin123   (role=admin)
    customer / customer123 (role=customer)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import bcrypt as _bcrypt


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _check_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

DB_PATH = Path.home() / ".config" / "visionq_users.db"

_DEFAULT_USERS = [
    ("admin",    "admin123",    "admin"),
    ("customer", "customer123", "customer"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            username         TEXT    NOT NULL UNIQUE,
            hashed_password  TEXT    NOT NULL,
            role             TEXT    NOT NULL DEFAULT 'customer',
            created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Seed default users if table is empty
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        for username, password, role in _DEFAULT_USERS:
            hashed = _hash_password(password)
            conn.execute(
                "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
                (username, hashed, role),
            )
        conn.commit()
    conn.close()


def get_user(username: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT id, username, hashed_password, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def verify_password(plain: str, hashed: str) -> bool:
    return _check_password(plain, hashed)


def update_password(username: str, new_password: str) -> bool:
    conn = _connect()
    hashed = _hash_password(new_password)
    cur = conn.execute(
        "UPDATE users SET hashed_password = ? WHERE username = ?",
        (hashed, username),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_users() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT id, username, role, created_at FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]
