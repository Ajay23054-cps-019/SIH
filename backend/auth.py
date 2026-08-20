import os
import sqlite3
import threading
import secrets
import hashlib
from datetime import datetime, timedelta

_AUTH_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "sysmon")
_AUTH_DB = os.path.join(_AUTH_DIR, "auth.db")
_TOKEN_EXPIRY_HOURS = 24
_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(_AUTH_DIR, exist_ok=True)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_auth():
    _ensure_dir()
    with sqlite3.connect(_AUTH_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tokens_expires ON tokens(expires_at)")
        conn.commit()


def create_default_admin():
    init_auth()
    with _lock:
        with sqlite3.connect(_AUTH_DB) as conn:
            row = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
            if row:
                return None
            password = secrets.token_hex(8)
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", _hash_password(password)),
            )
            conn.commit()
            with open(os.path.join(_AUTH_DIR, ".admin_credentials"), "w") as f:
                f.write(f"Username: admin\nPassword: {password}\n")
            return password


def print_startup_credentials():
    init_auth()
    creds_file = os.path.join(_AUTH_DIR, ".admin_credentials")
    if os.path.exists(creds_file):
        with open(creds_file) as f:
            print(f.read())
    else:
        password = create_default_admin()
        if password:
            print("=" * 50)
            print("DEFAULT ADMIN CREDENTIALS")
            print("Username: admin")
            print("Password: " + password)
            print("=" * 50)
        else:
            print("Admin user already exists. Use existing credentials to log in.")


def validate_user(username: str, password: str):
    init_auth()
    with sqlite3.connect(_AUTH_DB) as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if not row:
            return None
        user_id, stored_hash = row
        if stored_hash != _hash_password(password):
            return None
        token = secrets.token_hex(32)
        now = datetime.utcnow()
        expires = now + timedelta(hours=_TOKEN_EXPIRY_HOURS)
        conn.execute(
            "INSERT INTO tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires.isoformat()),
        )
        conn.commit()
        return token


def validate_token(token: str):
    if not token:
        return None
    token = token.replace("Bearer ", "").strip()
    init_auth()
    with sqlite3.connect(_AUTH_DB) as conn:
        row = conn.execute(
            "SELECT t.user_id, t.expires_at, u.username FROM tokens t JOIN users u ON t.user_id = u.id WHERE t.token=?",
            (token,),
        ).fetchone()
        if not row:
            return None
        user_id, expires_at, username = row
        if datetime.utcnow() > datetime.fromisoformat(expires_at):
            conn.execute("DELETE FROM tokens WHERE token=?", (token,))
            conn.commit()
            return None
        return {"user_id": user_id, "username": username}


def create_user(username: str, password: str):
    init_auth()
    with _lock:
        with sqlite3.connect(_AUTH_DB) as conn:
            try:
                conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, _hash_password(password)),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False


def revoke_token(token: str):
    init_auth()
    with sqlite3.connect(_AUTH_DB) as conn:
        conn.execute("DELETE FROM tokens WHERE token=?", (token,))
        conn.commit()


def cleanup_expired_tokens():
    init_auth()
    with sqlite3.connect(_AUTH_DB) as conn:
        conn.execute("DELETE FROM tokens WHERE expires_at < ?", (datetime.utcnow().isoformat(),))
        conn.commit()
