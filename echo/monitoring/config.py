"""Monitoring configuration, profiles, and persisted thresholds."""
from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MonitoringProfile = Literal["quiet", "balanced", "strict"]

# Profiles only change detection behaviour and thresholds. User-specific data
# (monitored applications, disk paths, network targets) is always preserved.
PROFILE_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "quiet": {
        "poll_interval_seconds": 15,
        "cpu_warning_percent": 92.0,
        "cpu_critical_percent": 98.0,
        "cpu_sustained_seconds": 300,
        "memory_warning_percent": 92.0,
        "memory_critical_percent": 97.0,
        "memory_sustained_seconds": 300,
        "disk_free_warning_gb": 5.0,
        "disk_free_critical_gb": 1.0,
        "disk_percent_warning": 95.0,
        "disk_percent_critical": 99.0,
        "disk_sustained_seconds": 120,
        "battery_warning_percent": 10.0,
        "battery_critical_percent": 5.0,
        "network_check_interval_seconds": 30,
        "network_failure_seconds": 180,
        "temperature_warning_celsius": 85.0,
        "temperature_critical_celsius": 95.0,
        "temperature_sustained_seconds": 180,
        "temperature_interval_seconds": 120,
        "windows_event_interval_seconds": 120,
        "windows_event_lookback_seconds": 240,
        "hung_window_seconds": 60,
        "alert_cooldown_seconds": 3600,
        "escalation_seconds": 3600,
        "monitor_hung_windows": False,
    },
    "balanced": {
        "poll_interval_seconds": 5,
        "cpu_warning_percent": 85.0,
        "cpu_critical_percent": 95.0,
        "cpu_sustained_seconds": 120,
        "memory_warning_percent": 88.0,
        "memory_critical_percent": 95.0,
        "memory_sustained_seconds": 120,
        "disk_free_warning_gb": 10.0,
        "disk_free_critical_gb": 3.0,
        "disk_percent_warning": 90.0,
        "disk_percent_critical": 97.0,
        "disk_sustained_seconds": 60,
        "battery_warning_percent": 20.0,
        "battery_critical_percent": 10.0,
        "network_check_interval_seconds": 15,
        "network_failure_seconds": 60,
        "temperature_warning_celsius": 80.0,
        "temperature_critical_celsius": 90.0,
        "temperature_sustained_seconds": 60,
        "temperature_interval_seconds": 60,
        "windows_event_interval_seconds": 60,
        "windows_event_lookback_seconds": 180,
        "hung_window_seconds": 20,
        "alert_cooldown_seconds": 900,
        "escalation_seconds": 900,
        "monitor_hung_windows": True,
    },
    "strict": {
        "poll_interval_seconds": 3,
        "cpu_warning_percent": 75.0,
        "cpu_critical_percent": 90.0,
        "cpu_sustained_seconds": 60,
        "memory_warning_percent": 80.0,
        "memory_critical_percent": 92.0,
        "memory_sustained_seconds": 60,
        "disk_free_warning_gb": 20.0,
        "disk_free_critical_gb": 5.0,
        "disk_percent_warning": 85.0,
        "disk_percent_critical": 95.0,
        "disk_sustained_seconds": 30,
        "battery_warning_percent": 30.0,
        "battery_critical_percent": 15.0,
        "network_check_interval_seconds": 10,
        "network_failure_seconds": 30,
        "temperature_warning_celsius": 70.0,
        "temperature_critical_celsius": 85.0,
        "temperature_sustained_seconds": 30,
        "temperature_interval_seconds": 30,
        "windows_event_interval_seconds": 30,
        "windows_event_lookback_seconds": 120,
        "hung_window_seconds": 10,
        "alert_cooldown_seconds": 300,
        "escalation_seconds": 300,
        "monitor_hung_windows": True,
    },
}


class MonitoringSettings(BaseModel):
    """Persisted monitoring preferences and thresholds."""

    enabled: bool = True
    profile: MonitoringProfile = "balanced"

    # Engine cadence
    poll_interval_seconds: int = Field(default=5, ge=2, le=120)
    retention_days: int = Field(default=30, ge=1, le=365)

    # Feature toggles
    monitor_cpu: bool = True
    monitor_memory: bool = True
    monitor_disk: bool = True
    monitor_battery: bool = True
    monitor_network: bool = True
    monitor_temperature: bool = True
    monitor_processes: bool = True
    monitor_hung_windows: bool = True
    monitor_windows_events: bool = True

    # CPU
    cpu_warning_percent: float = Field(default=85.0, ge=1, le=100)
    cpu_critical_percent: float = Field(default=95.0, ge=1, le=100)
    cpu_sustained_seconds: int = Field(default=120, ge=5, le=3600)

    # Memory
    memory_warning_percent: float = Field(default=88.0, ge=1, le=100)
    memory_critical_percent: float = Field(default=95.0, ge=1, le=100)
    memory_sustained_seconds: int = Field(default=120, ge=5, le=3600)

    # Storage
    disk_paths: List[str] = Field(default_factory=list)
    disk_free_warning_gb: float = Field(default=10.0, ge=0.1, le=1000)
    disk_free_critical_gb: float = Field(default=3.0, ge=0.1, le=1000)
    disk_percent_warning: float = Field(default=90.0, ge=1, le=100)
    disk_percent_critical: float = Field(default=97.0, ge=1, le=100)
    disk_sustained_seconds: int = Field(default=60, ge=5, le=3600)

    # Battery
    battery_warning_percent: float = Field(default=20.0, ge=1, le=100)
    battery_critical_percent: float = Field(default=10.0, ge=1, le=100)
    battery_sustained_seconds: int = Field(default=30, ge=5, le=600)

    # Network
    network_targets: List[str] = Field(
        default_factory=lambda: ["1.1.1.1:53", "8.8.8.8:53"]
    )
    network_check_interval_seconds: int = Field(default=15, ge=5, le=300)
    network_timeout_seconds: float = Field(default=4.0, ge=0.5, le=30.0)
    network_failure_seconds: int = Field(default=60, ge=10, le=1800)

    # Temperature (only available when a hardware bridge exists)
    temperature_warning_celsius: float = Field(default=80.0, ge=20, le=120)
    temperature_critical_celsius: float = Field(default=90.0, ge=20, le=130)
    temperature_sustained_seconds: int = Field(default=60, ge=5, le=1800)
    temperature_interval_seconds: int = Field(default=60, ge=15, le=600)

    # Windows events
    windows_event_interval_seconds: int = Field(default=60, ge=15, le=600)
    windows_event_lookback_seconds: int = Field(default=180, ge=30, le=3600)
    windows_event_max_per_log: int = Field(default=25, ge=5, le=100)

    # Applications
    monitored_applications: List[str] = Field(default_factory=list)
    hung_window_seconds: int = Field(default=20, ge=5, le=600)

    # Alert lifecycle
    alert_cooldown_seconds: int = Field(default=900, ge=60, le=86400)
    escalation_seconds: int = Field(default=900, ge=60, le=86400)
    recovery_margin_percent: float = Field(default=3.0, ge=0.0, le=30.0)
    recovery_margin_gb: float = Field(default=2.0, ge=0.0, le=100.0)
    notification_on_recovery: bool = True

    # Presentation
    top_process_count: int = Field(default=5, ge=0, le=20)

    model_config = {"extra": "ignore"}

    @field_validator(
        "disk_paths",
        "network_targets",
        "monitored_applications",
        mode="before",
    )
    @classmethod
    def _clean_lists(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _validate_pairs(self) -> "MonitoringSettings":
        if self.cpu_critical_percent <= self.cpu_warning_percent:
            raise ValueError("cpu_critical_percent must be greater than cpu_warning_percent")
        if self.memory_critical_percent <= self.memory_warning_percent:
            raise ValueError(
                "memory_critical_percent must be greater than memory_warning_percent"
            )
        if self.disk_free_critical_gb >= self.disk_free_warning_gb:
            raise ValueError(
                "disk_free_critical_gb must be less than disk_free_warning_gb"
            )
        if self.disk_percent_critical <= self.disk_percent_warning:
            raise ValueError(
                "disk_percent_critical must be greater than disk_percent_warning"
            )
        if self.battery_critical_percent >= self.battery_warning_percent:
            raise ValueError(
                "battery_critical_percent must be less than battery_warning_percent"
            )
        if self.temperature_critical_celsius <= self.temperature_warning_celsius:
            raise ValueError(
                "temperature_critical_celsius must be greater than temperature_warning_celsius"
            )
        for target in self.network_targets:
            if ":" not in target:
                raise ValueError(
                    f"network target '{target}' must use host:port format"
                )
        return self

    def apply_profile(self, profile: MonitoringProfile) -> "MonitoringSettings":
        data = self.model_dump()
        data["profile"] = profile
        data.update(PROFILE_OVERRIDES[profile])
        return MonitoringSettings(**data)

    @classmethod
    def for_profile(cls, profile: MonitoringProfile) -> "MonitoringSettings":
        return cls().apply_profile(profile)

    def public_dict(self) -> Dict[str, Any]:
        return self.model_dump()


DEFAULT_SETTINGS = MonitoringSettings()
