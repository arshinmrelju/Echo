import contextlib
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional
import uuid
from echo.core.config import get_settings


SCHEMA_MIGRATIONS = [
    # Migration 1: Initial schema for conversations, messages, settings, tasks, memory, action_logs
    """
    -- Conversations
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT
    );

    -- Messages
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
        content TEXT NOT NULL,
        token_count INTEGER,
        created_at TEXT NOT NULL,
        metadata TEXT
    );

    -- Settings Key-Value Store
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    -- Tasks Table
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        conversation_id TEXT REFERENCES conversations(id),
        goal TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('created', 'planning', 'in_progress', 'completed', 'failed', 'cancelled')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT
    );

    -- Memory Entries
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL CHECK(category IN ('fact', 'project', 'preference', 'context')),
        key TEXT NOT NULL,
        content TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        sensitivity TEXT DEFAULT 'normal' CHECK(sensitivity IN ('normal', 'high')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    -- Standalone Full Text Search for Memory
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        id UNINDEXED,
        key,
        content,
        category
    );

    -- Action Logs (Audit Trail)
    CREATE TABLE IF NOT EXISTS action_logs (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        details TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """
]


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = get_settings().db_path
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
            isolation_level=None,  # autocommit mode, transactions via explicit BEGIN
        )
        conn.row_factory = sqlite3.Row
        # Configure WAL mode and performance pragmas
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            conn.execute("BEGIN;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.get_connection() as conn:
            # Check schema version
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
            )
            cur = conn.execute("SELECT MAX(version) FROM schema_version;")
            row = cur.fetchone()
            current_version = row[0] if row and row[0] is not None else 0

            for idx, migration_sql in enumerate(SCHEMA_MIGRATIONS, start=1):
                if idx > current_version:
                    conn.executescript(migration_sql)
                    now_str = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                        (idx, now_str),
                    )


_global_database: Optional[Database] = None


def get_database() -> Database:
    global _global_database
    if _global_database is None:
        _global_database = Database()
    return _global_database
