"""Persisted remote relay preferences and secret handling."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

RemoteSeverity = Literal["info", "notice", "warning", "critical"]

# Notifications at or above this severity are considered operator-relevant.
SEVERITY_ORDER = ["info", "notice", "warning", "critical"]


class RemoteSettings(BaseModel):
    """Telegram relay configuration.

    ``bot_token`` is the only secret. It is persisted in the local SQLite
    database and never returned by the API or written to logs.
    """

    enabled: bool = False
    bot_token: str = ""
    bot_username: Optional[str] = None

    owner_user_id: Optional[int] = None
    owner_username: Optional[str] = None
    owner_display_name: Optional[str] = None
    allowed_user_ids: List[int] = Field(default_factory=list)

    # Pairing and abuse controls
    pairing_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    command_rate_limit: int = Field(default=20, ge=1, le=120)
    pairing_attempt_limit: int = Field(default=5, ge=1, le=20)
    pairing_attempt_window_seconds: int = Field(default=600, ge=60, le=3600)

    # Channel behaviour
    poll_timeout_seconds: int = Field(default=25, ge=5, le=50)
    reconnect_max_seconds: int = Field(default=60, ge=5, le=600)
    screenshot_enabled: bool = True
    max_screenshot_mb: int = Field(default=9, ge=1, le=20)

    # Notification routing
    notify_critical_alerts: bool = True
    notify_warnings: bool = True
    notify_task_results: bool = True
    notify_approval_requests: bool = True
    notify_connectivity: bool = True
    notify_monitor_events: bool = False
    monitor_event_min_severity: RemoteSeverity = "warning"
    monitor_event_categories: List[str] = Field(default_factory=list)

    # Offline queue hygiene
    queue_ttl_hours: int = Field(default=12, ge=1, le=168)
    queue_max_items: int = Field(default=200, ge=10, le=2000)
    queue_batch_size: int = Field(default=8, ge=1, le=50)
    send_rate_per_second: float = Field(default=1.0, ge=0.2, le=20.0)

    paused: bool = False
    pause_reason: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _clean_ids(cls, value: Any) -> List[int]:
        if value is None:
            return []
        if isinstance(value, (int, str)):
            value = [value]
        cleaned: List[int] = []
        for item in value:
            try:
                numeric = int(item)
            except (TypeError, ValueError):
                continue
            if numeric > 0 and numeric not in cleaned:
                cleaned.append(numeric)
        return cleaned

    @field_validator("monitor_event_categories", mode="before")
    @classmethod
    def _clean_categories(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item).strip() for item in value if str(item).strip()]

    @property
    def token_configured(self) -> bool:
        return bool(self.bot_token)

    def public_dict(self) -> Dict[str, Any]:
        """API-safe view: the token is replaced by a configuration flag."""
        data = self.model_dump()
        token = data.pop("bot_token", "") or ""
        data["bot_token_configured"] = bool(token)
        data["bot_token_hint"] = f"…{token[-4:]}" if len(token) >= 8 else ""
        data["effective_owner_user_id"] = self.effective_owner_id
        return data

    @property
    def effective_owner_id(self) -> Optional[int]:
        if self.owner_user_id:
            return self.owner_user_id
        env_owner = os.getenv("ECHO_TELEGRAM_OWNER_ID", "").strip()
        if env_owner:
            try:
                return int(env_owner)
            except ValueError:
                return None
        return None

    @property
    def effective_token(self) -> str:
        return self.bot_token or os.getenv("ECHO_TELEGRAM_BOT_TOKEN", "").strip()


DEFAULT_SETTINGS = RemoteSettings()
