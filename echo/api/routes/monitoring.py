"""System monitoring API: status, dashboard data, settings, and alert actions."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from echo.api.schemas import MonitoringSettingsUpdateRequest
from echo.monitoring.service import get_monitoring_service

router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring"])


@router.get("/status")
async def monitoring_status():
    return get_monitoring_service().status()


@router.get("/snapshot")
async def monitoring_snapshot():
    status = get_monitoring_service().status()
    return {
        "snapshot": status["snapshot"],
        "history": status["history"],
        "counts": status["counts"],
        "running": status["running"],
    }


@router.get("/settings")
async def monitoring_settings():
    return get_monitoring_service().settings_payload()


@router.put("/settings")
async def update_monitoring_settings(payload: MonitoringSettingsUpdateRequest):
    service = get_monitoring_service()
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"success": True, "settings": service.settings.public_dict(), "status": service.status()}
    try:
        settings = await service.update_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "settings": settings.public_dict(), "status": service.status()}


@router.post("/start")
async def start_monitoring():
    service = get_monitoring_service()
    started = await service.start()
    return {"success": started, "status": service.status()}


@router.post("/stop")
async def stop_monitoring():
    service = get_monitoring_service()
    await service.stop()
    return {"success": True, "status": service.status()}


@router.get("/alerts")
async def list_alerts(
    status: Optional[Literal["active", "recovered", "resolved"]] = None,
    category: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    alerts = get_monitoring_service().list_alerts(status=status, category=category, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    service = get_monitoring_service()
    alert = await service.acknowledge(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "alert": alert}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    service = get_monitoring_service()
    alert = await service.resolve(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "alert": alert}


@router.get("/events")
async def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    category: Optional[str] = None,
    severity: Optional[Literal["info", "notice", "warning", "critical"]] = None,
):
    events = get_monitoring_service().list_events(
        limit=limit, category=category, severity=severity
    )
    return {"events": events, "count": len(events)}
