"""Alert lifecycle: dedupe, cooldowns, escalation, recovery, and notifications."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from echo.monitoring.models import (
    Finding,
    Severity,
    escalate_severity,
    max_severity,
    parse_iso,
    severity_rank,
)
from echo.monitoring.store import MonitoringStore

logger = logging.getLogger("echo.monitoring.alerting")


class AlertManager:
    """Owns alert state transitions and returns websocket payloads to emit.

    The manager never broadcasts directly. The engine decides where payloads go,
    which keeps the alert logic testable without a running event loop.
    """

    def __init__(self, store: MonitoringStore, cooldown_seconds: int = 900) -> None:
        self._store = store
        self.cooldown_seconds = max(30, cooldown_seconds)

    def set_cooldown(self, seconds: int) -> None:
        self.cooldown_seconds = max(30, seconds)

    # ------------------------------------------------------------------ #
    # Lifecycle events
    # ------------------------------------------------------------------ #

    def _record_lifecycle(
        self,
        alert: Dict[str, Any],
        kind: str,
        severity: str,
        message: Optional[str] = None,
    ) -> None:
        self._store.insert_event(
            {
                "dedupe_key": None,
                "category": alert["category"],
                "severity": severity,
                "kind": kind,
                "title": alert["title"],
                "message": message or alert["message"],
                "details": alert.get("details") or {},
                "occurred_at": None,
            },
            alert_id=alert["id"],
        )

    # ------------------------------------------------------------------ #
    # Persistent condition alerts
    # ------------------------------------------------------------------ #

    def raise_alert(
        self,
        *,
        dedupe_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> Optional[Dict[str, Any]]:
        details = details or {}
        active = self._store.get_active_alert(dedupe_key)

        if active is None:
            alert = self._store.create_alert(
                dedupe_key=dedupe_key,
                category=category,
                severity=severity,
                title=title,
                message=message,
                details=details,
                source=source,
            )
            if alert is None:
                return None
            self._record_lifecycle(alert, "alert", severity)
            return {"type": "monitor_alert", "event": "triggered", "alert": alert}

        now = datetime.now(timezone.utc)
        last_notified = parse_iso(active.get("last_notified_at")) or now
        cooldown_elapsed = (now - last_notified).total_seconds() >= self.cooldown_seconds
        severity_increased = severity_rank(severity) > severity_rank(active["severity"])

        if severity_increased:
            updated = self._store.touch_alert(
                active["id"],
                severity=severity,
                message=message,
                details=details,
                notified=True,
                count_occurrence=True,
            )
            self._record_lifecycle(updated or active, "severity_increase", severity, message)
            return {"type": "monitor_alert", "event": "escalated", "alert": updated}

        if cooldown_elapsed:
            updated = self._store.touch_alert(
                active["id"],
                severity=severity,
                message=message,
                details=details,
                notified=True,
                count_occurrence=True,
            )
            self._record_lifecycle(updated or active, "reminder", updated["severity"] if updated else severity)
            return {"type": "monitor_alert", "event": "reminder", "alert": updated}

        # Condition still true but no notification is due. Keep last_seen fresh
        # without inflating the occurrence counter.
        self._store.touch_alert(
            active["id"],
            severity=severity,
            message=message,
            details=details,
            notified=False,
            count_occurrence=False,
        )
        return None

    def maybe_escalate(
        self, alert: Dict[str, Any], escalation_seconds: int
    ) -> Optional[Dict[str, Any]]:
        if alert.get("status") != "active":
            return None
        if alert.get("acknowledged_at"):
            return None
        if severity_rank(alert["severity"]) >= severity_rank(Severity.CRITICAL.value):
            return None

        now = datetime.now(timezone.utc)
        first_seen = parse_iso(alert.get("first_seen_at")) or now
        elapsed = (now - first_seen).total_seconds()
        if elapsed < escalation_seconds:
            return None

        last_escalated = parse_iso(alert.get("last_escalated_at"))
        if last_escalated is not None and (now - last_escalated).total_seconds() < escalation_seconds:
            return None

        new_severity = escalate_severity(alert["severity"])
        message = (
            f"{alert['message']} This has remained unresolved for "
            f"{int(elapsed // 60)} minutes."
        )
        updated = self._store.escalate_alert(alert["id"], new_severity, message)
        if updated is None:
            return None
        self._record_lifecycle(updated, "escalation", new_severity, message)
        return {"type": "monitor_alert", "event": "escalated", "alert": updated}

    def recover(
        self,
        dedupe_key: str,
        *,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        notify: bool = True,
    ) -> Optional[Dict[str, Any]]:
        active = self._store.get_active_alert(dedupe_key)
        if active is None:
            return None
        updated = self._store.recover_alert(
            active["id"], message or f"Recovered: {active['title']}"
        )
        if updated is None:
            return None
        self._record_lifecycle(updated, "recovery", Severity.INFO.value, message)
        if not notify:
            return None
        return {
            "type": "monitor_recovered",
            "alert": updated,
            "message": message or f"Recovered: {active['title']}",
        }

    # ------------------------------------------------------------------ #
    # Point events
    # ------------------------------------------------------------------ #

    def record_finding(self, finding: Finding) -> Optional[Dict[str, Any]]:
        event = self._store.insert_event(finding.as_event())
        if event is None:
            return None
        return {"type": "monitor_event", "event": event}

    def record_transient_alert(
        self,
        *,
        dedupe_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        occurred_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record a one-shot event as an already-resolved alert entry."""
        if self._store.alert_exists(dedupe_key):
            return None
        alert = self._store.create_alert(
            dedupe_key=dedupe_key,
            category=category,
            severity=severity,
            title=title,
            message=message,
            details=details or {},
            status="resolved",
            occurred_at=occurred_at,
        )
        if alert is None:
            return None
        return {"type": "monitor_alert", "event": "transient", "alert": alert}

    # ------------------------------------------------------------------ #
    # User actions
    # ------------------------------------------------------------------ #

    def acknowledge(self, alert_id: str) -> Optional[Dict[str, Any]]:
        updated = self._store.acknowledge_alert(alert_id)
        if updated is None:
            return None
        self._record_lifecycle(updated, "acknowledged", Severity.INFO.value)
        return {"type": "monitor_alert", "event": "acknowledged", "alert": updated}

    def resolve(self, alert_id: str) -> Optional[Dict[str, Any]]:
        updated = self._store.resolve_alert(alert_id)
        if updated is None:
            return None
        self._record_lifecycle(updated, "resolved", Severity.INFO.value)
        return {"type": "monitor_alert", "event": "resolved", "alert": updated}

    def acknowledge_all(self) -> int:
        count = 0
        for alert in self._store.list_active_alerts():
            if not alert.get("acknowledged_at"):
                if self._store.acknowledge_alert(alert["id"]) is not None:
                    count += 1
        return count

    def resolve_stale(self, alerts: list[Dict[str, Any]], dedupe_prefix: str) -> None:
        """Recover alerts whose source condition no longer exists."""
        for alert in alerts:
            if alert["dedupe_key"].startswith(dedupe_prefix):
                self.recover(alert["dedupe_key"], notify=False)


def alert_severity_for(alert: Dict[str, Any]) -> str:
    return max_severity(alert.get("severity") or Severity.INFO.value, Severity.INFO.value)
