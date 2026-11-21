"""SQLite persistence for monitoring alerts, events, and settings."""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from echo.core.database import Database, get_database
from echo.monitoring.models import max_severity, now_iso

logger = logging.getLogger("echo.monitoring.store")

MONITORING_SETTINGS_KEY = "monitoring_settings"


def _row_to_alert(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "dedupe_key": row["dedupe_key"],
        "category": row["category"],
        "severity": row["severity"],
        "title": row["title"],
        "message": row["message"],
        "details": json.loads(row["details"]) if row["details"] else {},
        "status": row["status"],
        "source": row["source"],
        "occurrences": row["occurrences"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "last_notified_at": row["last_notified_at"],
        "last_escalated_at": row["last_escalated_at"],
        "acknowledged_at": row["acknowledged_at"],
        "recovered_at": row["recovered_at"],
        "resolved_at": row["resolved_at"],
        "escalation_level": row["escalation_level"],
    }


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "dedupe_key": row["dedupe_key"],
        "category": row["category"],
        "severity": row["severity"],
        "kind": row["kind"],
        "title": row["title"],
        "message": row["message"],
        "details": json.loads(row["details"]) if row["details"] else {},
        "alert_id": row["alert_id"],
        "occurred_at": row["occurred_at"],
        "recorded_at": row["recorded_at"],
    }


class MonitoringStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #

    def load_settings(self) -> Optional[Dict[str, Any]]:
        try:
            with self._db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?;",
                    (MONITORING_SETTINGS_KEY,),
                ).fetchone()
            if row and row["value"]:
                return json.loads(row["value"])
        except Exception as exc:
            logger.warning("Could not load monitoring settings: %s", exc)
        return None

    def save_settings(self, settings: Dict[str, Any]) -> None:
        payload = json.dumps(settings)
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (MONITORING_SETTINGS_KEY, payload, now_iso()),
            )

    # ------------------------------------------------------------------ #
    # Alerts
    # ------------------------------------------------------------------ #

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM monitor_alerts WHERE id = ?;", (alert_id,)
            ).fetchone()
        return _row_to_alert(row) if row else None

    def get_active_alert(self, dedupe_key: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM monitor_alerts WHERE dedupe_key = ? AND status = 'active';",
                (dedupe_key,),
            ).fetchone()
        return _row_to_alert(row) if row else None

    def alert_exists(self, dedupe_key: str) -> bool:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM monitor_alerts WHERE dedupe_key = ? LIMIT 1;",
                (dedupe_key,),
            ).fetchone()
        return row is not None

    def create_alert(
        self,
        *,
        dedupe_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system",
        status: str = "active",
        occurred_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        moment = occurred_at or now_iso()
        alert_id = str(uuid.uuid4())
        resolved_at = now_iso() if status == "resolved" else None
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO monitor_alerts (
                        id, dedupe_key, category, severity, title, message, details,
                        status, source, occurrences, first_seen_at, last_seen_at,
                        last_notified_at, last_escalated_at, acknowledged_at,
                        recovered_at, resolved_at, escalation_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, NULL, NULL, ?, 0);
                    """,
                    (
                        alert_id,
                        dedupe_key,
                        category,
                        severity,
                        title,
                        message,
                        json.dumps(details or {}, ensure_ascii=False),
                        status,
                        source,
                        moment,
                        moment,
                        moment,
                        resolved_at,
                    ),
                )
        except sqlite3.IntegrityError:
            # Another active alert slipped in; return it so the caller can update.
            return self.get_active_alert(dedupe_key)
        return self.get_alert(alert_id)

    def touch_alert(
        self,
        alert_id: str,
        *,
        severity: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        notified: bool = False,
        count_occurrence: bool = True,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_alert(alert_id)
        if current is None:
            return None
        updated_severity = max_severity(current["severity"], severity)
        moment = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE monitor_alerts
                SET occurrences = occurrences + ?,
                    last_seen_at = ?,
                    severity = ?,
                    message = COALESCE(?, message),
                    details = COALESCE(?, details),
                    last_notified_at = CASE WHEN ? THEN ? ELSE last_notified_at END
                WHERE id = ?;
                """,
                (
                    1 if count_occurrence else 0,
                    moment,
                    updated_severity,
                    message,
                    json.dumps(details, ensure_ascii=False) if details is not None else None,
                    1 if notified else 0,
                    moment,
                    alert_id,
                ),
            )
        return self.get_alert(alert_id)

    def escalate_alert(
        self, alert_id: str, severity: str, message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        moment = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE monitor_alerts
                SET severity = ?,
                    message = COALESCE(?, message),
                    escalation_level = escalation_level + 1,
                    last_escalated_at = ?,
                    last_notified_at = ?
                WHERE id = ?;
                """,
                (severity, message, moment, moment, alert_id),
            )
        return self.get_alert(alert_id)

    def recover_alert(
        self, alert_id: str, message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        moment = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE monitor_alerts
                SET status = 'recovered',
                    recovered_at = ?,
                    message = COALESCE(?, message)
                WHERE id = ? AND status = 'active';
                """,
                (moment, message, alert_id),
            )
        return self.get_alert(alert_id)

    def acknowledge_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE monitor_alerts
                SET acknowledged_at = COALESCE(acknowledged_at, ?)
                WHERE id = ?;
                """,
                (now_iso(), alert_id),
            )
        return self.get_alert(alert_id)

    def resolve_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        moment = now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE monitor_alerts
                SET status = 'resolved',
                    resolved_at = COALESCE(resolved_at, ?),
                    recovered_at = CASE WHEN status = 'active' THEN COALESCE(recovered_at, ?) ELSE recovered_at END
                WHERE id = ?;
                """,
                (moment, moment, alert_id),
            )
        return self.get_alert(alert_id)

    def list_alerts(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._db.get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM monitor_alerts {where} ORDER BY last_seen_at DESC LIMIT ?;",
                params,
            ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def list_active_alerts(self) -> List[Dict[str, Any]]:
        return self.list_alerts(status="active", limit=200)

    def alert_counts(self) -> Dict[str, int]:
        counts = {"info": 0, "notice": 0, "warning": 0, "critical": 0, "total": 0, "unacknowledged": 0}
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT severity, COUNT(*) AS total FROM monitor_alerts WHERE status = 'active' GROUP BY severity;"
            ).fetchall()
            unack = conn.execute(
                "SELECT COUNT(*) AS total FROM monitor_alerts WHERE status = 'active' AND acknowledged_at IS NULL;"
            ).fetchone()
        for row in rows:
            severity = row["severity"]
            if severity in counts:
                counts[severity] = int(row["total"])
            counts["total"] += int(row["total"])
        counts["unacknowledged"] = int(unack["total"]) if unack else 0
        return counts

    # ------------------------------------------------------------------ #
    # Event feed
    # ------------------------------------------------------------------ #

    def insert_event(self, event: Dict[str, Any], alert_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        event_id = str(uuid.uuid4())
        recorded_at = now_iso()
        occurred_at = event.get("occurred_at") or recorded_at
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO monitor_events (
                        id, dedupe_key, category, severity, kind, title, message,
                        details, alert_id, occurred_at, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event_id,
                        event.get("dedupe_key"),
                        event["category"],
                        event["severity"],
                        event.get("kind") or "event",
                        event["title"],
                        event["message"],
                        json.dumps(event.get("details") or {}, ensure_ascii=False),
                        alert_id,
                        occurred_at,
                        recorded_at,
                    ),
                )
        except sqlite3.IntegrityError:
            return None
        return {
            "id": event_id,
            "dedupe_key": event.get("dedupe_key"),
            "category": event["category"],
            "severity": event["severity"],
            "kind": event.get("kind") or "event",
            "title": event["title"],
            "message": event["message"],
            "details": event.get("details") or {},
            "alert_id": alert_id,
            "occurred_at": occurred_at,
            "recorded_at": recorded_at,
        }

    def list_events(
        self,
        *,
        limit: int = 100,
        category: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._db.get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM monitor_events {where} ORDER BY occurred_at DESC LIMIT ?;",
                params,
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Retention
    # ------------------------------------------------------------------ #

    def purge(self, retention_days: int) -> Dict[str, int]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
        ).isoformat()
        with self._db.transaction() as conn:
            alerts_deleted = conn.execute(
                """
                DELETE FROM monitor_alerts
                WHERE status != 'active'
                  AND COALESCE(resolved_at, recovered_at, last_seen_at) < ?;
                """,
                (cutoff,),
            ).rowcount
            events_deleted = conn.execute(
                "DELETE FROM monitor_events WHERE occurred_at < ?;",
                (cutoff,),
            ).rowcount
        return {"alerts": int(alerts_deleted or 0), "events": int(events_deleted or 0)}
