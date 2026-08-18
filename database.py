import sqlite3
from datetime import datetime
import threading


_db_path = "system_metrics.db"
_lock = threading.Lock()


def init_db():
    with sqlite3.connect(_db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu REAL NOT NULL,
                ram_used REAL NOT NULL,
                ram_total REAL NOT NULL,
                ram_percent REAL NOT NULL,
                bytes_sent REAL NOT NULL,
                bytes_received REAL NOT NULL
            )
        """)
        conn.commit()


def insert_metrics(cpu, ram_used, ram_total, ram_percent, bytes_sent, bytes_received):
    with _lock:
        with sqlite3.connect(_db_path) as conn:
            conn.execute(
                "INSERT INTO metrics (timestamp, cpu, ram_used, ram_total, ram_percent, bytes_sent, bytes_received) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), cpu, ram_used, ram_total, ram_percent, bytes_sent, bytes_received),
            )
            conn.commit()


def get_latest(limit=60):
    with _lock:
        with sqlite3.connect(_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM metrics ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in reversed(rows)]
