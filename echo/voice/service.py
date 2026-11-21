"""Voice service facade: lifecycle, settings persistence, status, and controls."""
from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import platform
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from echo.api.ws_hub import manager
from echo.core.config import get_settings
from echo.core.database import get_database
from echo.voice.config import VoiceSettings
from echo.voice.microphone import list_input_devices
from echo.voice.session import VoiceSession
from echo.voice.stt import WhisperSTT
from echo.voice.tts import TTSEngine

logger = logging.getLogger("echo.voice.service")

VOICE_SETTINGS_KEY = "voice_settings"
VOICE_CONVERSATION_KEY = "voice_last_conversation_id"

_STRUCTURAL_FIELDS = (
    "mode",
    "mic_device_index",
    "mic_sample_rate",
    "stt_model",
    "stt_device",
    "stt_compute_type",
    "stt_language",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceService:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session: Optional[VoiceSession] = None
        self._lock = threading.RLock()
        self.settings = self._load_settings()
        self._conversation_id = self._load_conversation_id()
        self._last_error: Optional[str] = None
        self._last_state = "idle"
        self._devices_cache: List[dict] = []
        self._devices_loaded_at = 0.0
        self._started_at: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load_settings(self) -> VoiceSettings:
        try:
            db = get_database()
            with db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?;", (VOICE_SETTINGS_KEY,)
                ).fetchone()
            if row and row["value"]:
                return VoiceSettings(**json.loads(row["value"]))
        except Exception as exc:
            logger.warning("Could not load voice settings; using defaults: %s", exc)
        return VoiceSettings()

    def _save_settings(self) -> None:
        try:
            db = get_database()
            payload = json.dumps(self.settings.model_dump())
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                    """,
                    (VOICE_SETTINGS_KEY, payload, _now()),
                )
        except Exception as exc:
            logger.error("Could not persist voice settings: %s", exc)

    def _load_conversation_id(self) -> Optional[str]:
        try:
            db = get_database()
            with db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?;", (VOICE_CONVERSATION_KEY,)
                ).fetchone()
            return row["value"] if row and row["value"] else None
        except Exception:
            return None

    def _persist_conversation(self, conversation_id: Optional[str]) -> None:
        if not conversation_id:
            return
        self._conversation_id = conversation_id
        try:
            db = get_database()
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                    """,
                    (VOICE_CONVERSATION_KEY, conversation_id, _now()),
                )
        except Exception as exc:
            logger.debug("Could not persist voice conversation id: %s", exc)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        session = self._session
        if session is not None:
            session._loop = loop  # type: ignore[attr-defined]

    async def start(self) -> bool:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        with self._lock:
            session = self._session
            if session and session.is_running:
                return True
            session = self._build_session()
            self._session = session
        ok = await session.start()
        if ok:
            self._last_error = session.status().get("last_error")
            self._started_at = _now()
            logger.info("Voice service started")
        else:
            self._last_error = session.status().get("last_error") or "Voice could not start."
            logger.warning("Voice service failed to start: %s", self._last_error)
        self._emit_status()
        return ok

    async def stop(self) -> None:
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            await session.stop()
        self._last_state = "idle"
        self._emit_status()

    def _build_session(self) -> VoiceSession:
        return VoiceSession(
            self.settings,
            emit=self._emit,
            chat_turn=self._chat_turn,
            conversation_id=self._conversation_id,
            data_dir=get_settings().data_dir,
            on_conversation_changed=self._persist_conversation,
            warmup_stt=True,
        )

    async def _chat_turn(self, conversation_id: Optional[str], text: str, on_chunk) -> Any:
        from echo.core.chat_service import get_chat_turn_service

        async def emit(payload: Dict[str, Any]) -> None:
            await manager.broadcast(payload)

        return await get_chat_turn_service().run_turn(
            conversation_id=conversation_id,
            content=text,
            emit=emit,
            source="voice",
            voice_mode=True,
            on_chunk=on_chunk,
            task_key=conversation_id or "voice",
        )

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #

    async def update_settings(self, updates: Dict[str, Any]) -> VoiceSettings:
        merged = self.settings.model_dump()
        for key, value in updates.items():
            if key in type(self.settings).model_fields:
                merged[key] = value
        new_settings = VoiceSettings(**merged)

        restart = False
        with self._lock:
            session = self._session
            running = bool(session and session.is_running)
            if running:
                restart = any(
                    getattr(self.settings, field) != getattr(new_settings, field)
                    for field in _STRUCTURAL_FIELDS
                )
            self.settings = new_settings
        self._save_settings()

        if session and running:
            if restart:
                await session.stop()
                with self._lock:
                    self._session = None
                await self.start()
            else:
                session.update_live_settings(new_settings)
        self._emit_status()
        return self.settings

    def settings_dict(self) -> Dict[str, Any]:
        return self.settings.public_dict()

    # ------------------------------------------------------------------ #
    # Controls
    # ------------------------------------------------------------------ #

    async def mute(self) -> bool:
        session = self._session
        if session is None or not session.is_running:
            return False
        await session.mute()
        return True

    async def unmute(self) -> bool:
        session = self._session
        if session is None:
            return False
        return await session.unmute()

    async def ptt_start(self, conversation_id: Optional[str] = None) -> bool:
        if conversation_id:
            self.set_conversation(conversation_id)
        if self._session is None or not self._session.is_running:
            if not await self.start():
                return False
        assert self._session is not None
        return await self._session.begin_push_to_talk()

    async def ptt_stop(self) -> bool:
        if self._session is None:
            return False
        return await self._session.end_push_to_talk()

    async def stop_speaking(self) -> None:
        if self._session is not None:
            await self._session.stop_speaking()

    async def dismiss(self) -> None:
        if self._session is not None:
            await self._session.dismiss_conversation()

    async def speak_test(self, text: str = "Voice output is working.") -> bool:
        if self._session is None or not self._session.is_running:
            if not await self.start():
                return False
        assert self._session is not None
        return await self._session.speak_test(text)

    def set_conversation(self, conversation_id: Optional[str]) -> None:
        if not conversation_id:
            return
        self._persist_conversation(conversation_id)
        if self._session is not None:
            self._session.set_conversation(conversation_id)
        self._emit_status()

    async def handle_ws_command(self, msg_type: str, data: Dict[str, Any]) -> None:
        if msg_type == "voice_start":
            await self.start()
        elif msg_type == "voice_stop":
            await self.stop()
        elif msg_type == "voice_ptt_start":
            await self.ptt_start(data.get("conversation_id"))
        elif msg_type == "voice_ptt_stop":
            await self.ptt_stop()
        elif msg_type == "voice_stop_speaking":
            await self.stop_speaking()
        elif msg_type == "voice_mute":
            await self.mute()
        elif msg_type == "voice_unmute":
            await self.unmute()
        elif msg_type == "voice_dismiss":
            await self.dismiss()
        elif msg_type == "voice_set_conversation":
            self.set_conversation(data.get("conversation_id"))
        elif msg_type == "voice_status_request":
            self._emit_status()
        else:
            logger.debug("Unhandled voice websocket command: %s", msg_type)

    # ------------------------------------------------------------------ #
    # Status & diagnostics
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        session = self._session
        if session is not None:
            status = session.status()
            self._last_state = status["state"]
            status["enabled"] = session.is_running
            status["settings"] = self.settings.public_dict()
            status["started_at"] = self._started_at
            if not status.get("last_error"):
                status["last_error"] = self._last_error
            return status

        stt = WhisperSTT()
        tts = TTSEngine()
        return {
            "state": "idle",
            "enabled": False,
            "running": False,
            "muted": False,
            "mic_active": False,
            "capturing": False,
            "speaking": False,
            "mode": self.settings.mode,
            "wake_word": self.settings.wake_word,
            "wake_active": False,
            "level": 0.0,
            "noise_floor": 0.0,
            "sample_rate": self.settings.mic_sample_rate,
            "device": None,
            "stt_available": stt.is_available,
            "stt_loaded": False,
            "stt_model": self.settings.stt_model,
            "stt_error": None,
            "partial_transcription": self.settings.partial_transcription,
            "tts_available": tts.is_available,
            "tts_running": False,
            "tts_queue_size": 0,
            "tts_error": None,
            "tts_voice": self.settings.tts_voice,
            "barge_in_enabled": self.settings.barge_in_enabled,
            "continuous_timeout_seconds": self.settings.continuous_timeout_seconds,
            "conversation_id": self._conversation_id,
            "last_transcript": "",
            "last_reply": "",
            "last_error": self._last_error,
            "last_notice": None,
            "stt_latency_ms": None,
            "first_token_ms": None,
            "turns_completed": 0,
            "recordings_saved": self._count_recordings(),
            "save_recordings": self.settings.save_recordings,
            "started_at": self._started_at,
            "dropped_frames": 0,
            "settings": self.settings.public_dict(),
            "installed": {
                "numpy": _package_version("numpy") is not None,
                "sounddevice": _package_version("sounddevice") is not None,
                "faster_whisper": stt.is_available,
                "pyttsx3": tts.is_available,
            },
        }

    def status_event(self) -> Dict[str, Any]:
        return {"type": "voice_status", **self.status()}

    def refresh_devices(self, force: bool = False) -> List[dict]:
        import time

        if force or not self._devices_loaded_at or time.monotonic() - self._devices_loaded_at > 15:
            self._devices_cache = list_input_devices()
            self._devices_loaded_at = time.monotonic()
        return list(self._devices_cache)

    def voices(self) -> List[dict]:
        engine = getattr(self._session, "_tts", None)
        if engine is not None:
            return engine.list_voices()
        return TTSEngine().list_voices()

    def diagnostics(self) -> Dict[str, Any]:
        status = self.status()
        recordings = self.list_recordings()
        return {
            "platform": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "packages": {
                "numpy": _package_version("numpy"),
                "sounddevice": _package_version("sounddevice"),
                "faster-whisper": _package_version("faster-whisper"),
                "pyttsx3": _package_version("pyttsx3"),
            },
            "loop": self._loop is not None,
            "state": status["state"],
            "stt": {
                "available": status["stt_available"],
                "model": status["stt_model"],
                "loaded": status["stt_loaded"],
                "error": status.get("stt_error"),
                "latency_ms": status.get("stt_latency_ms"),
            },
            "tts": {
                "available": status["tts_available"],
                "running": status.get("tts_running", False),
                "error": status.get("tts_error"),
                "voice_count": len(self.voices()),
            },
            "wake_word": {
                "engine": "whisper-segment",
                "word": self.settings.wake_word,
                "aliases": self.settings.wake_aliases,
                "sensitivity": self.settings.wake_sensitivity,
            },
            "privacy": {
                "save_recordings": self.settings.save_recordings,
                "recordings": len(recordings),
                "retention": self.settings.recording_retention,
                "raw_audio_default": "memory only",
            },
            "audio_devices": self.refresh_devices(force=True),
            "last_error": status.get("last_error"),
        }

    def list_recordings(self) -> List[dict]:
        directory = get_settings().data_dir / "voice-recordings"
        if not directory.exists():
            return []
        items = []
        for path in sorted(directory.glob("voice-*.wav"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            items.append(
                {
                    "name": path.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                }
            )
        return items

    def delete_recordings(self) -> int:
        session = self._session
        if session is not None:
            return session.clear_recordings()
        directory = get_settings().data_dir / "voice-recordings"
        if not directory.exists():
            return 0
        removed = 0
        for path in directory.glob("voice-*.wav"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def _count_recordings(self) -> int:
        return len(self.list_recordings())

    # ------------------------------------------------------------------ #
    # Event fan-out
    # ------------------------------------------------------------------ #

    def _emit(self, payload: Dict[str, Any]) -> None:
        event_type = payload.get("type")
        if event_type == "voice_error":
            self._last_error = payload.get("message")
        elif event_type == "voice_state":
            self._last_state = payload.get("state", self._last_state)
        loop = self._loop
        if loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)
            except RuntimeError:
                pass

    def _emit_status(self) -> None:
        self._emit(self.status_event())


def _package_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


_service: Optional[VoiceService] = None


def get_voice_service() -> VoiceService:
    global _service
    if _service is None:
        _service = VoiceService()
    return _service


def set_voice_service(service: Optional[VoiceService]) -> None:
    """Test seam."""
    global _service
    _service = service
