import inspect
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from echo.api.ws_hub import ConnectionManager, manager
from echo.core.chat_service import get_chat_turn_service

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger("echo.websocket")

__all__ = ["router", "manager", "ConnectionManager"]


async def _voice_service():
    """Import lazily so the chat gateway still works if voice deps are absent."""
    from echo.voice.service import get_voice_service

    return get_voice_service()


async def _monitoring_service():
    from echo.monitoring.service import get_monitoring_service

    return get_monitoring_service()


async def _remote_service():
    from echo.remote.service import get_remote_service

    return get_remote_service()


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    chat_service = get_chat_turn_service()

    await manager.send_json(
        websocket,
        {
            "type": "connection_established",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
        },
    )

    # Voice status so the UI can render the correct controls on first paint.
    try:
        service = await _voice_service()
        await manager.send_json(websocket, service.status_event())
    except Exception as exc:
        logger.debug("Voice status unavailable at connect: %s", exc)

    # Monitoring status so the dashboard and badge are correct immediately.
    try:
        monitoring = await _monitoring_service()
        await manager.send_json(websocket, monitoring.status_event())
    except Exception as exc:
        logger.debug("Monitoring status unavailable at connect: %s", exc)

    # Remote relay status for the sidebar badge and panel.
    try:
        remote = await _remote_service()
        await manager.send_json(websocket, await remote.status_event())
    except Exception as exc:
        logger.debug("Remote status unavailable at connect: %s", exc)

    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                await manager.send_json(
                    websocket, {"type": "error", "message": "Invalid JSON format"}
                )
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await manager.send_json(
                    websocket,
                    {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()},
                )
                continue

            if msg_type == "stop":
                conv_id = data.get("conversation_id", "default")
                chat_service.cancel(conv_id)
                await manager.send_json(
                    websocket, {"type": "generation_stopped", "conversation_id": conv_id}
                )
                continue

            if msg_type == "chat_message":
                content = (data.get("content") or "").strip()
                if not content:
                    await manager.send_json(
                        websocket, {"type": "error", "message": "Message content cannot be empty"}
                    )
                    continue

                async def emit(payload, _ws=websocket):
                    await manager.broadcast(payload)

                chat_service.start_turn(
                    conversation_id=data.get("conversation_id"),
                    content=content,
                    emit=emit,
                    source="text",
                )
                continue

            if isinstance(msg_type, str) and msg_type.startswith("voice_"):
                try:
                    service = await _voice_service()
                    result = service.handle_ws_command(msg_type, data)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    logger.error("Voice command %s failed: %s", msg_type, exc)
                    await manager.send_json(
                        websocket,
                        {
                            "type": "voice_error",
                            "code": "command_failed",
                            "message": str(exc),
                        },
                    )
                continue

            if isinstance(msg_type, str) and msg_type.startswith("remote_"):
                try:
                    remote = await _remote_service()
                    await remote.handle_ws_command(msg_type, data)
                except Exception as exc:
                    logger.error("Remote command %s failed: %s", msg_type, exc)
                    await manager.send_json(
                        websocket,
                        {
                            "type": "remote_error",
                            "code": "command_failed",
                            "message": str(exc),
                        },
                    )
                continue

            if isinstance(msg_type, str) and msg_type.startswith("monitor_"):
                try:
                    monitoring = await _monitoring_service()
                    await monitoring.handle_ws_command(msg_type, data)
                except Exception as exc:
                    logger.error("Monitoring command %s failed: %s", msg_type, exc)
                    await manager.send_json(
                        websocket,
                        {
                            "type": "monitor_error",
                            "code": "command_failed",
                            "message": str(exc),
                        },
                    )
                continue

            await manager.send_json(
                websocket, {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket exception: %s", exc)
        manager.disconnect(websocket)
