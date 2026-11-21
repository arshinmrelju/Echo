"""Tests for monitoring profiles, alert lifecycle, collectors, and API wiring."""
from __future__ import annotations

import socket
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError

from echo.monitoring.alerting import AlertManager
from echo.monitoring.collectors import (
    _parse_event_xml,
    check_connectivity,
    collect_snapshot,
    event_dedupe_key,
)
from echo.monitoring.config import MonitoringSettings
from echo.monitoring.engine import MonitoringEngine
from echo.monitoring.models import Finding
from echo.monitoring.service import MonitoringService
from echo.monitoring.store import MonitoringStore


@pytest.fixture
def monitor_store(temp_db):
    return MonitoringStore(db=temp_db)


@pytest.fixture
def alert_manager(monitor_store):
    return AlertManager(monitor_store, cooldown_seconds=30)


@pytest.fixture
async def async_client():
    from echo.api.app import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _backdate_alert(db, alert_id: str, column: str, seconds: int) -> None:
    moment = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with db.transaction() as conn:
        conn.execute(f"UPDATE monitor_alerts SET {column} = ? WHERE id = ?;", (moment, alert_id))


def _raise_warning(manager: AlertManager, key: str = "cpu:high"):
    return manager.raise_alert(
        dedupe_key=key,
        category="cpu",
        severity="warning",
        title="Sustained high CPU usage",
        message="CPU usage is 92%.",
        details={"percent": 92},
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_profile_defaults_and_validation():
    balanced = MonitoringSettings()
    assert balanced.profile == "balanced"
    assert balanced.cpu_warning_percent == 85.0
    assert balanced.network_failure_seconds == 60

    strict = balanced.apply_profile("strict")
    assert strict.profile == "strict"
    assert strict.cpu_warning_percent == 75.0
    assert strict.network_failure_seconds == 30

    quiet = MonitoringSettings.for_profile("quiet")
    assert quiet.cpu_critical_percent == 98.0
    assert quiet.monitor_hung_windows is False

    with pytest.raises(ValidationError):
        MonitoringSettings(cpu_warning_percent=95, cpu_critical_percent=90)
    with pytest.raises(ValidationError):
        MonitoringSettings(network_targets=["not-a-target"])


def test_profile_change_preserves_user_specific_fields():
    custom = MonitoringSettings(
        monitored_applications=["Code.exe"],
        disk_paths=["C:\\"],
        network_targets=["example.com:443"],
    )
    strict = custom.apply_profile("strict")
    assert strict.monitored_applications == ["Code.exe"]
    assert strict.disk_paths == ["C:\\"]
    assert strict.network_targets == ["example.com:443"]
    assert strict.temperature_interval_seconds == 30


# ---------------------------------------------------------------------------
# Alert lifecycle
# ---------------------------------------------------------------------------


def test_alert_dedupe_cooldown_escalation_and_recovery(alert_manager, monitor_store):
    first = _raise_warning(alert_manager)
    assert first["event"] == "triggered"
    alert = first["alert"]
    assert alert["status"] == "active"
    assert alert["occurrences"] == 1
    assert monitor_store.alert_counts()["warning"] == 1

    # Repeated detection within the cooldown must not notify again.
    assert _raise_warning(alert_manager) is None
    active = monitor_store.get_active_alert("cpu:high")
    assert active["occurrences"] == 1

    # After the cooldown, the same condition becomes a reminder.
    _backdate_alert(monitor_store._db, alert["id"], "last_notified_at", 120)
    reminder = _raise_warning(alert_manager)
    assert reminder["event"] == "reminder"
    assert reminder["alert"]["occurrences"] == 2

    # Severity increase notifies immediately, even inside the cooldown.
    escalated = alert_manager.raise_alert(
        dedupe_key="cpu:high",
        category="cpu",
        severity="critical",
        title="Sustained high CPU usage",
        message="CPU usage is 99%.",
        details={"percent": 99},
    )
    assert escalated["event"] == "escalated"
    assert escalated["alert"]["severity"] == "critical"

    recovered = alert_manager.recover("cpu:high", message="CPU usage recovered.")
    assert recovered["type"] == "monitor_recovered"
    assert recovered["alert"]["status"] == "recovered"
    assert monitor_store.alert_counts()["total"] == 0

    # A recovered alert frees the dedupe key for a new active alert.
    again = _raise_warning(alert_manager)
    assert again["event"] == "triggered"
    assert again["alert"]["id"] != alert["id"]


def test_escalation_requires_unresolved_time_and_respects_ack(alert_manager, monitor_store):
    created = _raise_warning(alert_manager)["alert"]
    _backdate_alert(monitor_store._db, created["id"], "first_seen_at", 3600)
    current = monitor_store.get_alert(created["id"])

    payload = alert_manager.maybe_escalate(current, escalation_seconds=900)
    assert payload is not None
    assert payload["alert"]["severity"] == "critical"
    assert payload["alert"]["escalation_level"] == 1

    # Already critical: no further escalation.
    assert alert_manager.maybe_escalate(payload["alert"], escalation_seconds=900) is None

    # Acknowledged alerts do not escalate.
    alert_manager.recover("cpu:high")
    alert_manager.set_cooldown(0)
    second = alert_manager.raise_alert(
        dedupe_key="memory:high",
        category="memory",
        severity="warning",
        title="High memory usage",
        message="Memory usage is 92%.",
    )["alert"]
    _backdate_alert(monitor_store._db, second["id"], "first_seen_at", 3600)
    alert_manager.acknowledge(second["id"])
    assert alert_manager.maybe_escalate(monitor_store.get_alert(second["id"]), 900) is None


def test_event_dedupe_and_transient_alerts(alert_manager, monitor_store):
    finding = Finding(
        dedupe_key="winevent:System:42",
        category="system",
        severity="warning",
        kind="windows_event",
        title="Unexpected shutdown",
        message="Kernel power event",
    )
    assert alert_manager.record_finding(finding) is not None
    assert alert_manager.record_finding(finding) is None
    assert len(monitor_store.list_events()) == 1

    transient = alert_manager.record_transient_alert(
        dedupe_key="event:winevent:System:42",
        category="system",
        severity="critical",
        title="Unexpected shutdown",
        message="Kernel power event",
    )
    assert transient["event"] == "transient"
    assert transient["alert"]["status"] == "resolved"
    assert monitor_store.alert_counts()["total"] == 0
    assert (
        alert_manager.record_transient_alert(
            dedupe_key="event:winevent:System:42",
            category="system",
            severity="critical",
            title="Unexpected shutdown",
            message="Kernel power event",
        )
        is None
    )


# ---------------------------------------------------------------------------
# Engine threshold persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_threshold_persistence_and_recovery(monitor_store):
    settings = MonitoringSettings(cpu_sustained_seconds=10)
    emitted = []

    async def emit(payload):
        emitted.append(payload)

    engine = MonitoringEngine(settings, monitor_store, emit)

    kwargs = {
        "key": "cpu:high",
        "severity": "warning",
        "category": "cpu",
        "title": "Sustained high CPU usage",
        "message": "CPU usage is 92%.",
        "details": {"percent": 92},
        "sustained_seconds": 10,
        "recovery_message": "CPU recovered.",
    }
    await engine._condition(triggered=True, recovered=False, **kwargs)
    assert monitor_store.get_active_alert("cpu:high") is None

    engine._pending["cpu:high"] = time.monotonic() - 11
    await engine._condition(triggered=True, recovered=False, **kwargs)
    assert monitor_store.get_active_alert("cpu:high") is not None

    await engine._condition(triggered=False, recovered=True, **kwargs)
    assert monitor_store.get_active_alert("cpu:high") is None
    assert any(payload["type"] == "monitor_recovered" for payload in emitted)


@pytest.mark.asyncio
async def test_service_settings_roundtrip(monitor_store):
    service = MonitoringService(store=monitor_store)
    await service.update_settings(
        {"cpu_warning_percent": 70.0, "cpu_critical_percent": 90.0}
    )
    assert service.settings.cpu_warning_percent == 70.0

    reloaded = MonitoringService(store=monitor_store)
    assert reloaded.settings.cpu_warning_percent == 70.0

    await reloaded.update_settings({"profile": "strict"})
    assert reloaded.settings.profile == "strict"
    assert reloaded.settings.cpu_warning_percent == 75.0


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def test_snapshot_has_real_system_fields():
    snapshot = collect_snapshot(top_process_count=3)
    assert 0 <= snapshot["cpu"]["percent"] <= 100
    assert 0 <= snapshot["memory"]["percent"] <= 100
    assert snapshot["memory"]["total_gb"] > 0
    assert isinstance(snapshot["disks"], list)
    assert len(snapshot["top_processes"]) <= 3
    assert snapshot["platform"]


def test_connectivity_probe_detects_local_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        result = check_connectivity([f"127.0.0.1:{port}"], timeout=1.0)
        assert result["online"] is True
        assert result["target"] == f"127.0.0.1:{port}"
    finally:
        server.close()

    failed = check_connectivity(["127.0.0.1:1"], timeout=0.2)
    assert failed["online"] is False
    assert failed["errors"]


def test_windows_event_xml_parse_and_dedupe():
    xml = """
    <Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
      <System>
        <Provider Name="Application Error" />
        <EventID>1000</EventID>
        <Level>2</Level>
        <TimeCreated SystemTime="2026-11-20T10:00:00.0000000Z" />
        <EventRecordID>777</EventRecordID>
        <Channel>Application</Channel>
        <Computer>TESTPC</Computer>
      </System>
      <EventData>
        <Data Name="AppName">Sample.exe</Data>
        <Data Name="AppVersion">1.0.0</Data>
      </EventData>
    </Event>
    """
    events = _parse_event_xml(xml)
    assert len(events) == 1
    record = events[0]
    assert record["event_id"] == 1000
    assert record["provider"] == "Application Error"
    assert record["data"]["AppName"] == "Sample.exe"
    assert event_dedupe_key({**record, "log": "Application"}) == "winevent:Application:777"


# ---------------------------------------------------------------------------
# API wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_status_and_lists_endpoints(async_client):
    res = await async_client.get("/api/v1/monitoring/status")
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    assert "counts" in data
    assert "snapshot" in data
    assert data["settings"]["profile"] in ("quiet", "balanced", "strict")

    alerts = await async_client.get("/api/v1/monitoring/alerts?limit=5")
    assert alerts.status_code == 200
    assert "alerts" in alerts.json()

    events = await async_client.get("/api/v1/monitoring/events?limit=5")
    assert events.status_code == 200
    assert "events" in events.json()
