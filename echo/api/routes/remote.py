"""Remote relay API. These routes are loopback-only like the rest of the daemon."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from echo.api.schemas import RemotePauseRequest, RemoteSettingsUpdateRequest, RemoteUserRequest
from echo.remote.service import get_remote_service

router = APIRouter(prefix="/api/v1/remote", tags=["Remote Relay"])


@router.get("/status")
async def remote_status():
    return get_remote_service().status()


@router.get("/settings")
async def remote_settings():
    return get_remote_service().settings_payload()


@router.put("/settings")
async def update_remote_settings(payload: RemoteSettingsUpdateRequest):
    service = get_remote_service()
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"success": True, "settings": service.settings.public_dict(), "status": service.status()}
    try:
        settings = await service.update_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "settings": settings.public_dict(), "status": service.status()}


@router.post("/start")
async def start_remote():
    service = get_remote_service()
    started = await service.start()
    return {"success": started, "status": service.status()}


@router.post("/stop")
async def stop_remote():
    service = get_remote_service()
    await service.stop()
    return {"success": True, "status": service.status()}


@router.post("/reconnect")
async def reconnect_remote():
    service = get_remote_service()
    if service.running:
        await service.stop(disable=False)
    started = await service.start(enable=False)
    return {"success": started, "status": service.status()}


@router.post("/pairing/start")
async def start_pairing():
    return await get_remote_service().start_pairing()


@router.post("/pairing/cancel")
async def cancel_pairing():
    await get_remote_service().cancel_pairing()
    return {"success": True}


@router.get("/users")
async def list_users():
    return {"users": get_remote_service().store.list_users()}


@router.post("/users")
async def add_user(payload: RemoteUserRequest):
    try:
        user = await get_remote_service().add_allowed_user(payload.telegram_id, payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "user": user}


@router.delete("/users/{telegram_id}")
async def remove_user(telegram_id: int):
    removed = await get_remote_service().remove_user(telegram_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Telegram user not found")
    return {"success": True, "telegram_id": telegram_id}


@router.get("/commands")
async def list_commands(limit: int = Query(default=100, ge=1, le=500)):
    commands = get_remote_service().list_commands(limit=limit)
    return {"commands": commands, "count": len(commands)}


@router.get("/notifications")
async def list_notifications(
    status: Optional[Literal["queued", "sending", "sent", "failed", "expired", "suppressed"]] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    notifications = get_remote_service().list_notifications(status=status, limit=limit)
    return {"notifications": notifications, "count": len(notifications)}


@router.post("/notifications/{notification_id}/retry")
async def retry_notification(notification_id: str):
    retried = await get_remote_service().retry_notification(notification_id)
    if not retried:
        raise HTTPException(status_code=404, detail="Notification is not retryable")
    return {"success": True, "id": notification_id}


@router.post("/notifications/test")
async def test_notification():
    sent = await get_remote_service().send_test_notification()
    if not sent:
        raise HTTPException(
            status_code=409,
            detail="Configure a bot token and owner before sending a test notification.",
        )
    return {"success": True}


@router.get("/pending")
async def pending_actions():
    actions = get_remote_service().store.list_pending_actions("pending")
    return {"actions": actions, "count": len(actions)}


@router.post("/pause")
async def pause_remote(payload: Optional[RemotePauseRequest] = None):
    service = get_remote_service()
    await service.pause(payload.reason if payload else None)
    return {"success": True, "status": service.status()}


@router.post("/resume")
async def resume_remote():
    service = get_remote_service()
    await service.resume()
    return {"success": True, "status": service.status()}


@router.get("/tasks")
async def remote_tasks(limit: int = Query(default=50, ge=1, le=200)):
    tasks = get_remote_service().store.list_remote_tasks(limit=limit)
    return {"tasks": tasks, "count": len(tasks)}
