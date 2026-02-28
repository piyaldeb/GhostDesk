"""
GhostPC Memory Layer
SQLite-backed persistent memory for commands, notes, schedules, credentials, and conversations.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    from config import DB_PATH
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    user_input  TEXT    NOT NULL,
    ai_thought  TEXT,
    actions_taken TEXT,
    result      TEXT,
    success     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    tags        TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_expression TEXT    NOT NULL,
    command_text    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    last_run        TEXT,
    active          INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS api_credentials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name    TEXT    NOT NULL UNIQUE,
    credential_type TEXT    NOT NULL,
    credential_value TEXT   NOT NULL,
    added_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    contact     TEXT,
    message     TEXT    NOT NULL,
    direction   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS screen_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    screenshot_path TEXT    NOT NULL,
    ai_summary      TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
    USING fts5(title, content, tags, content='notes', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content, tags) VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags) VALUES('delete', old.id, old.title, old.content, old.tags);
END;
"""


def init_db():
    """Initialize the database and create all tables."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info(f"Database initialized at {get_db_path()}")


# ─── Command Logging ─────────────────────────────────────────────────────────

def log_command(
    user_input: str,
    thought: str = "",
    actions: Any = None,
    result: str = "",
    success: bool = True
) -> int:
    """Log every command the user sends and the agent's response."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO commands (timestamp, user_input, ai_thought, actions_taken, result, success)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                user_input,
                thought,
                json.dumps(actions) if actions else "",
                result,
                1 if success else 0,
            )
        )
        return cur.lastrowid


def get_recent_commands(n: int = 10) -> list[dict]:
    """Return the last N commands for AI context injection."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM commands ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ─── Notes ───────────────────────────────────────────────────────────────────

def save_note(title: str, content: str, tags: str = "") -> int:
    """Save a note to memory."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO notes (timestamp, title, content, tags) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), title, content, tags)
        )
        return cur.lastrowid


def get_notes(limit: int = 20) -> list[dict]:
    """Get recent notes."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_note(note_id: int) -> bool:
    """Delete a note by ID."""
    with get_connection() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return True


# ─── Full-Text Search ─────────────────────────────────────────────────────────

def search_memory(query: str) -> dict:
    """Full-text search across notes, commands, and conversations."""
    results = {"notes": [], "commands": [], "conversations": []}

    with get_connection() as conn:
        # Search notes via FTS
        try:
            rows = conn.execute(
                "SELECT * FROM notes WHERE id IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)",
                (query,)
            ).fetchall()
            results["notes"] = [dict(r) for r in rows]
        except Exception:
            # Fallback to LIKE if FTS fails
            rows = conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? OR content LIKE ?",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
            results["notes"] = [dict(r) for r in rows]

        # Search commands
        rows = conn.execute(
            "SELECT * FROM commands WHERE user_input LIKE ? OR result LIKE ? ORDER BY id DESC LIMIT 20",
            (f"%{query}%", f"%{query}%")
        ).fetchall()
        results["commands"] = [dict(r) for r in rows]

        # Search conversations
        rows = conn.execute(
            "SELECT * FROM conversations WHERE message LIKE ? ORDER BY id DESC LIMIT 20",
            (f"%{query}%",)
        ).fetchall()
        results["conversations"] = [dict(r) for r in rows]

    return results


# ─── Schedules ───────────────────────────────────────────────────────────────

def save_schedule(cron_expression: str, command_text: str) -> int:
    """Save a new scheduled task."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO schedules (cron_expression, command_text, created_at) VALUES (?, ?, ?)",
            (cron_expression, command_text, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_active_schedules() -> list[dict]:
    """Get all active schedules."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE active = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_schedule(schedule_id: int) -> bool:
    """Delete a schedule."""
    with get_connection() as conn:
        conn.execute("UPDATE schedules SET active = 0 WHERE id = ?", (schedule_id,))
    return True


def update_schedule_last_run(schedule_id: int):
    """Update last_run timestamp for a schedule."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE schedules SET last_run = ? WHERE id = ?",
            (datetime.now().isoformat(), schedule_id)
        )


# ─── API Credentials ─────────────────────────────────────────────────────────

def save_api_credential(service_name: str, credential_type: str, credential_value: str) -> int:
    """Store an API credential. Overwrites if service already exists."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO api_credentials (service_name, credential_type, credential_value, added_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(service_name) DO UPDATE SET
                 credential_type = excluded.credential_type,
                 credential_value = excluded.credential_value,
                 added_at = excluded.added_at""",
            (service_name.lower(), credential_type, credential_value, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_api_credential(service_name: str) -> Optional[dict]:
    """Retrieve a stored credential by service name."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_credentials WHERE service_name = ?",
            (service_name.lower(),)
        ).fetchone()
    return dict(row) if row else None


def list_api_credentials() -> list[dict]:
    """List all stored credential service names (not values)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, service_name, credential_type, added_at FROM api_credentials"
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Conversations ────────────────────────────────────────────────────────────

def log_conversation(source: str, contact: str, message: str, direction: str = "in"):
    """Log a conversation message (WhatsApp, email, etc.)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (timestamp, source, contact, message, direction) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), source, contact, message, direction)
        )


def get_conversation_history(contact: str, source: str, days: int = 2) -> list[dict]:
    """
    Fetch the last N days of conversation with a specific contact on a given source.
    Returns messages ordered oldest → newest for natural reading in AI prompts.
    """
    from datetime import timedelta
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT timestamp, direction, message FROM conversations
               WHERE contact = ? AND source = ? AND timestamp >= ?
               ORDER BY timestamp ASC
               LIMIT 100""",
            (contact, source, since)
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Screen Log ──────────────────────────────────────────────────────────────

def log_screenshot(screenshot_path: str, ai_summary: str = ""):
    """Log a screenshot entry."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO screen_log (timestamp, screenshot_path, ai_summary) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), screenshot_path, ai_summary)
        )


# ─── Context Builder for AI ──────────────────────────────────────────────────

def build_memory_context(n_commands: int = 10) -> str:
    """Build a concise memory context string to inject into AI prompts."""
    recent = get_recent_commands(n_commands)
    if not recent:
        return "No previous commands."

    lines = ["Recent commands:"]
    for cmd in recent:
        status = "✓" if cmd["success"] else "✗"
        ts = cmd["timestamp"][:16].replace("T", " ")
        lines.append(f"  [{ts}] {status} {cmd['user_input'][:100]}")

    return "\n".join(lines)
