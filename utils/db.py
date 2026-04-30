"""
db.py — SQLite Database Layer for Clinical AI Platform

Handles user authentication, report storage, and retrieval.
"""

import sqlite3
import hashlib
import json
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "clinical_reports.db")


def _get_conn():
    """Get a SQLite connection with row_factory for dict-like access."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    """Create tables if they don't exist and seed demo accounts."""
    conn = _get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            psychologist_facial TEXT DEFAULT '',
            psychologist_conversation TEXT DEFAULT '',
            psychologist_conclusion TEXT DEFAULT '',
            psychiatrist_params TEXT DEFAULT '{}',
            psychiatrist_abnormalities TEXT DEFAULT '[]',
            integrated_summary TEXT DEFAULT '',
            avg_severity REAL DEFAULT 0.0,
            likely_disorder TEXT DEFAULT 'Unknown',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Seed demo accounts if they don't exist
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("demo_user", _hash_password("demo123"), "Demo Patient", "user", datetime.now().isoformat())
        )
    except sqlite3.IntegrityError:
        pass  # Already exists

    try:
        c.execute(
            "INSERT INTO users (username, password_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("demo_admin", _hash_password("admin123"), "Dr. Admin", "admin", datetime.now().isoformat())
        )
    except sqlite3.IntegrityError:
        pass  # Already exists

    conn.commit()
    conn.close()


def authenticate(username: str, password: str) -> dict | None:
    """Authenticate a user. Returns user dict or None."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, _hash_password(password))
    )
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def create_user(username: str, password: str, display_name: str, role: str = "user") -> bool:
    """Create a new user. Returns True on success, False if username exists."""
    conn = _get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, _hash_password(password), display_name, role, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def save_report(
    user_id: int,
    psychologist_facial: str = "",
    psychologist_conversation: str = "",
    psychologist_conclusion: str = "",
    psychiatrist_params: dict = None,
    psychiatrist_abnormalities: list = None,
    integrated_summary: str = "",
    avg_severity: float = 0.0,
    likely_disorder: str = "Unknown"
) -> int:
    """Save a clinical report. Returns the report ID."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO reports 
           (user_id, timestamp, psychologist_facial, psychologist_conversation, 
            psychologist_conclusion, psychiatrist_params, psychiatrist_abnormalities,
            integrated_summary, avg_severity, likely_disorder)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            datetime.now().isoformat(),
            psychologist_facial,
            psychologist_conversation,
            psychologist_conclusion,
            json.dumps(psychiatrist_params or {}),
            json.dumps(psychiatrist_abnormalities or []),
            integrated_summary,
            avg_severity,
            likely_disorder
        )
    )
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id


def update_report_integrated(report_id: int, integrated_summary: str):
    """Update the integrated summary of an existing report."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE reports SET integrated_summary = ? WHERE id = ?",
        (integrated_summary, report_id)
    )
    conn.commit()
    conn.close()


def update_report_psychiatrist(report_id: int, params: dict, abnormalities: list):
    """Update the psychiatrist data of an existing report."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE reports SET psychiatrist_params = ?, psychiatrist_abnormalities = ? WHERE id = ?",
        (json.dumps(params), json.dumps(abnormalities), report_id)
    )
    conn.commit()
    conn.close()


def update_report_severity(report_id: int, avg_severity: float):
    """Update the avg_severity of an existing report (e.g. after blending psych + psychiatrist)."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE reports SET avg_severity = ? WHERE id = ?",
        (avg_severity, report_id)
    )
    conn.commit()
    conn.close()


def get_latest_report_id(user_id: int) -> int | None:
    """Get the most recent report ID for a user."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM reports WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None


def get_reports_for_user(user_id: int) -> list[dict]:
    """Get all reports for a user, newest first."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM reports WHERE user_id = ? ORDER BY timestamp DESC",
        (user_id,)
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_all_users(role: str = "user") -> list[dict]:
    """Get all users with a given role."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role = ? ORDER BY display_name", (role,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_user_report_count(user_id: int) -> int:
    """Get the number of reports for a user."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM reports WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_user_latest_report(user_id: int) -> dict | None:
    """Get the most recent report for a user."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM reports WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
