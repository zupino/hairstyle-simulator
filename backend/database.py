"""
SQLite database initialisation and helper functions.

All queries use the stdlib sqlite3 module — no ORM.
The database file is created automatically on first startup.
"""

import sqlite3
import os
from contextlib import contextmanager
from backend import config


def _db_path() -> str:
    return config.DB_PATH


def init_db() -> None:
    """Create tables if they do not already exist."""
    os.makedirs(os.path.dirname(os.path.abspath(_db_path())), exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            PRAGMA journal_mode=WAL;


            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT    UNIQUE NOT NULL,
                password_hash TEXT   NOT NULL,
                role         TEXT    NOT NULL CHECK(role IN ('admin', 'operator')),
                is_active    INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hairstyles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                filename    TEXT    UNIQUE NOT NULL,
                uploaded_by INTEGER NOT NULL REFERENCES users(id),
                created_at  TEXT    NOT NULL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id              TEXT PRIMARY KEY,
                bfl_request_id  TEXT NOT NULL,
                bfl_polling_url TEXT NOT NULL,
                operator_id     INTEGER NOT NULL REFERENCES users(id),
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL
            );
        """)
    _apply_migrations()


def _apply_migrations() -> None:
    """Incremental schema migrations for existing databases.

    Each statement is idempotent: it catches the OperationalError SQLite raises
    when a column already exists, so running this on a fresh database or one
    that already has the column is equally safe.
    """
    with _connect() as conn:
        try:
            conn.execute("ALTER TABLE hairstyles ADD COLUMN description TEXT")
        except sqlite3.OperationalError:
            pass  # column already present


@contextmanager
def _connect():
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def get_user_by_username(username: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def create_user(username: str, password_hash: str, role: str, created_at: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (username, password_hash, role, created_at),
        )
        return cur.lastrowid


def list_operators() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE role = 'operator'"
        ).fetchall()


def update_operator(user_id: int, is_active: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ? AND role = 'operator'",
            (is_active, user_id),
        )
        return cur.rowcount > 0


def delete_operator(user_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM users WHERE id = ? AND role = 'operator'", (user_id,)
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Hairstyle helpers
# ---------------------------------------------------------------------------

def create_hairstyle(
    name: str,
    filename: str,
    uploaded_by: int,
    created_at: str,
    description: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO hairstyles (name, filename, uploaded_by, created_at, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, filename, uploaded_by, created_at, description),
        )
        return cur.lastrowid


def update_hairstyle_description(hairstyle_id: int, description: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE hairstyles SET description = ? WHERE id = ?",
            (description, hairstyle_id),
        )


def list_hairstyles() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM hairstyles ORDER BY created_at DESC").fetchall()


def get_hairstyle(hairstyle_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM hairstyles WHERE id = ?", (hairstyle_id,)
        ).fetchone()


def delete_hairstyle(hairstyle_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM hairstyles WHERE id = ?", (hairstyle_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def create_job(
    job_id: str,
    bfl_request_id: str,
    bfl_polling_url: str,
    operator_id: int,
    created_at: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, bfl_request_id, bfl_polling_url, operator_id, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (job_id, bfl_request_id, bfl_polling_url, operator_id, created_at),
        )


def get_job(job_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def update_job_status(job_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def delete_job(job_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def bootstrap_admin(username: str, password_hash: str) -> None:
    """Concurrent starts must neither duplicate accounts nor overwrite credentials."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users(username,password_hash,role,created_at) "
            "VALUES (?,?,'admin',CURRENT_TIMESTAMP) ON CONFLICT(username) DO NOTHING",
            (username, password_hash),
        )
