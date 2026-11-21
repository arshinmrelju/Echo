"""Notification routing and the offline-tolerant delivery queue."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from echo.remote.config import RemoteSettings, SEVERITY_ORDER
from echo.remote.store import RemoteStore
from echo.remote.telegram import TelegramClient, TelegramError, esc

logger = logging.getLogger("echo.remote.notifications")

# How long a queued notification remains useful, by severity.
SEVERITY_TTL_SECONDS = {
    "critical": 6 * 3600,
    "warning": 2 * 3600,
    "notice": 3600,
    "info": 30 * 60,
}

CATEGORY_LABELS = {
    "alert": "SYSTEM ALERT",
    "alert_recovery": "ALERT RECOVERED",
    "monitor_event": "MONITOR EVENT",
    "task": "TASK",
    "approval": "APPROVAL REQUIRED",
    "connectivity": "CONNECTIVITY",
    "system": "ECHO",
}


class NotificationRouter:
    """Decides what is worth sending and formats it for Telegram."""

    def __init__(
        self,
        store: RemoteStore,
        settings_getter: Callable[[], RemoteSettings],
    ) -> None:
        self._store = store
        self._settings = settings_getter

    # ------------------------------------------------------------------ #
    # Eligibility
    # ------------------------------------------------------------------ #

    def _ttl(self, severity: str) -> int:
        settings = self._settings()
        cap = settings.queue_ttl_hours * 3600
        return min(SEVERITY_TTL_SECONDS.get(severity, 3600), cap)

    def _enabled(self) -> bool:
        settings = self._settings()
        return bool(settings.enabled and settings.effective_owner_id)

    def _event_selected(self, severity: str, category: str) -> bool:
        settings = self._settings()
        if not settings.notify_monitor_events:
            return False
        threshold = settings.monitor_event_min_severity
        if SEVERITY_ORDER.index(severity) < SEVERITY_ORDER.index(threshold):
            return False
        if settings.monitor_event_categories and category not in settings.monitor_event_categories:
            return False
        return True

    def enqueue(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
    ) -> Optional[str]:
        if not self._enabled():
            return None
        if severity not in SEVERITY_ORDER:
            severity = "info"
        return self._store.enqueue_notification(
            category=category,
            severity=severity,
            title=title,
            message=message,
            payload=payload,
            dedupe_key=dedupe_key,
            ttl_seconds=self._ttl(severity),
        )

    # ------------------------------------------------------------------ #
    # Event ingestion
    # ------------------------------------------------------------------ #

    async def handle_bus_event(self, topic: str, payload: Dict[str, Any]) -> None:
        try:
            if topic == "monitor_alert":
                self._handle_alert(payload)
            elif topic == "monitor_recovered":
                self._handle_recovery(payload)
            elif topic == "monitor_event":
                self._handle_monitor_event(payload)
            elif topic == "approval_request":
                self._handle_approval(payload)
            elif topic == "task_updated":
                self._handle_task(payload)
        except Exception as exc:
            logger.warning("Remote notification routing failed for %s: %s", topic, exc)

    def _handle_alert(self, payload: Dict[str, Any]) -> None:
        settings = self._settings()
        alert = payload.get("alert") or {}
        severity = str(alert.get("severity") or "warning")
        if severity == "critical" and not settings.notify_critical_alerts:
            return
        if severity == "warning" and not settings.notify_warnings:
            return
        if severity in ("info", "notice") and not settings.notify_warnings:
            return
        if alert.get("status") != "active":
            return
        event = payload.get("event")
        label = {
            "triggered": "ALERT",
            "escalated": "ESCALATED",
            "reminder": "STILL ACTIVE",
            "transient": "EVENT",
        }.get(str(event), "ALERT")
        title = f"{label}: {alert.get('title')}"
        self.enqueue(
            category="alert",
            severity=severity,
            title=title,
            message=str(alert.get("message") or ""),
            payload={"alert_id": alert.get("id"), "event": event, "category": alert.get("category")},
            dedupe_key=f"alert:{alert.get('id')}",
        )

    def _handle_recovery(self, payload: Dict[str, Any]) -> None:
        settings = self._settings()
        if not settings.notify_critical_alerts and not settings.notify_warnings:
            return
        alert = payload.get("alert") or {}
        self.enqueue(
            category="alert_recovery",
            severity="info",
            title=f"RECOVERED: {alert.get('title')}",
            message=str(payload.get("message") or alert.get("message") or "The condition has cleared."),
            payload={"alert_id": alert.get("id")},
            dedupe_key=f"recovered:{alert.get('id')}",
        )

    def _handle_monitor_event(self, payload: Dict[str, Any]) -> None:
        event = payload.get("event") or {}
        severity = str(event.get("severity") or "info")
        category = str(event.get("category") or "system")
        if not self._event_selected(severity, category):
            return
        self.enqueue(
            category="monitor_event",
            severity=severity,
            title=f"{severity.upper()}: {event.get('title')}",
            message=str(event.get("message") or ""),
            payload={"event_id": event.get("id"), "category": category},
            dedupe_key=f"event:{event.get('id')}",
        )

    def _handle_approval(self, payload: Dict[str, Any]) -> None:
        if not self._settings().notify_approval_requests:
            return
        approval = payload.get("approval") or {}
        self.enqueue(
            category="approval",
            severity="warning",
            title=f"APPROVAL REQUIRED: {approval.get('tool_name')}",
            message=(
                f"{approval.get('description') or 'A tool is waiting for approval.'}\n"
                f"Approve locally in ECHO or reply /approve {approval.get('id')}"
            ),
            payload={"approval_id": approval.get("id"), "tool_name": approval.get("tool_name")},
            dedupe_key=f"approval:{approval.get('id')}",
        )

    def _handle_task(self, payload: Dict[str, Any]) -> None:
        if not self._settings().notify_task_results:
            return
        task = payload.get("task") or {}
        if task.get("origin") == "remote":
            return  # the command reply already reports the result
        status = str(task.get("status") or "")
        if status not in ("completed", "failed", "cancelled"):
            return
        severity = "notice" if status == "completed" else "warning"
        self.enqueue(
            category="task",
            severity=severity,
            title=f"TASK {status.upper()}: {task.get('goal')}",
            message=str(task.get("error") or "Task finished."),
            payload={"task_id": task.get("id"), "status": status},
            dedupe_key=f"task:{task.get('id')}:{status}",
        )

    def enqueue_connectivity(self, *, back_online: bool, downtime_seconds: int = 0, suppressed: int = 0) -> None:
        if not self._settings().notify_connectivity:
            return
        if back_online:
            minutes = max(1, downtime_seconds // 60)
            extra = f" {suppressed} stale notifications were condensed." if suppressed else ""
            self.enqueue(
                category="connectivity",
                severity="info",
                title="ECHO BACK ONLINE",
                message=f"The desktop relay reconnected after ~{minutes}m offline.{extra}",
                dedupe_key="connectivity:online",
            )
        else:
            self.enqueue(
                category="connectivity",
                severity="warning",
                title="ECHO OFFLINE",
                message="The desktop lost its Telegram relay. Commands will queue until it reconnects.",
                dedupe_key="connectivity:offline",
            )

    async def notify_command_result(self, title: str, message: str, *, success: bool = True) -> None:
        self.enqueue(
            category="system",
            severity="info" if success else "warning",
            title=title,
            message=message,
        )

    # ------------------------------------------------------------------ #
    # Formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def format(notification: Dict[str, Any]) -> str:
        severity = str(notification.get("severity") or "info").upper()
        category = CATEGORY_LABELS.get(str(notification.get("category")), "ECHO")
        title = esc(notification.get("title") or "Notification")
        message = esc(notification.get("message") or "")
        stamp = _short_time(notification.get("created_at"))
        header = f"<b>[{severity}] {title}</b>"
        footer = f"<i>{esc(category)} · {stamp}</i>"
        return "\n".join(part for part in [header, message, footer] if part)


class NotificationDelivery:
    """Drains the queue while Telegram is reachable and applies backoff."""

    def __init__(
        self,
        store: RemoteStore,
        router: NotificationRouter,
        settings_getter: Callable[[], RemoteSettings],
    ) -> None:
        self._store = store
        self._router = router
        self._settings = settings_getter
        self._lock = asyncio.Lock()
        self.last_error: Optional[str] = None

    async def flush_once(self, client: TelegramClient, chat_id: int) -> Tuple[int, int]:
        """Send due notifications. Returns ``(sent, failed)``."""
        async with self._lock:
            settings = self._settings()
            expired = self._store.expire_notifications()
            if expired:
                logger.info("Expired %d stale remote notifications", expired)
            due = self._store.list_due_notifications(settings.queue_batch_size)
            sent = 0
            failed = 0
            for notification in due:
                if not self._store.mark_notification_sending(notification["id"]):
                    continue
                text = self._router.format(notification)
                try:
                    await client.send_message(chat_id, text)
                except TelegramError as exc:
                    failed += 1
                    self.last_error = exc.description
                    attempts = int(notification.get("attempts") or 0)
                    retry_after = exc.retry_after or min(300, 5 * (2 ** min(attempts, 6)))
                    expired_now = _is_expired(notification)
                    self._store.mark_notification_failed(
                        notification["id"],
                        error=exc.description,
                        retry_in_seconds=retry_after,
                        expired=expired_now,
                    )
                    if exc.error_code == 429:
                        await asyncio.sleep(min(5, retry_after))
                    # An auth or connectivity failure applies to the whole
                    # batch; leave the rest queued for the next pass.
                    break
                except Exception as exc:
                    failed += 1
                    self.last_error = str(exc)
                    self._store.mark_notification_failed(
                        notification["id"],
                        error=str(exc),
                        retry_in_seconds=30,
                    )
                    break
                else:
                    sent += 1
                    self._store.mark_notification_sent(notification["id"])
                    delay = 1.0 / max(0.2, settings.send_rate_per_second)
                    if sent < len(due):
                        await asyncio.sleep(delay)
            if sent:
                self._store.purge_sent_notifications(keep=200)
            return sent, failed

    def prepare_reconnect(self) -> int:
        """Collapse duplicates and expire stale entries before a reconnect flush."""
        self._store.expire_notifications()
        result = self._store.collapse_queued_notifications(self._settings().queue_max_items)
        return int(result.get("suppressed") or 0)


def _short_time(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return ""


def _is_expired(notification: Dict[str, Any]) -> bool:
    value = notification.get("expires_at")
    if not value:
        return False
    try:
        expires = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return expires <= datetime.now(timezone.utc)
