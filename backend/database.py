import os
import sqlite3
from datetime import datetime
import threading
import json


_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system_metrics.db")
_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics_log.json")
_lock = threading.Lock()
_max_rows = 500
_cache = []
_max_cache = 30
_write_batch = []
_max_batch = 5


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
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()


def insert_metrics(cpu, ram_used, ram_total, ram_percent, bytes_sent, bytes_received):
    row = (
        datetime.utcnow().isoformat(),
        cpu,
        ram_used,
        ram_total,
        ram_percent,
        bytes_sent,
        bytes_received,
    )

    with _lock:
        _cache.append(row)
        if len(_cache) > _max_cache:
            del _cache[0 : len(_cache) - _max_cache]

        _write_batch.append(row)
        if len(_write_batch) < _max_batch:
            return

        batch = _write_batch[:]
        _write_batch.clear()

    with sqlite3.connect(_db_path) as conn:
        conn.executemany(
            "INSERT INTO metrics (timestamp, cpu, ram_used, ram_total, ram_percent, bytes_sent, bytes_received) VALUES (?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        conn.commit()

    _maybe_cleanup()


def get_latest(limit=30):
    with _lock:
        if _cache:
            return [
                {
                    "timestamp": r[0],
                    "cpu": r[1],
                    "ram_used": r[2],
                    "ram_total": r[3],
                    "ram_percent": r[4],
                    "bytes_sent": r[5],
                    "bytes_received": r[6],
                }
                for r in _cache[-limit:]
            ]

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

    with open(_log_path, "a") as f:
        for row in rows:
            entry = {
                "timestamp": row[1],
                "cpu": row[2],
                "ram_used": row[3],
                "ram_total": row[4],
                "ram_percent": row[5],
                "bytes_sent": row[6],
                "bytes_received": row[7],
            }
            f.write(json.dumps(entry) + "\n")

    ids = [str(row[0]) for row in rows]
    with sqlite3.connect(_db_path) as conn:
        conn.execute(
            f"DELETE FROM metrics WHERE id IN ({','.join(ids)})"
        )
        conn.commit()
