"""Remote status assembly and Telegram-safe formatting."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from echo.remote.config import RemoteSettings
from echo.remote.store import RemoteStore
from echo.remote.telegram import esc

logger = logging.getLogger("echo.remote.status")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def age_seconds(value: Optional[str]) -> Optional[int]:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return max(0, int((_now() - parsed).total_seconds()))


def human_age(value: Optional[str]) -> str:
    seconds = age_seconds(value)
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _monitor():
    try:
        from echo.monitoring.service import get_monitoring_service

        return get_monitoring_service()
    except Exception as exc:  # pragma: no cover - monitoring is optional
        logger.debug("Monitoring service unavailable for remote status: %s", exc)
        return None


def _latest_task(store: RemoteStore) -> Optional[Dict[str, Any]]:
    try:
        with store.database.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, goal, status, updated_at FROM tasks
                WHERE status IN ('planning', 'in_progress')
                ORDER BY updated_at DESC LIMIT 1;
                """
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _cpu_memory_fallback() -> Dict[str, Any]:
    try:
        import psutil

        memory = psutil.virtual_memory()
        return {
            "cpu_percent": float(psutil.cpu_percent(interval=None)),
            "memory_percent": float(memory.percent),
            "memory_used_gb": round(memory.used / (1024 ** 3), 1),
            "memory_total_gb": round(memory.total / (1024 ** 3), 1),
        }
    except Exception:
        return {}


def build_status(
    settings: RemoteSettings,
    store: RemoteStore,
    relay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    relay = relay or {}
    service = _monitor()
    monitor_status: Dict[str, Any] = {}
    if service is not None:
        try:
            monitor_status = service.status()
        except Exception as exc:
            logger.debug("Could not read monitoring status: %s", exc)

    snapshot = monitor_status.get("snapshot") or {}
    counts = monitor_status.get("counts") or snapshot.get("alert_counts") or {}
    cpu = snapshot.get("cpu") or {}
    memory = snapshot.get("memory") or {}
    network = snapshot.get("network") or {}

    fallback = _cpu_memory_fallback() if not cpu or not memory else {}
    cpu_percent = cpu.get("percent", fallback.get("cpu_percent"))
    memory_percent = memory.get("percent", fallback.get("memory_percent"))

    disks: List[Dict[str, Any]] = []
    for disk in (snapshot.get("disks") or [])[:3]:
        disks.append(
            {
                "path": disk.get("path"),
                "free_gb": disk.get("free_gb"),
                "total_gb": disk.get("total_gb"),
                "percent": disk.get("percent"),
            }
        )

    active_alerts = int(counts.get("unacknowledged") or 0)
    critical = int(counts.get("critical") or 0)
    warning = int(counts.get("warning") or 0)
    if critical > 0:
        health_state = "critical"
    elif warning > 0:
        health_state = "warning"
    elif monitor_status.get("running") and snapshot.get("available"):
        health_state = "healthy"
    elif monitor_status.get("running"):
        health_state = "starting"
    else:
        health_state = "unknown"

    network_online = network.get("online")
    if network_online is None:
        network_online = bool(relay.get("connected")) or None

    task = _latest_task(store)
    remote_tasks = [t for t in store.list_remote_tasks(limit=10) if t["status"] in ("created", "planning", "in_progress")]
    current_task = None
    if task:
        current_task = {"id": task["id"], "goal": task["goal"], "status": task["status"], "source": "local"}
    elif remote_tasks:
        rt = remote_tasks[0]
        current_task = {"id": rt["id"], "goal": rt["goal"], "status": rt["status"], "source": "remote"}

    paused = bool(settings.paused)
    heartbeat = store.get_state("last_heartbeat_at")

    return {
        "timestamp": _now().isoformat(),
        "relay": {
            "enabled": settings.enabled,
            "connected": bool(relay.get("connected")),
            "running": bool(relay.get("running")),
            "bot_username": settings.bot_username,
            "polling": bool(relay.get("polling")),
            "last_poll_at": store.get_state("last_poll_at"),
            "last_heartbeat_at": heartbeat,
            "last_error": relay.get("last_error"),
            "reconnect_attempts": int(relay.get("reconnect_attempts") or 0),
        },
        "pc_online": bool(network_online) if network_online is not None else bool(relay.get("connected")),
        "echo_running": not paused,
        "echo_state": "paused" if paused else "running",
        "paused": paused,
        "pause_reason": settings.pause_reason,
        "current_task": current_task,
        "health": {
            "state": health_state,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_used_gb": memory.get("used_gb", fallback.get("memory_used_gb")),
            "memory_total_gb": memory.get("total_gb", fallback.get("memory_total_gb")),
            "disks": disks,
            "battery": snapshot.get("battery") or {},
            "network_online": network_online,
            "uptime_seconds": snapshot.get("uptime_seconds"),
            "active_alerts": active_alerts,
            "alerts_by_severity": {
                "critical": critical,
                "warning": warning,
                "notice": int(counts.get("notice") or 0),
                "info": int(counts.get("info") or 0),
            },
            "monitoring_running": bool(monitor_status.get("running")),
        },
        "last_heartbeat_at": heartbeat,
        "last_heartbeat_age_seconds": age_seconds(heartbeat),
    }


def format_status(status: Dict[str, Any]) -> str:
    relay = status.get("relay") or {}
    health = status.get("health") or {}
    task = status.get("current_task")
    lines = [
        "<b>ECHO · REMOTE STATUS</b>",
        "",
        f"PC <b>{'ONLINE' if status.get('pc_online') else 'OFFLINE'}</b> · "
        f"ECHO <b>{str(status.get('echo_state', 'unknown')).upper()}</b>",
        f"Relay <b>{'CONNECTED' if relay.get('connected') else 'DISCONNECTED'}</b>"
        + (f" · @{esc(relay['bot_username'])}" if relay.get("bot_username") else ""),
        f"Health <b>{str(health.get('state', 'unknown')).upper()}</b>"
        + (f" · {health.get('active_alerts')} unacknowledged alerts" if health.get("active_alerts") else ""),
    ]
    if task:
        lines.append(f"Task <b>{esc(task.get('goal'))}</b> ({esc(task.get('status'))})")
    else:
        lines.append("Task <b>IDLE</b>")
    if status.get("paused") and status.get("pause_reason"):
        lines.append(f"Paused: {esc(status['pause_reason'])}")

    resources = _resource_line(health)
    if resources:
        lines.append("")
        lines.append(resources)
    lines.append("")
    lines.append(
        f"<i>Heartbeat {human_age(status.get('last_heartbeat_at'))} · "
        f"{_local_time(status.get('timestamp'))}</i>"
    )
    return "\n".join(lines)


def format_health(status: Dict[str, Any]) -> str:
    health = status.get("health") or {}
    lines = ["<b>ECHO · SYSTEM HEALTH</b>", ""]
    resources = _resource_line(health)
    lines.append(resources or "Metrics unavailable.")

    battery = health.get("battery") or {}
    if battery.get("present"):
        plugged = "plugged in" if battery.get("plugged") else "on battery"
        lines.append(f"Battery: {battery.get('percent')}% ({plugged})")

    uptime = health.get("uptime_seconds")
    if uptime:
        lines.append(f"Uptime: {int(uptime) // 3600}h {(int(uptime) % 3600) // 60}m")

    state = str(health.get("state", "unknown")).upper()
    lines.append("")
    lines.append(f"Overall: <b>{state}</b>")
    counts = health.get("alerts_by_severity") or {}
    if any(counts.values()):
        lines.append(
            "Alerts: "
            + " · ".join(
                f"{esc(sev).upper()} {count}" for sev, count in counts.items() if count
            )
        )
    if not health.get("monitoring_running"):
        lines.append("<i>Monitoring engine is idle; metrics may be stale.</i>")
    return "\n".join(lines)


def _resource_line(health: Dict[str, Any]) -> str:
    parts: List[str] = []
    if health.get("cpu_percent") is not None:
        parts.append(f"CPU {float(health['cpu_percent']):.0f}%")
    if health.get("memory_percent") is not None:
        parts.append(f"RAM {float(health['memory_percent']):.0f}%")
    disks = health.get("disks") or []
    if disks:
        disk = disks[0]
        free = disk.get("free_gb")
        if free is not None:
            parts.append(f"Disk {disk.get('path')} {float(free):.1f} GB free")
    return " · ".join(parts)


def format_events(events: List[Dict[str, Any]], limit: int) -> str:
    if not events:
        return "<b>ECHO · EVENT FEED</b>\n\nNo monitored events recorded yet."
    lines = [f"<b>ECHO · EVENT FEED</b> (last {min(limit, len(events))})", ""]
    for event in events[:limit]:
        severity = str(event.get("severity") or "info").upper()
        occurred = human_age(event.get("occurred_at"))
        lines.append(
            f"[{severity}] <b>{esc(event.get('title'))}</b>\n"
            f"{esc(event.get('message'))}\n<i>{esc(event.get('category'))} · {occurred}</i>"
        )
    return "\n\n".join(lines)


def format_tasks(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return "<b>ECHO · TASKS</b>\n\nNo tasks registered."
    lines = [f"<b>ECHO · TASKS</b> ({len(tasks)})", ""]
    for task in tasks[:20]:
        lines.append(
            f"<b>{esc(task.get('goal'))}</b>\n"
            f"{esc(task.get('status')).upper()} · {human_age(task.get('updated_at'))}"
        )
    return "\n\n".join(lines)


def _local_time(value: Optional[str]) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "now"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
