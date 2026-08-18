import sqlite3
from datetime import datetime
import threading
import json
import os


_db_path = "system_metrics.db"
_log_path = "metrics_log.json"
_lock = threading.Lock()
_max_rows = 500


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

    _maybe_cleanup()


def get_latest(limit=60):
    with _lock:
        with sqlite3.connect(_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM metrics ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _maybe_cleanup():
    with sqlite3.connect(_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        if count < _max_rows:
            return

        excess = count - _max_rows + 1
        rows = conn.execute(
            "SELECT * FROM metrics ORDER BY id ASC LIMIT ?",
            (excess,),
        ).fetchall()

    if not rows:
        return

    logs = []
    for row in rows:
        logs.append({
            "timestamp": row[1],
            "cpu": row[2],
            "ram_used": row[3],
            "ram_total": row[4],
            "ram_percent": row[5],
            "bytes_sent": row[6],
            "bytes_received": row[7],
        })

    if logs:
        with open(_log_path, "a") as f:
            for entry in logs:
                f.write(json.dumps(entry) + "\n")

    ids = [str(row[0]) for row in rows]
    with sqlite3.connect(_db_path) as conn:
        conn.execute(
            f"DELETE FROM metrics WHERE id IN ({','.join(ids)})"
        )
        conn.commit()
