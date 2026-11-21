"""Background monitoring loop.

The engine owns cadence and threshold persistence. Heavy probes run in worker
threads so the daemon event loop stays responsive.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

import psutil

from echo.monitoring import collectors
from echo.monitoring.alerting import AlertManager
from echo.monitoring.config import MonitoringSettings
from echo.monitoring.models import (
    Finding,
    MonitorCategory,
    Severity,
    now_iso,
    parse_iso,
)
from echo.monitoring.store import MonitoringStore

logger = logging.getLogger("echo.monitoring.engine")

EmitFn = Callable[[Dict[str, Any]], Awaitable[None]]

HISTORY_POINTS = 360
PURGE_INTERVAL_SECONDS = 6 * 60 * 60


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "timestamp": None,
        "available": False,
        "cpu": {},
        "memory": {},
        "disks": [],
        "battery": {"present": False, "percent": None, "plugged": None, "seconds_left": None},
        "network": {
            "online": None,
            "latency_ms": None,
            "last_check_at": None,
            "down_kbps": 0.0,
            "up_kbps": 0.0,
            "errors": [],
        },
        "temperature": {
            "available": False,
            "celsius": None,
            "source": None,
            "reason": "Waiting for first hardware probe.",
            "checked_at": None,
        },
        "monitored_applications": [],
        "hung_windows": [],
        "process_count": None,
        "top_processes": [],
        "boot_time": None,
        "uptime_seconds": None,
        "platform": None,
        "windows_events_available": None,
        "alert_counts": {"info": 0, "notice": 0, "warning": 0, "critical": 0, "total": 0, "unacknowledged": 0},
    }


def _rates(previous: Optional[tuple[Dict[str, int], float]], current: Dict[str, int]) -> Dict[str, float]:
    if previous is None:
        return {"down_kbps": 0.0, "up_kbps": 0.0}
    prev_counters, prev_at = previous
    elapsed = max(0.001, time.monotonic() - prev_at)
    down = max(0, current.get("bytes_recv", 0) - prev_counters.get("bytes_recv", 0))
    up = max(0, current.get("bytes_sent", 0) - prev_counters.get("bytes_sent", 0))
    return {
        "down_kbps": round((down * 8) / 1000 / elapsed, 1),
        "up_kbps": round((up * 8) / 1000 / elapsed, 1),
    }


class MonitoringEngine:
    def __init__(
        self,
        settings: MonitoringSettings,
        store: MonitoringStore,
        emit: EmitFn,
    ) -> None:
        self.settings = settings
        self.store = store
        self.alerts = AlertManager(store, settings.alert_cooldown_seconds)
        self._emit = emit
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._started_at: Optional[str] = None
        self._last_error: Optional[str] = None

        self._snapshot = _empty_snapshot()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=HISTORY_POINTS)
        self._pending: Dict[str, float] = {}
        self._last_net_counters: Optional[tuple[Dict[str, int], float]] = None

        self._network_last: Optional[Dict[str, Any]] = None
        self._network_failure_since: Optional[float] = None
        self._network_online: Optional[bool] = None
        self._network_error: Optional[str] = None

        self._temperature: Dict[str, Any] = dict(_empty_snapshot()["temperature"])
        self._temperature_unavailable_until = 0.0
        self._temperature_checked_at: Optional[str] = None

        self._windows_events_available: Optional[bool] = None
        self._windows_events_error: Optional[str] = None
        self._last_windows_event_check: Optional[str] = None
        self._last_temperature_check: Optional[str] = None
        self._last_network_check: Optional[str] = None

        self._app_state: Dict[str, bool] = {}
        self._hung_pending: Dict[str, float] = {}

        # Slow probes run as supervised background tasks so they never stall the
        # snapshot cadence (PowerShell and wevtutil can take seconds).
        self._network_task: Optional[asyncio.Task] = None
        self._temperature_task: Optional[asyncio.Task] = None
        self._events_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._started_at = self._started_at or now_iso()
        self._task = asyncio.create_task(self._run(), name="echo-system-monitoring")
        logger.info("System monitoring engine started")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=8)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            self._task = None
        probes = [self._network_task, self._temperature_task, self._events_task]
        for probe in probes:
            if probe is not None and not probe.done():
                probe.cancel()
        await asyncio.gather(*(probe for probe in probes if probe is not None), return_exceptions=True)
        self._network_task = self._temperature_task = self._events_task = None
        logger.info("System monitoring engine stopped")

    def update_settings(self, settings: MonitoringSettings) -> None:
        self.settings = settings
        self.alerts.set_cooldown(settings.alert_cooldown_seconds)

    async def _emit_payload(self, payload: Optional[Dict[str, Any]]) -> None:
        if not payload:
            return
        try:
            await self._emit(payload)
        except Exception as exc:
            logger.debug("Monitoring payload could not be broadcast: %s", exc)

    async def _supervised(self, label: str, coro: Awaitable[None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = f"{label}: {type(exc).__name__}: {exc}"
            logger.exception("%s probe failed", label)

    def _spawn_probe(
        self, slot: str, label: str, coro_factory: Callable[[], Awaitable[None]]
    ) -> None:
        task = getattr(self, slot)
        if task is not None and not task.done():
            return
        setattr(
            self,
            slot,
            asyncio.create_task(
                self._supervised(label, coro_factory()), name=f"monitor-{label}"
            ),
        )

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    async def _run(self) -> None:
        # Prime psutil's non-blocking CPU counter so the first real sample is valid.
        try:
            await asyncio.to_thread(psutil.cpu_percent, None)
        except Exception:
            pass
        await asyncio.sleep(min(0.5, max(0.1, self.settings.poll_interval_seconds / 4)))

        now = time.monotonic()
        next_poll = now
        next_network = now
        next_temperature = now + 1.0
        next_events = now + 2.0
        next_purge = now + 5.0

        while not self._stop_event.is_set():
            now = time.monotonic()
            settings = self.settings
            try:
                if now >= next_poll:
                    await self._poll_snapshot()
                    next_poll = now + settings.poll_interval_seconds
                if settings.monitor_network and now >= next_network:
                    self._spawn_probe("_network_task", "network", lambda: self._check_network())
                    next_network = now + settings.network_check_interval_seconds
                if settings.monitor_temperature and now >= next_temperature:
                    self._spawn_probe("_temperature_task", "temperature", lambda: self._check_temperature())
                    next_temperature = now + settings.temperature_interval_seconds
                if settings.monitor_windows_events and now >= next_events:
                    self._spawn_probe("_events_task", "windows_events", lambda: self._poll_windows_events())
                    next_events = now + settings.windows_event_interval_seconds
                if now >= next_purge:
                    await self._purge()
                    next_purge = now + PURGE_INTERVAL_SECONDS
                await self._maintain_active_alerts()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Monitoring cycle failed")

            next_due = min(next_poll, next_network, next_temperature, next_events)
            delay = max(0.2, min(2.0, next_due - time.monotonic()))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------ #
    # Snapshot collection
    # ------------------------------------------------------------------ #

    async def _poll_snapshot(self) -> None:
        settings = self.settings
        try:
            snapshot = await asyncio.to_thread(
                collectors.collect_snapshot,
                settings.top_process_count,
                settings.disk_paths,
            )
        except Exception as exc:
            self._last_error = f"Snapshot collection failed: {exc}"
            logger.exception("Snapshot collection failed")
            return

        io_counters = snapshot.pop("network_io", None)
        if io_counters:
            rates = _rates(self._last_net_counters, io_counters)
            self._last_net_counters = (io_counters, time.monotonic())
        else:
            rates = {"down_kbps": 0.0, "up_kbps": 0.0}

        net = self._network_last or {}
        snapshot["network"] = {
            "online": net.get("online", self._network_online),
            "latency_ms": net.get("latency_ms"),
            "last_check_at": net.get("checked_at") or self._last_network_check,
            "down_kbps": rates["down_kbps"],
            "up_kbps": rates["up_kbps"],
            "errors": net.get("errors", []),
        }
        snapshot["temperature"] = dict(self._temperature)
        snapshot["windows_events_available"] = self._windows_events_available
        snapshot["windows_events_error"] = self._windows_events_error
        snapshot["available"] = True

        if settings.monitor_processes and settings.monitored_applications:
            try:
                apps = await asyncio.to_thread(
                    collectors.collect_processes, settings.monitored_applications
                )
            except Exception:
                apps = self._snapshot.get("monitored_applications", [])
            snapshot["monitored_applications"] = apps
            await self._evaluate_applications(apps)
        else:
            snapshot["monitored_applications"] = []
            self._app_state = {}

        hung: List[Dict[str, Any]] = []
        if settings.monitor_processes and settings.monitor_hung_windows:
            try:
                hung = await asyncio.to_thread(collectors.collect_hung_windows)
            except Exception:
                hung = []
        snapshot["hung_windows"] = hung
        await self._evaluate_hung_windows(hung)

        snapshot["alert_counts"] = self.store.alert_counts()
        self._snapshot = snapshot
        self._history.append(
            {
                "t": snapshot["timestamp"],
                "cpu": snapshot["cpu"].get("percent", 0),
                "memory": snapshot["memory"].get("percent", 0),
                "disk_free_gb": min(
                    (disk.get("free_gb", 0) for disk in snapshot.get("disks", [])),
                    default=None,
                ),
                "down_kbps": rates["down_kbps"],
                "up_kbps": rates["up_kbps"],
            }
        )

        await self._evaluate_cpu(snapshot)
        await self._evaluate_memory(snapshot)
        await self._evaluate_disks(snapshot)
        await self._evaluate_battery(snapshot)

        # Refresh counts after evaluations so the snapshot reflects new alerts.
        snapshot["alert_counts"] = self.store.alert_counts()

        await self._emit_payload({"type": "monitor_snapshot", "snapshot": snapshot})

    # ------------------------------------------------------------------ #
    # Threshold evaluation
    # ------------------------------------------------------------------ #

    async def _condition(
        self,
        *,
        key: str,
        triggered: bool,
        severity: str,
        category: str,
        title: str,
        message: str,
        details: Dict[str, Any],
        sustained_seconds: int,
        recovered: bool,
        recovery_message: str,
    ) -> None:
        now = time.monotonic()
        if triggered:
            first = self._pending.setdefault(key, now)
            if now - first >= sustained_seconds:
                payload = self.alerts.raise_alert(
                    dedupe_key=key,
                    category=category,
                    severity=severity,
                    title=title,
                    message=message,
                    details=details,
                )
                await self._emit_payload(payload)
                return
            return

        self._pending.pop(key, None)
        if recovered:
            payload = self.alerts.recover(key, message=recovery_message)
            await self._emit_payload(payload)

    async def _evaluate_cpu(self, snapshot: Dict[str, Any]) -> None:
        settings = self.settings
        if not settings.monitor_cpu:
            await self._emit_payload(self.alerts.recover("cpu:high", notify=False))
            return
        percent = float(snapshot["cpu"].get("percent") or 0.0)
        triggered = percent >= settings.cpu_warning_percent
        severity = (
            Severity.CRITICAL.value
            if percent >= settings.cpu_critical_percent
            else Severity.WARNING.value
        )
        recovered = percent < settings.cpu_warning_percent - settings.recovery_margin_percent
        await self._condition(
            key="cpu:high",
            triggered=triggered,
            severity=severity,
            category=MonitorCategory.CPU.value,
            title="Sustained high CPU usage",
            message=f"CPU usage is {percent:.1f}% (warning at {settings.cpu_warning_percent:.0f}%).",
            details={"percent": percent, "cores": snapshot["cpu"].get("cores_logical")},
            sustained_seconds=settings.cpu_sustained_seconds,
            recovered=recovered,
            recovery_message=f"CPU usage recovered to {percent:.1f}%.",
        )

    async def _evaluate_memory(self, snapshot: Dict[str, Any]) -> None:
        settings = self.settings
        if not settings.monitor_memory:
            await self._emit_payload(self.alerts.recover("memory:high", notify=False))
            return
        memory = snapshot["memory"]
        percent = float(memory.get("percent") or 0.0)
        triggered = percent >= settings.memory_warning_percent
        severity = (
            Severity.CRITICAL.value
            if percent >= settings.memory_critical_percent
            else Severity.WARNING.value
        )
        recovered = percent < settings.memory_warning_percent - settings.recovery_margin_percent
        await self._condition(
            key="memory:high",
            triggered=triggered,
            severity=severity,
            category=MonitorCategory.MEMORY.value,
            title="High memory usage",
            message=(
                f"Memory usage is {percent:.1f}% "
                f"({memory.get('used_gb', 0):.1f} GB used, "
                f"{memory.get('available_gb', 0):.1f} GB available)."
            ),
            details={
                "percent": percent,
                "used_gb": memory.get("used_gb"),
                "available_gb": memory.get("available_gb"),
                "total_gb": memory.get("total_gb"),
            },
            sustained_seconds=settings.memory_sustained_seconds,
            recovered=recovered,
            recovery_message=f"Memory usage recovered to {percent:.1f}%.",
        )

    async def _evaluate_disks(self, snapshot: Dict[str, Any]) -> None:
        settings = self.settings
        active_disk_keys: Set[str] = set()
        if not settings.monitor_disk:
            for alert in self.store.list_active_alerts():
                if alert["dedupe_key"].startswith("disk:low:"):
                    self.alerts.recover(alert["dedupe_key"], notify=False)
            return

        for disk in snapshot.get("disks", []):
            key = f"disk:low:{disk['path'].lower()}"
            active_disk_keys.add(key)
            free_gb = float(disk.get("free_gb") or 0.0)
            percent = float(disk.get("percent") or 0.0)
            triggered = (
                free_gb < settings.disk_free_warning_gb
                or percent >= settings.disk_percent_warning
            )
            severity = (
                Severity.CRITICAL.value
                if free_gb < settings.disk_free_critical_gb
                or percent >= settings.disk_percent_critical
                else Severity.WARNING.value
            )
            recovered = (
                free_gb >= settings.disk_free_warning_gb + settings.recovery_margin_gb
                and percent <= settings.disk_percent_warning - settings.recovery_margin_percent
            )
            await self._condition(
                key=key,
                triggered=triggered,
                severity=severity,
                category=MonitorCategory.DISK.value,
                title=f"Low disk space on {disk['path']}",
                message=(
                    f"{disk['path']} has {free_gb:.1f} GB free ({percent:.1f}% used). "
                    f"Warning threshold is {settings.disk_free_warning_gb:.1f} GB."
                ),
                details=disk,
                sustained_seconds=settings.disk_sustained_seconds,
                recovered=recovered,
                recovery_message=(
                    f"{disk['path']} recovered to {free_gb:.1f} GB free ({percent:.1f}% used)."
                ),
            )

        # A removed/renamed volume should not leave a permanently active alert.
        for alert in self.store.list_active_alerts():
            if alert["dedupe_key"].startswith("disk:low:") and alert["dedupe_key"] not in active_disk_keys:
                self.alerts.recover(alert["dedupe_key"], notify=False)

    async def _evaluate_battery(self, snapshot: Dict[str, Any]) -> None:
        settings = self.settings
        battery = snapshot.get("battery") or {}
        if not settings.monitor_battery or not battery.get("present"):
            await self._emit_payload(self.alerts.recover("battery:low", notify=False))
            return
        percent = battery.get("percent")
        if percent is None:
            await self._emit_payload(self.alerts.recover("battery:low", notify=False))
            return
        plugged = bool(battery.get("plugged"))
        triggered = (not plugged) and percent <= settings.battery_warning_percent
        severity = (
            Severity.CRITICAL.value
            if percent <= settings.battery_critical_percent
            else Severity.WARNING.value
        )
        recovered = plugged or percent > settings.battery_warning_percent
        minutes_left = battery.get("seconds_left")
        suffix = f" About {int(minutes_left // 60)} minutes remaining." if minutes_left else ""
        await self._condition(
            key="battery:low",
            triggered=triggered,
            severity=severity,
            category=MonitorCategory.BATTERY.value,
            title="Low battery",
            message=(
                f"Battery is at {percent:.0f}% and discharging."
                f"{suffix}"
            ),
            details=battery,
            sustained_seconds=settings.battery_sustained_seconds,
            recovered=recovered,
            recovery_message=(
                "Battery is charging."
                if plugged
                else f"Battery recovered to {percent:.0f}%."
            ),
        )

    # ------------------------------------------------------------------ #
    # Network
    # ------------------------------------------------------------------ #

    async def _check_network(self) -> None:
        settings = self.settings
        if not settings.network_targets:
            self._network_last = {
                "online": None,
                "latency_ms": None,
                "checked_at": now_iso(),
                "errors": ["No connectivity targets are configured."],
            }
            return
        try:
            result = await asyncio.to_thread(
                collectors.check_connectivity,
                settings.network_targets,
                settings.network_timeout_seconds,
            )
        except Exception as exc:
            result = {
                "online": False,
                "latency_ms": None,
                "checked_at": now_iso(),
                "errors": [str(exc)],
            }
        self._network_last = result
        self._last_network_check = result["checked_at"]
        self._network_error = "; ".join(result.get("errors") or []) or None
        now = time.monotonic()

        if result["online"]:
            was_offline = self._network_online is False or self._network_failure_since is not None
            self._network_failure_since = None
            self._network_online = True
            if was_offline:
                payload = self.alerts.recover(
                    "network:offline",
                    message=(
                        f"Internet connectivity restored via {result.get('target')} "
                        f"({result.get('latency_ms')} ms)."
                    ),
                )
                await self._emit_payload(payload)
                finding = Finding(
                    dedupe_key=None,
                    category=MonitorCategory.NETWORK.value,
                    severity=Severity.INFO.value,
                    kind="connectivity",
                    title="Internet connectivity restored",
                    message=(
                        f"Reachable via {result.get('target')} "
                        f"({result.get('latency_ms')} ms)."
                    ),
                    details=result,
                    occurred_at=result["checked_at"],
                )
                await self._emit_payload(self.alerts.record_finding(finding))
            return

        self._network_online = False
        if self._network_failure_since is None:
            self._network_failure_since = now
            finding = Finding(
                dedupe_key=None,
                category=MonitorCategory.NETWORK.value,
                severity=Severity.NOTICE.value,
                kind="connectivity",
                title="Internet connectivity lost",
                message="No configured connectivity target is reachable. Waiting before alerting.",
                details=result,
                occurred_at=result["checked_at"],
            )
            await self._emit_payload(self.alerts.record_finding(finding))

        elapsed = now - self._network_failure_since
        if elapsed >= settings.network_failure_seconds:
            payload = self.alerts.raise_alert(
                dedupe_key="network:offline",
                category=MonitorCategory.NETWORK.value,
                severity=Severity.WARNING.value,
                title="Internet connectivity unavailable",
                message=(
                    f"No connectivity target has been reachable for {int(elapsed)} seconds."
                ),
                details={
                    "targets": settings.network_targets,
                    "errors": result.get("errors", []),
                },
            )
            await self._emit_payload(payload)

    # ------------------------------------------------------------------ #
    # Temperature
    # ------------------------------------------------------------------ #

    async def _check_temperature(self) -> None:
        settings = self.settings
        now = time.monotonic()
        if now < self._temperature_unavailable_until:
            return
        result = await asyncio.to_thread(collectors.collect_temperature)
        self._temperature_checked_at = result.get("checked_at") or now_iso()
        self._last_temperature_check = self._temperature_checked_at
        self._temperature = result
        if not result.get("available"):
            # Hardware probes are expensive; do not retry a missing sensor constantly.
            self._temperature_unavailable_until = now + 600
            await self._emit_payload(self.alerts.recover("temperature:high", notify=False))
            return
        celsius = result.get("celsius")
        if celsius is None:
            return
        triggered = celsius >= settings.temperature_warning_celsius
        severity = (
            Severity.CRITICAL.value
            if celsius >= settings.temperature_critical_celsius
            else Severity.WARNING.value
        )
        recovered = celsius < settings.temperature_warning_celsius - settings.recovery_margin_percent
        await self._condition(
            key="temperature:high",
            triggered=triggered,
            severity=severity,
            category=MonitorCategory.TEMPERATURE.value,
            title="System overheating",
            message=(
                f"CPU temperature is {celsius:.1f}°C "
                f"(warning at {settings.temperature_warning_celsius:.0f}°C)."
            ),
            details=result,
            sustained_seconds=settings.temperature_sustained_seconds,
            recovered=recovered,
            recovery_message=f"Temperature recovered to {celsius:.1f}°C.",
        )

    # ------------------------------------------------------------------ #
    # Applications
    # ------------------------------------------------------------------ #

    async def _evaluate_applications(self, apps: List[Dict[str, Any]]) -> None:
        for app in apps:
            name = app["name"]
            running = bool(app["running"])
            previous = self._app_state.get(name)
            if previous is None:
                self._app_state[name] = running
                continue
            if previous == running:
                continue
            self._app_state[name] = running
            if running:
                finding = Finding(
                    dedupe_key=None,
                    category=MonitorCategory.APPLICATION.value,
                    severity=Severity.INFO.value,
                    kind="app_state",
                    title=f"Monitored application running: {name}",
                    message=f"{name} is now running (PID {', '.join(map(str, app.get('pids') or []))}).",
                    details=app,
                )
            else:
                finding = Finding(
                    dedupe_key=None,
                    category=MonitorCategory.APPLICATION.value,
                    severity=Severity.NOTICE.value,
                    kind="app_state",
                    title=f"Monitored application stopped: {name}",
                    message=f"{name} is no longer running.",
                    details=app,
                )
            await self._emit_payload(self.alerts.record_finding(finding))

    async def _evaluate_hung_windows(self, hung: List[Dict[str, Any]]) -> None:
        settings = self.settings
        active_keys: Set[str] = set()
        if not settings.monitor_hung_windows or not settings.monitor_processes:
            for alert in self.store.list_active_alerts():
                if alert["dedupe_key"].startswith("hung:"):
                    self.alerts.recover(alert["dedupe_key"], notify=False)
            self._hung_pending.clear()
            return

        now = time.monotonic()
        for window in hung:
            key = (
                f"{str(window.get('process_name') or 'unknown').lower()}:"
                f"{str(window.get('title') or '').lower()}"
            )
            active_keys.add(key)
            first = self._hung_pending.setdefault(key, now)
            if now - first < settings.hung_window_seconds:
                continue
            payload = self.alerts.raise_alert(
                dedupe_key=f"hung:{key}",
                category=MonitorCategory.APPLICATION.value,
                severity=Severity.WARNING.value,
                title="Application not responding",
                message=(
                    f"{window.get('process_name') or 'An application'} is not responding: "
                    f"{window.get('title')}"
                ),
                details=window,
            )
            await self._emit_payload(payload)

        for key in list(self._hung_pending):
            if key not in active_keys:
                self._hung_pending.pop(key, None)
                payload = self.alerts.recover(
                    f"hung:{key}", message="Application is responding again."
                )
                await self._emit_payload(payload)

    # ------------------------------------------------------------------ #
    # Windows Event Log
    # ------------------------------------------------------------------ #

    async def _poll_windows_events(self) -> None:
        settings = self.settings
        result = await asyncio.to_thread(
            collectors.read_windows_events,
            settings.windows_event_lookback_seconds,
            settings.windows_event_max_per_log,
        )
        self._windows_events_available = bool(result.get("available"))
        self._windows_events_error = "; ".join(result.get("errors") or []) or None
        self._last_windows_event_check = result.get("checked_at") or now_iso()
        if not result.get("available"):
            return

        monitored = {
            collectors.normalize_process_name(name)
            for name in settings.monitored_applications
            if name.strip()
        }

        for record in result.get("events", []):
            await self._process_windows_event(record, monitored)

    async def _process_windows_event(
        self, record: Dict[str, Any], monitored: Set[str]
    ) -> None:
        event_id = int(record.get("event_id") or 0)
        log_name = record.get("log") or record.get("channel") or ""
        dedupe_key = collectors.event_dedupe_key(record)
        occurred_at = record.get("time_created")
        details = {
            "provider": record.get("provider"),
            "event_id": event_id,
            "level": record.get("level"),
            "channel": record.get("channel"),
            "record_id": record.get("record_id"),
            "computer": record.get("computer"),
            "data": record.get("data") or {},
        }

        if log_name == "Application":
            app_name = collectors.event_application_name(record) or "Unknown application"
            normalized = collectors.normalize_process_name(app_name)
            is_monitored = normalized in monitored
            is_hang = (record.get("provider") == "Application Hang") or event_id == 1002
            severity = Severity.WARNING.value if is_monitored else Severity.NOTICE.value
            title = (
                f"Monitored application {'stopped responding' if is_hang else 'crashed'}: {app_name}"
                if is_monitored
                else f"Application {'hang' if is_hang else 'crash'}: {app_name}"
            )
            finding = Finding(
                dedupe_key=dedupe_key,
                category=MonitorCategory.APPLICATION.value,
                severity=severity,
                kind="application_event",
                title=title,
                message=collectors.event_summary(record),
                details={**details, "application": app_name, "monitored": is_monitored},
                occurred_at=occurred_at,
            )
            await self._emit_payload(self.alerts.record_finding(finding))
            if is_monitored:
                payload = self.alerts.record_transient_alert(
                    dedupe_key=f"event:{dedupe_key}",
                    category=MonitorCategory.APPLICATION.value,
                    severity=severity,
                    title=title,
                    message=collectors.event_summary(record),
                    details={**details, "application": app_name},
                    occurred_at=occurred_at,
                )
                await self._emit_payload(payload)
            return

        mapping = collectors.SYSTEM_EVENT_MAP.get(event_id)
        if mapping is None:
            return

        severity = mapping["severity"]
        level = int(record.get("level") or 0)
        # Several providers log informational entries with IDs that are usually
        # errors elsewhere (e.g. Ntfs shadow-copy 98). Do not turn those into
        # warning alerts; keep them in the feed at NOTICE.
        if level >= 4 and severity in (Severity.WARNING.value, Severity.CRITICAL.value):
            severity = Severity.NOTICE.value
        title = mapping["title"]
        finding = Finding(
            dedupe_key=dedupe_key,
            category=MonitorCategory.WINDOWS_EVENT.value
            if event_id not in (41, 1001, 6005, 6006, 6008)
            else MonitorCategory.SYSTEM.value,
            severity=severity,
            kind="windows_event",
            title=title,
            message=collectors.event_summary(record),
            details=details,
            occurred_at=occurred_at,
        )
        await self._emit_payload(self.alerts.record_finding(finding))

        if severity in (Severity.WARNING.value, Severity.CRITICAL.value):
            payload = self.alerts.record_transient_alert(
                dedupe_key=f"event:{dedupe_key}",
                category=finding.category,
                severity=severity,
                title=title,
                message=collectors.event_summary(record),
                details=details,
                occurred_at=occurred_at,
            )
            await self._emit_payload(payload)

    # ------------------------------------------------------------------ #
    # Escalation and maintenance
    # ------------------------------------------------------------------ #

    async def _maintain_active_alerts(self) -> None:
        settings = self.settings
        active = self.store.list_active_alerts()
        for alert in active:
            if not settings.monitor_cpu and alert["dedupe_key"] == "cpu:high":
                continue
            payload = self.alerts.maybe_escalate(alert, settings.escalation_seconds)
            await self._emit_payload(payload)

        if not settings.monitor_temperature:
            await self._emit_payload(self.alerts.recover("temperature:high", notify=False))
        if not settings.monitor_network:
            await self._emit_payload(self.alerts.recover("network:offline", notify=False))

    async def _purge(self) -> None:
        try:
            result = await asyncio.to_thread(
                self.store.purge, self.settings.retention_days
            )
            if result["alerts"] or result["events"]:
                logger.info(
                    "Monitoring retention purge removed %d alerts and %d events",
                    result["alerts"],
                    result["events"],
                )
        except Exception as exc:
            logger.warning("Monitoring retention purge failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        settings = self.settings
        return {
            "running": self.running,
            "enabled": settings.enabled,
            "profile": settings.profile,
            "started_at": self._started_at,
            "last_error": self._last_error,
            "last_poll_at": self._snapshot.get("timestamp"),
            "last_network_check_at": self._last_network_check,
            "last_temperature_check_at": self._last_temperature_check,
            "last_windows_event_check_at": self._last_windows_event_check,
            "snapshot": self._snapshot,
            "history": list(self._history)[-180:],
            "counts": self.store.alert_counts(),
            "availability": {
                "temperature": {
                    "available": bool(self._temperature.get("available")),
                    "reason": self._temperature.get("reason"),
                    "source": self._temperature.get("source"),
                },
                "battery": {
                    "available": bool(self._snapshot.get("battery", {}).get("present"))
                },
                "windows_events": {
                    "available": self._windows_events_available,
                    "error": self._windows_events_error,
                },
                "network": {
                    "online": self._network_online,
                    "error": self._network_error,
                },
            },
        }


def uptime_from_boot(boot_time: Optional[str]) -> Optional[float]:
    parsed = parse_iso(boot_time)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
