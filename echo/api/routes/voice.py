"""Voice control and diagnostics API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from echo.api.schemas import (
    VoiceConversationRequest,
    VoicePushToTalkRequest,
    VoiceSettingsUpdateRequest,
    VoiceSpeakTestRequest,
)
from echo.voice.config import VoiceSettings
from echo.voice.service import get_voice_service

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])


def _action(success: bool, error: str | None = None) -> Dict[str, Any]:
    service = get_voice_service()
    status = service.status()
    return {
        "success": success,
        "error": error,
        "status": status,
    }


@router.get("/status")
async def voice_status():
    return get_voice_service().status()


@router.get("/settings")
async def voice_settings():
    service = get_voice_service()
    return {
        "settings": service.settings_dict(),
        "defaults": VoiceSettings().model_dump(),
        "status": service.status(),
    }


@router.put("/settings")
async def update_voice_settings(payload: VoiceSettingsUpdateRequest):
    service = get_voice_service()
    updates = payload.model_dump(exclude_unset=True)
    settings = await service.update_settings(updates)
    return {"success": True, "settings": settings.model_dump(), "status": service.status()}


@router.post("/start")
async def start_voice():
    service = get_voice_service()
    ok = await service.start()
    status = service.status()
    return _action(ok, None if ok else status.get("last_error") or "Voice could not start.")


@router.post("/stop")
async def stop_voice():
    service = get_voice_service()
    await service.stop()
    return _action(True)


@router.post("/mute")
async def mute_voice():
    service = get_voice_service()
    ok = await service.mute()
    return _action(ok, None if ok else "Voice is not running.")


@router.post("/unmute")
async def unmute_voice():
    service = get_voice_service()
    ok = await service.unmute()
    return _action(ok, None if ok else "Voice is not running or could not reopen the microphone.")


@router.post("/ptt/start")
async def push_to_talk_start(payload: VoicePushToTalkRequest | None = None):
    service = get_voice_service()
    ok = await service.ptt_start(payload.conversation_id if payload else None)
    return _action(ok, None if ok else service.status().get("last_error") or "Could not start recording.")


@router.post("/ptt/stop")
async def push_to_talk_stop():
    service = get_voice_service()
    ok = await service.ptt_stop()
    return _action(ok, None if ok else "Voice was not recording.")


@router.post("/stop-speaking")
async def stop_speaking():
    service = get_voice_service()
    await service.stop_speaking()
    return _action(True)


@router.post("/dismiss")
async def dismiss_conversation():
    service = get_voice_service()
    await service.dismiss()
    return _action(True)


@router.post("/conversation")
async def set_conversation(payload: VoiceConversationRequest):
    service = get_voice_service()
    service.set_conversation(payload.conversation_id)
    return _action(True)


@router.post("/test-speech")
async def test_speech(payload: VoiceSpeakTestRequest | None = None):
    service = get_voice_service()
    text = (payload.text if payload and payload.text else "Voice output is working.").strip()
    ok = await service.speak_test(text)
    return _action(ok, None if ok else "Speech output is unavailable.")


@router.get("/devices")
async def voice_devices(force: bool = False):
    return {"devices": get_voice_service().refresh_devices(force=force)}


@router.get("/voices")
async def voice_voices():
    return {"voices": get_voice_service().voices()}


@router.get("/diagnostics")
async def voice_diagnostics():
    return get_voice_service().diagnostics()


@router.get("/recordings")
async def list_recordings():
    service = get_voice_service()
    return {"recordings": service.list_recordings(), "enabled": service.settings.save_recordings}


@router.delete("/recordings")
async def delete_recordings():
    removed = get_voice_service().delete_recordings()
    return {"success": True, "removed": removed, "recordings": []}
