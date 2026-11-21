"""SQLite persistence for the remote relay."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from echo.core.database import Database, get_database

logger = logging.getLogger("echo.remote.store")

REMOTE_SETTINGS_KEY = "remote_settings"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def hash_pairing_code(code: str) -> str:
    normalized = code.strip().upper()
    return hashlib.sha256(f"echo-pair:{normalized}".encode("utf-8")).hexdigest()


def _row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


class RemoteStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    @property
    def database(self) -> Database:
        return self._db

    # ------------------------------------------------------------------ #
    # Settings and state
    # ------------------------------------------------------------------ #

    def load_settings(self) -> Optional[Dict[str, Any]]:
        try:
            with self._db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?;",
                    (REMOTE_SETTINGS_KEY,),
                ).fetchone()
            if row and row["value"]:
                return json.loads(row["value"])
        except Exception as exc:
            logger.warning("Could not load remote settings: %s", exc)
        return None

    def save_settings(self, settings: Dict[str, Any]) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (REMOTE_SETTINGS_KEY, json.dumps(settings), now_iso()),
            )

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            with self._db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM remote_state WHERE key = ?;", (key,)
                ).fetchone()
            return row["value"] if row else default
        except Exception:
            return default

    def set_state(self, key: str, value: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO remote_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (key, value, now_iso()),
            )

    def get_json_state(self, key: str, default: Any = None) -> Any:
        raw = self.get_state(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default

    def set_json_state(self, key: str, value: Any) -> None:
        self.set_state(key, json.dumps(value))

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #

    def upsert_user(
        self,
        telegram_id: int,
        *,
        username: Optional[str],
        display_name: str,
        role: str,
        added_by: str = "pairing",
    ) -> Dict[str, Any]:
        stamp = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO remote_users (telegram_id, username, display_name, role, paired_at, last_seen_at, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    display_name = excluded.display_name,
                    role = excluded.role,
                    last_seen_at = excluded.last_seen_at;
                """,
                (telegram_id, username, display_name, role, stamp, stamp, added_by),
            )
            row = conn.execute(
                "SELECT * FROM remote_users WHERE telegram_id = ?;", (telegram_id,)
            ).fetchone()
        return dict(row)

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM remote_users WHERE telegram_id = ?;", (telegram_id,)
            ).fetchone()
        return _row(row)

    def list_users(self) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM remote_users ORDER BY role ASC, paired_at ASC;"
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_user(self, telegram_id: int) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM remote_users WHERE telegram_id = ?;", (telegram_id,)
            )
        return cur.rowcount > 0

    def remove_allowed_users(self) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM remote_users WHERE role = 'allowed';")

    def touch_user(self, telegram_id: int) -> None:
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "UPDATE remote_users SET last_seen_at = ? WHERE telegram_id = ?;",
                    (now_iso(), telegram_id),
                )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Pairing
    # ------------------------------------------------------------------ #

    def create_pairing(self, code_hash: str, ttl_seconds: int) -> str:
        created = now_iso()
        expires = iso_after(ttl_seconds)
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM remote_pairing_codes WHERE expires_at < ? AND used_at IS NULL;",
                (created,),
            )
            conn.execute(
                "INSERT INTO remote_pairing_codes (code_hash, created_at, expires_at) VALUES (?, ?, ?);",
                (code_hash, created, expires),
            )
        return expires

    def get_pairing(self, code_hash: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM remote_pairing_codes WHERE code_hash = ?;", (code_hash,)
            ).fetchone()
        return _row(row)

    def consume_pairing(self, code_hash: str, telegram_id: int) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE remote_pairing_codes
                SET used_at = ?, used_by = ?
                WHERE code_hash = ? AND used_at IS NULL AND expires_at >= ?;
                """,
                (now_iso(), telegram_id, code_hash, now_iso()),
            )
        return cur.rowcount > 0

    def cancel_pairing(self) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM remote_pairing_codes WHERE used_at IS NULL;"
            )

    # ------------------------------------------------------------------ #
    # Command audit
    # ------------------------------------------------------------------ #

    def start_command(
        self,
        *,
        telegram_id: int,
        username: Optional[str],
        command: str,
        args: Optional[Dict[str, Any]] = None,
    ) -> str:
        command_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO remote_commands (id, telegram_id, username, command, args, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'received', ?);
                """,
                (
                    command_id,
                    telegram_id,
                    username,
                    command,
                    json.dumps(args or {}),
                    now_iso(),
                ),
            )
        return command_id

    def finish_command(
        self,
        command_id: str,
        *,
        status: str,
        response: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    """
                    UPDATE remote_commands
                    SET status = ?, response = ?, error = ?, completed_at = ?
                    WHERE id = ?;
                    """,
                    (status, (response or "")[:4000], error, now_iso(), command_id),
                )
        except Exception as exc:
            logger.error("Could not finish remote command audit row: %s", exc)

    def list_commands(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM remote_commands ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_recent_commands(self, telegram_id: int, window_seconds: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()
        with self._db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM remote_commands
                WHERE telegram_id = ? AND created_at >= ? AND status != 'rate_limited';
                """,
                (telegram_id, cutoff),
            ).fetchone()
        return int(row["count"]) if row else 0

    # ------------------------------------------------------------------ #
    # Notification queue
    # ------------------------------------------------------------------ #

    def enqueue_notification(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
        ttl_seconds: int = 43200,
    ) -> Optional[str]:
        stamp = now_iso()
        expires = iso_after(ttl_seconds)
        with self._db.transaction() as conn:
            if dedupe_key:
                existing = conn.execute(
                    """
                    SELECT id FROM remote_notifications
                    WHERE category = ? AND dedupe_key = ? AND status = 'queued'
                    ORDER BY created_at DESC LIMIT 1;
                    """,
                    (category, dedupe_key),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE remote_notifications
                        SET severity = ?, title = ?, message = ?, payload = ?,
                            created_at = ?, next_attempt_at = ?, expires_at = ?, last_error = NULL
                        WHERE id = ?;
                        """,
                        (
                            severity,
                            title,
                            message,
                            json.dumps(payload or {}),
                            stamp,
                            stamp,
                            expires,
                            existing["id"],
                        ),
                    )
                    return existing["id"]

            notification_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO remote_notifications
                    (id, dedupe_key, category, severity, title, message, payload, status,
                     attempts, next_attempt_at, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?);
                """,
                (
                    notification_id,
                    dedupe_key,
                    category,
                    severity,
                    title,
                    message,
                    json.dumps(payload or {}),
                    stamp,
                    stamp,
                    expires,
                ),
            )
        return notification_id

    def list_due_notifications(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM remote_notifications
                WHERE status = 'queued' AND next_attempt_at <= ?
                ORDER BY created_at ASC LIMIT ?;
                """,
                (now_iso(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_notifications(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM remote_notifications"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)
        with self._db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def mark_notification_sending(self, notification_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE remote_notifications SET status = 'sending' WHERE id = ? AND status = 'queued';",
                (notification_id,),
            )
        return cur.rowcount > 0

    def mark_notification_sent(self, notification_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE remote_notifications SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ?;",
                (now_iso(), notification_id),
            )

    def mark_notification_failed(
        self,
        notification_id: str,
        *,
        error: str,
        retry_in_seconds: int,
        expired: bool = False,
    ) -> None:
        with self._db.transaction() as conn:
            if expired:
                conn.execute(
                    "UPDATE remote_notifications SET status = 'expired', last_error = ? WHERE id = ?;",
                    (error[:500], notification_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE remote_notifications
                    SET status = 'queued', attempts = attempts + 1,
                        next_attempt_at = ?, last_error = ?
                    WHERE id = ?;
                    """,
                    (iso_after(max(1, retry_in_seconds)), error[:500], notification_id),
                )

    def suppress_notification(self, notification_id: str, reason: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE remote_notifications SET status = 'suppressed', last_error = ? WHERE id = ?;",
                (reason[:500], notification_id),
            )

    def retry_notification(self, notification_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE remote_notifications
                SET status = 'queued', attempts = 0, next_attempt_at = ?, last_error = NULL
                WHERE id = ? AND status IN ('failed', 'expired', 'suppressed');
                """,
                (now_iso(), notification_id),
            )
        return cur.rowcount > 0

    def expire_notifications(self) -> int:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE remote_notifications
                SET status = 'expired', last_error = 'expired before delivery'
                WHERE status = 'queued' AND expires_at < ?;
                """,
                (now_iso(),),
            )
        return cur.rowcount

    def reset_sending_notifications(self) -> int:
        """Recover rows left mid-flight by a daemon restart."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE remote_notifications SET status = 'queued' WHERE status = 'sending';"
            )
        return cur.rowcount

    def collapse_queued_notifications(self, max_items: int) -> Dict[str, int]:
        """Drop duplicate and overflow rows before flushing after a reconnect."""
        suppressed = 0
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, category, dedupe_key FROM remote_notifications
                WHERE status = 'queued' ORDER BY created_at DESC;
                """
            ).fetchall()
            seen: set[tuple[str, str]] = set()
            overflow_ids: List[str] = []
            for index, row in enumerate(rows):
                key = (row["category"], row["dedupe_key"] or "")
                if row["dedupe_key"] and key in seen:
                    conn.execute(
                        "UPDATE remote_notifications SET status = 'suppressed', last_error = 'collapsed duplicate' WHERE id = ?;",
                        (row["id"],),
                    )
                    suppressed += 1
                    continue
                if row["dedupe_key"]:
                    seen.add(key)
                if index - suppressed >= max_items:
                    overflow_ids.append(row["id"])
            for notification_id in overflow_ids:
                conn.execute(
                    "UPDATE remote_notifications SET status = 'suppressed', last_error = 'queue overflow' WHERE id = ?;",
                    (notification_id,),
                )
                suppressed += 1
        return {"suppressed": suppressed}

    def notification_stats(self) -> Dict[str, int]:
        stats = {"queued": 0, "sending": 0, "sent": 0, "failed": 0, "expired": 0, "suppressed": 0}
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM remote_notifications GROUP BY status;"
            ).fetchall()
        for row in rows:
            stats[row["status"]] = int(row["count"])
        stats["total"] = sum(stats.values())
        return stats

    def purge_sent_notifications(self, keep: int = 200) -> int:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                DELETE FROM remote_notifications
                WHERE status = 'sent' AND id NOT IN (
                    SELECT id FROM remote_notifications WHERE status = 'sent'
                    ORDER BY created_at DESC LIMIT ?
                );
                """,
                (keep,),
            )
        return cur.rowcount

    # ------------------------------------------------------------------ #
    # Remote tasks
    # ------------------------------------------------------------------ #

    def create_remote_task(self, telegram_id: int, command: str, goal: str) -> str:
        task_id = str(uuid.uuid4())
        stamp = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO remote_tasks (id, telegram_id, command, goal, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'created', ?, ?);
                """,
                (task_id, telegram_id, command, goal, stamp, stamp),
            )
        return task_id

    def update_remote_task(
        self,
        task_id: str,
        *,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE remote_tasks SET status = ?, result = ?, error = ?, updated_at = ?
                WHERE id = ?;
                """,
                (status, result, error, now_iso(), task_id),
            )

    def get_remote_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute("SELECT * FROM remote_tasks WHERE id = ?;", (task_id,)).fetchone()
        return _row(row)

    def list_remote_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM remote_tasks ORDER BY created_at DESC LIMIT ?;", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Pending dangerous actions
    # ------------------------------------------------------------------ #

    def create_pending_action(
        self,
        *,
        approval_id: str,
        telegram_id: int,
        command: str,
        tool_name: str,
        arguments: Dict[str, Any],
        ttl_seconds: int = 900,
        task_id: Optional[str] = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO remote_pending_actions
                    (approval_id, telegram_id, command, tool_name, arguments, status, result, task_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?, ?);
                """,
                (
                    approval_id,
                    telegram_id,
                    command,
                    tool_name,
                    json.dumps(arguments),
                    task_id,
                    now_iso(),
                    iso_after(ttl_seconds),
                ),
            )

    def get_pending_action(self, approval_id: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM remote_pending_actions WHERE approval_id = ?;", (approval_id,)
            ).fetchone()
        return _row(row)

    def list_pending_actions(self, status: Optional[str] = "pending") -> List[Dict[str, Any]]:
        query = "SELECT * FROM remote_pending_actions"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC;"
        with self._db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def set_pending_action_status(
        self,
        approval_id: str,
        status: str,
        result: Optional[str] = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE remote_pending_actions SET status = ?, result = ? WHERE approval_id = ?;",
                (status, result, approval_id),
            )

    def expire_pending_actions(self) -> int:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE remote_pending_actions SET status = 'expired'
                WHERE status = 'pending' AND expires_at < ?;
                """,
                (now_iso(),),
            )
        return cur.rowcount
