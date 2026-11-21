import contextlib
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, Optional
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
    """,
    # Migration 2: System monitoring alerts and event feed
    """
    -- Alert lifecycle. Only one active alert may exist per dedupe key; a new
    -- alert can be opened after the previous one has recovered or resolved.
    CREATE TABLE IF NOT EXISTS monitor_alerts (
        id TEXT PRIMARY KEY,
        dedupe_key TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL CHECK(severity IN ('info', 'notice', 'warning', 'critical')),
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        details TEXT,
        status TEXT NOT NULL CHECK(status IN ('active', 'recovered', 'resolved')),
        source TEXT NOT NULL DEFAULT 'system',
        occurrences INTEGER NOT NULL DEFAULT 1,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        last_notified_at TEXT NOT NULL,
        last_escalated_at TEXT,
        acknowledged_at TEXT,
        recovered_at TEXT,
        resolved_at TEXT,
        escalation_level INTEGER NOT NULL DEFAULT 0
    );

    CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_alerts_active
        ON monitor_alerts(dedupe_key) WHERE status = 'active';
    CREATE INDEX IF NOT EXISTS ix_monitor_alerts_status
        ON monitor_alerts(status, last_seen_at DESC);
    CREATE INDEX IF NOT EXISTS ix_monitor_alerts_dedupe
        ON monitor_alerts(dedupe_key, status);

    -- Raw event feed: Windows events, app transitions, connectivity changes,
    -- alert lifecycle entries. dedupe_key prevents duplicate ingestion.
    CREATE TABLE IF NOT EXISTS monitor_events (
        id TEXT PRIMARY KEY,
        dedupe_key TEXT,
        category TEXT NOT NULL,
        severity TEXT NOT NULL CHECK(severity IN ('info', 'notice', 'warning', 'critical')),
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        details TEXT,
        alert_id TEXT,
        occurred_at TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    );

    CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_events_dedupe
        ON monitor_events(dedupe_key) WHERE dedupe_key IS NOT NULL;
    CREATE INDEX IF NOT EXISTS ix_monitor_events_time
        ON monitor_events(occurred_at DESC);
    CREATE INDEX IF NOT EXISTS ix_monitor_events_category
        ON monitor_events(category, occurred_at DESC);
    """,
    # Migration 3: Remote relay (Telegram channel, pairing, audit, delivery queue)
    """
    -- Telegram identities allowed to talk to ECHO. The owner row is the only
    -- account permitted to run dangerous commands or receive screenshots.
    CREATE TABLE IF NOT EXISTS remote_users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        display_name TEXT,
        role TEXT NOT NULL CHECK(role IN ('owner', 'allowed')),
        paired_at TEXT NOT NULL,
        last_seen_at TEXT,
        added_by TEXT NOT NULL DEFAULT 'pairing'
    );

    -- Short-lived one-time pairing codes. Only the hash of the code is stored.
    CREATE TABLE IF NOT EXISTS remote_pairing_codes (
        code_hash TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        used_by INTEGER
    );

    CREATE INDEX IF NOT EXISTS ix_remote_pairing_expiry
        ON remote_pairing_codes(expires_at);

    -- Every accepted, rejected, or failed remote command is audited here.
    CREATE TABLE IF NOT EXISTS remote_commands (
        id TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        username TEXT,
        command TEXT NOT NULL,
        args TEXT,
        status TEXT NOT NULL,
        response TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    );

    CREATE INDEX IF NOT EXISTS ix_remote_commands_time
        ON remote_commands(created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_remote_commands_user
        ON remote_commands(telegram_id, created_at DESC);

    -- Outbound notification queue. Rows stay queued while Telegram is
    -- unreachable and are collapsed/expired on reconnect to avoid floods.
    CREATE TABLE IF NOT EXISTS remote_notifications (
        id TEXT PRIMARY KEY,
        dedupe_key TEXT,
        category TEXT NOT NULL,
        severity TEXT NOT NULL CHECK(severity IN ('info', 'notice', 'warning', 'critical')),
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        payload TEXT,
        status TEXT NOT NULL CHECK(status IN ('queued', 'sending', 'sent', 'failed', 'expired', 'suppressed')),
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        expires_at TEXT,
        last_error TEXT
    );

    CREATE INDEX IF NOT EXISTS ix_remote_notifications_due
        ON remote_notifications(status, next_attempt_at);
    CREATE INDEX IF NOT EXISTS ix_remote_notifications_dedupe
        ON remote_notifications(category, dedupe_key, created_at DESC);

    -- Remote task requests with their progress and final result.
    CREATE TABLE IF NOT EXISTS remote_tasks (
        id TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        goal TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('created', 'planning', 'in_progress', 'completed', 'failed', 'cancelled')),
        result TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_remote_tasks_time
        ON remote_tasks(created_at DESC);

    -- Dangerous remote actions wait for an explicit owner approval.
    CREATE TABLE IF NOT EXISTS remote_pending_actions (
        approval_id TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        arguments TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'denied', 'executed', 'expired')),
        result TEXT,
        task_id TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_remote_pending_status
        ON remote_pending_actions(status, created_at DESC);

    -- Relay state: update offset, heartbeat, paused flag, connectivity.
    CREATE TABLE IF NOT EXISTS remote_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    # Migration 4: Stage 6 memory expansion and file intelligence index
    """
    -- Rebuild memories: the original CHECK only allowed four categories.
    -- Stage 6 adds task and conversation memory plus provenance, tags, and
    -- pin/archive state. Existing rows are preserved.
    CREATE TABLE IF NOT EXISTS memories_v2 (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL CHECK(category IN (
            'fact', 'project', 'preference', 'context', 'task', 'conversation'
        )),
        key TEXT NOT NULL,
        content TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        sensitivity TEXT DEFAULT 'normal' CHECK(sensitivity IN ('normal', 'high')),
        source TEXT NOT NULL DEFAULT 'user',
        tags TEXT NOT NULL DEFAULT '[]',
        pinned INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        permission_granted INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT,
        use_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    INSERT OR IGNORE INTO memories_v2 (
        id, category, key, content, confidence, sensitivity, source, tags,
        pinned, archived, permission_granted, last_used_at, use_count,
        created_at, updated_at
    )
    SELECT
        id, category, key, content, confidence, sensitivity, 'user', '[]',
        0, 0, 0, NULL, 0, created_at, updated_at
    FROM memories;

    DROP TABLE IF EXISTS memories;
    ALTER TABLE memories_v2 RENAME TO memories;

    DROP TABLE IF EXISTS memories_fts;
    CREATE VIRTUAL TABLE memories_fts USING fts5(
        id UNINDEXED,
        key,
        content,
        category,
        tags
    );

    INSERT INTO memories_fts (id, key, content, category, tags)
    SELECT id, key, content, category, tags FROM memories;

    CREATE INDEX IF NOT EXISTS ix_memories_category
        ON memories(category, updated_at DESC);
    CREATE INDEX IF NOT EXISTS ix_memories_source
        ON memories(source, updated_at DESC);

    -- Directories the user has explicitly approved for indexing and search.
    CREATE TABLE IF NOT EXISTS approved_directories (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        label TEXT,
        recursive INTEGER NOT NULL DEFAULT 1,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        last_indexed_at TEXT
    );

    -- One row per indexed file. content_text is capped and secret-redacted.
    CREATE TABLE IF NOT EXISTS file_index (
        id TEXT PRIMARY KEY,
        directory_id TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        extension TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT 'other',
        size_bytes INTEGER NOT NULL DEFAULT 0,
        modified_at REAL,
        created_at TEXT,
        content_hash TEXT,
        content_text TEXT,
        content_status TEXT NOT NULL DEFAULT 'not_indexed',
        metadata TEXT,
        indexed_at TEXT NOT NULL,
        error TEXT
    );

    CREATE INDEX IF NOT EXISTS ix_file_index_name
        ON file_index(name);
    CREATE INDEX IF NOT EXISTS ix_file_index_extension
        ON file_index(extension);
    CREATE INDEX IF NOT EXISTS ix_file_index_category
        ON file_index(category);
    CREATE INDEX IF NOT EXISTS ix_file_index_size
        ON file_index(size_bytes DESC);
    CREATE INDEX IF NOT EXISTS ix_file_index_modified
        ON file_index(modified_at DESC);
    CREATE INDEX IF NOT EXISTS ix_file_index_hash
        ON file_index(content_hash, size_bytes);
    CREATE INDEX IF NOT EXISTS ix_file_index_directory
        ON file_index(directory_id);

    -- Audit trail for file actions. There is deliberately no delete action.
    CREATE TABLE IF NOT EXISTS file_actions (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        source_path TEXT,
        target_path TEXT,
        status TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_file_actions_time
        ON file_actions(created_at DESC);
    """,
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
