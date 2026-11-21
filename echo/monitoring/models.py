"""Shared monitoring types and helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class Severity(str, Enum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


SEVERITY_RANK: Dict[str, int] = {
    Severity.INFO.value: 0,
    Severity.NOTICE.value: 1,
    Severity.WARNING.value: 2,
    Severity.CRITICAL.value: 3,
}


class MonitorCategory(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    BATTERY = "battery"
    NETWORK = "network"
    TEMPERATURE = "temperature"
    APPLICATION = "application"
    WINDOWS_EVENT = "windows_event"
    SYSTEM = "system"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(severity, 0)


def max_severity(left: str, right: str) -> str:
    return left if severity_rank(left) >= severity_rank(right) else right


def escalate_severity(severity: str) -> str:
    order = [Severity.INFO.value, Severity.NOTICE.value, Severity.WARNING.value, Severity.CRITICAL.value]
    try:
        index = order.index(severity)
    except ValueError:
        return severity
    return order[min(index + 1, len(order) - 1)]


def severity_from_windows_level(level: Any) -> str:
    try:
        numeric = int(level)
    except (TypeError, ValueError):
        return Severity.INFO.value
    if numeric <= 1:
        return Severity.CRITICAL.value
    if numeric == 2:
        return Severity.WARNING.value
    if numeric == 3:
        return Severity.NOTICE.value
    return Severity.INFO.value


@dataclass
class Finding:
    """A raw event observation ready to be persisted in the event feed."""

    dedupe_key: Optional[str]
    category: str
    severity: str
    kind: str
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    occurred_at: Optional[str] = None

    def as_event(self) -> Dict[str, Any]:
        return {
            "dedupe_key": self.dedupe_key,
            "category": self.category,
            "severity": self.severity,
            "kind": self.kind,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "occurred_at": self.occurred_at or now_iso(),
        }
