"""Monitoring service facade: lifecycle, settings, status, and user actions."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from echo.api.ws_hub import manager
from echo.core.events import Event, get_event_bus
from echo.monitoring.config import MonitoringSettings
from echo.monitoring.engine import MonitoringEngine
from echo.monitoring.models import now_iso
from echo.monitoring.store import MonitoringStore

logger = logging.getLogger("echo.monitoring.service")


class MonitoringService:
    def __init__(self, store: Optional[MonitoringStore] = None) -> None:
        self._store = store or MonitoringStore()
        self.settings = self._load_settings()
        self._engine = MonitoringEngine(self.settings, self._store, self._broadcast)
        self._started_at: Optional[str] = None
        self._start_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load_settings(self) -> MonitoringSettings:
        raw = self._store.load_settings()
        if raw:
            try:
                return MonitoringSettings(**raw)
            except Exception as exc:
                logger.warning("Stored monitoring settings are invalid: %s", exc)
        return MonitoringSettings()

    def _save_settings(self) -> None:
        try:
            self._store.save_settings(self.settings.model_dump())
        except Exception as exc:
            logger.error("Could not persist monitoring settings: %s", exc)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def running(self) -> bool:
        return self._engine.running

    async def start(self, enable: bool = True) -> bool:
        async with self._start_lock:
            if enable and not self.settings.enabled:
                self.settings = self.settings.model_copy(update={"enabled": True})
                self._save_settings()
            self._engine.update_settings(self.settings)
            await self._engine.start()
            self._started_at = self._started_at or now_iso()
        await self._broadcast(self.status_event())
        return self._engine.running

    async def stop(self, disable: bool = True) -> None:
        async with self._start_lock:
            if disable and self.settings.enabled:
                self.settings = self.settings.model_copy(update={"enabled": False})
                self._save_settings()
            await self._engine.stop()
        await self._broadcast(self.status_event())

    async def update_settings(self, updates: Dict[str, Any]) -> MonitoringSettings:
        profile = updates.get("profile")
        if profile and profile != self.settings.profile:
            base = self.settings.apply_profile(profile)
            merged = base.model_dump()
            remaining = {key: value for key, value in updates.items() if key != "profile"}
            merged.update(remaining)
        else:
            merged = self.settings.model_dump()
            for key, value in updates.items():
                if key in type(self.settings).model_fields:
                    merged[key] = value
        new_settings = MonitoringSettings(**merged)

        enabled_changed = new_settings.enabled != self.settings.enabled
        self.settings = new_settings
        self._save_settings()
        self._engine.update_settings(self.settings)

        if enabled_changed:
            if new_settings.enabled:
                await self.start(enable=False)
            else:
                await self.stop(disable=False)
        else:
            await self._broadcast(self.status_event())
        return self.settings

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        status = self._engine.status()
        status["settings"] = self.settings.public_dict()
        status["enabled"] = self.settings.enabled
        status["running"] = self._engine.running
        status["service_started_at"] = self._started_at
        return status

    def status_event(self) -> Dict[str, Any]:
        return {"type": "monitor_status", **self.status()}

    def settings_payload(self) -> Dict[str, Any]:
        return {
            "settings": self.settings.public_dict(),
            "defaults": MonitoringSettings().model_dump(),
            "profiles": {
                "quiet": MonitoringSettings.for_profile("quiet").model_dump(),
                "balanced": MonitoringSettings.for_profile("balanced").model_dump(),
                "strict": MonitoringSettings.for_profile("strict").model_dump(),
            },
            "status": self.status(),
        }

    # ------------------------------------------------------------------ #
    # Alerts and events
    # ------------------------------------------------------------------ #

    def list_alerts(
        self, status: Optional[str] = None, category: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self._store.list_alerts(status=status, category=category, limit=limit)

    def list_events(
        self, limit: int = 100, category: Optional[str] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self._store.list_events(limit=limit, category=category, severity=severity)

    def alert_counts(self) -> Dict[str, int]:
        return self._store.alert_counts()

    async def acknowledge(self, alert_id: str) -> Optional[Dict[str, Any]]:
        payload = self._engine.alerts.acknowledge(alert_id)
        if payload is None:
            return None
        await self._broadcast(payload)
        await self._broadcast(self.status_event())
        return payload["alert"]

    async def resolve(self, alert_id: str) -> Optional[Dict[str, Any]]:
        payload = self._engine.alerts.resolve(alert_id)
        if payload is None:
            return None
        await self._broadcast(payload)
        await self._broadcast(self.status_event())
        return payload["alert"]

    # ------------------------------------------------------------------ #
    # WebSocket commands
    # ------------------------------------------------------------------ #

    async def handle_ws_command(self, msg_type: str, data: Dict[str, Any]) -> None:
        if msg_type == "monitor_status_request":
            await self._broadcast(self.status_event())
        elif msg_type == "monitor_start":
            await self.start()
        elif msg_type == "monitor_stop":
            await self.stop()
        elif msg_type == "monitor_acknowledge":
            alert_id = data.get("alert_id")
            if alert_id:
                await self.acknowledge(str(alert_id))
        elif msg_type == "monitor_resolve":
            alert_id = data.get("alert_id")
            if alert_id:
                await self.resolve(str(alert_id))
        else:
            logger.debug("Unhandled monitoring websocket command: %s", msg_type)

    # ------------------------------------------------------------------ #
    # Fan-out
    # ------------------------------------------------------------------ #

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        try:
            await manager.broadcast(payload)
        except Exception as exc:  # pragma: no cover - transport failure
            logger.debug("Monitoring broadcast failed: %s", exc)

        topic = payload.get("type")
        if topic in ("monitor_alert", "monitor_recovered", "monitor_event"):
            try:
                await get_event_bus().publish(Event(topic=topic, payload=payload))
            except Exception as exc:  # pragma: no cover - subscriber failure
                logger.debug("Monitoring event publication failed: %s", exc)


_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    global _service
    if _service is None:
        _service = MonitoringService()
    return _service


def set_monitoring_service(service: Optional[MonitoringService]) -> None:
    """Test seam."""
    global _service
    _service = service
