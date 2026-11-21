"""ECHO voice session: microphone, wake word, STT, chat, and speech playback.

Design notes:
- Audio callbacks only enqueue frames. A dedicated worker performs VAD and
  state decisions so PortAudio never stalls on inference.
- Raw audio lives in memory only and is discarded after each turn unless the
  user explicitly opts into debug recordings.
- One shared Whisper model serves both wake-word spotting and command STT.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from echo.voice.config import VoiceSettings
from echo.voice.microphone import MicrophoneStream
from echo.voice.state_machine import VoiceState, VoiceStateMachine
from echo.voice.stt import WhisperSTT
from echo.voice.tts import SentenceChunker, TTSEngine, prepare_speech_text
from echo.voice.vad import (
    AudioRingBuffer,
    UtteranceDetector,
    audio_level,
    rms,
)
from echo.voice.wake_word import WakeHit, WakeWordDetector, strip_wake_word

logger = logging.getLogger("echo.voice.session")

EventEmitter = Callable[[Dict[str, Any]], None]
ChatTurn = Callable[[Optional[str], str, Callable[[str], None]], Awaitable[Any]]
ConversationCallback = Callable[[str], None]


def _utc_now() -> str:
    return datetime.now().astimezone().isoformat()


class VoiceSession:
    """Owns all live voice resources for one daemon process."""

    def __init__(
        self,
        settings: VoiceSettings,
        *,
        emit: EventEmitter,
        chat_turn: ChatTurn,
        stt: Optional[WhisperSTT] = None,
        tts: Optional[TTSEngine] = None,
        microphone: Optional[MicrophoneStream] = None,
        wake: Optional[WakeWordDetector] = None,
        conversation_id: Optional[str] = None,
        data_dir: Optional[Path] = None,
        on_conversation_changed: Optional[ConversationCallback] = None,
        warmup_stt: bool = True,
    ) -> None:
        self.settings = settings
        self._emit = emit
        self._chat_turn = chat_turn
        self._on_conversation_changed = on_conversation_changed
        self.conversation_id = conversation_id
        self._data_dir = data_dir
        self._warmup_stt = warmup_stt

        self._stt = stt or WhisperSTT(
            settings.stt_model, settings.stt_device, settings.stt_compute_type, settings.stt_language
        )
        self._tts = tts or TTSEngine(
            voice_id=settings.tts_voice,
            rate=settings.tts_rate,
            volume=settings.tts_volume,
            on_start=self._on_tts_start_threadsafe,
        )
        self._wake = wake or WakeWordDetector(
            wake_word=settings.wake_word,
            aliases=settings.wake_aliases,
            sensitivity=settings.wake_sensitivity,
            stt=self._stt,
            sample_rate=settings.mic_sample_rate,
        )
        self._wake.set_callback(self._on_wake_word_threadsafe)
        self._mic = microphone
        self._mic_owned = microphone is None

        self._sm = VoiceStateMachine(listener=self._on_state_change)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._muted = False
        self._audio_queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue(maxsize=96)
        self._audio_thread: Optional[threading.Thread] = None
        self._ring = AudioRingBuffer(settings.mic_sample_rate, capacity_seconds=0.7)
        self._detector = UtteranceDetector(
            settings.mic_sample_rate,
            threshold=settings.vad_rms_threshold,
            silence_seconds=settings.silence_threshold_seconds,
            min_speech_seconds=settings.min_speech_seconds,
            max_seconds=settings.max_utterance_seconds,
        )

        self._finish_task: Optional[asyncio.Task] = None
        self._turn_task: Optional[asyncio.Task] = None
        self._partial_task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None
        self._request_lock: Optional[asyncio.Lock] = None
        self._partial_token = 0
        self._suppress_speech = False
        self._stream_finished = False

        self._level = 0.0
        self._last_level_emit = 0.0
        self._noise_floor = 0.002
        self._last_voice_activity = 0.0
        self._speech_started_at = 0.0
        self._barge_speech_seconds = 0.0
        self._barge_guard_until = 0.0
        self._last_transcript = ""
        self._last_reply = ""
        self._last_error: Optional[str] = None
        self._last_notice: Optional[str] = None
        self._stt_latency_ms: Optional[float] = None
        self._turn_started_at: Optional[float] = None
        self._tts_started_at: Optional[float] = None
        self._first_token_ms: Optional[float] = None
        self._turns_completed = 0
        self._recordings_saved = 0
        self._dropped_frames = 0
        self._started_at: Optional[float] = None
        self._mic_start_error: Optional[str] = None
        self._unknown_prefix = ""

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> VoiceState:
        return self._sm.state

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_muted(self) -> bool:
        return self._muted

    @property
    def is_speaking(self) -> bool:
        return self._tts.is_speaking

    def status(self) -> Dict[str, Any]:
        state = self._sm.state
        return {
            "state": state.value,
            "running": self._running,
            "muted": self._muted,
            "mic_active": bool(self._mic and self._mic.is_active),
            "capturing": state == VoiceState.LISTENING,
            "speaking": self._tts.is_speaking,
            "mode": self.settings.mode,
            "wake_word": self.settings.wake_word,
            "wake_active": bool(self._running and self.settings.mode == "wake_word" and not self._muted),
            "level": round(self._level, 3),
            "noise_floor": round(self._noise_floor, 4),
            "sample_rate": self.settings.mic_sample_rate,
            "device": getattr(self._mic, "device_name", None) if self._mic else None,
            "stt_available": self._stt.is_available,
            "stt_loaded": self._stt.is_loaded,
            "stt_model": self.settings.stt_model,
            "stt_error": self._stt.load_error,
            "partial_transcription": self.settings.partial_transcription,
            "tts_available": self._tts.is_available,
            "tts_running": self._tts.is_running,
            "tts_queue_size": self._tts.queue_size,
            "tts_error": self._tts.error,
            "tts_voice": self.settings.tts_voice,
            "barge_in_enabled": self.settings.barge_in_enabled,
            "continuous_timeout_seconds": self.settings.continuous_timeout_seconds,
            "conversation_id": self.conversation_id,
            "last_transcript": self._last_transcript,
            "last_reply": self._last_reply,
            "last_error": self._last_error,
            "last_notice": self._last_notice,
            "stt_latency_ms": self._stt_latency_ms,
            "first_token_ms": self._first_token_ms,
            "turns_completed": self._turns_completed,
            "recordings_saved": self._recordings_saved,
            "save_recordings": self.settings.save_recordings,
            "started_at": self._started_at,
            "dropped_frames": self._dropped_frames,
        }

    def set_last_error(self, message: Optional[str]) -> None:
        self._last_error = message

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> bool:
        if self._running:
            return True
        if np is None:
            self._fail_start("numpy is not installed. Run: pip install -r requirements.txt")
            return False
        self._loop = asyncio.get_running_loop()
        self._request_lock = asyncio.Lock()

        tts_ok = await asyncio.to_thread(self._tts.start)
        if not tts_ok:
            self._last_error = self._tts.error or "Speech output is unavailable."
            logger.warning("TTS unavailable: %s", self._last_error)

        self._wake.update(
            wake_word=self.settings.wake_word,
            aliases=self.settings.wake_aliases,
            sensitivity=self.settings.wake_sensitivity,
        )

        if self._mic is None:
            self._mic = MicrophoneStream(
                callback=self._on_audio_frame,
                sample_rate=self.settings.mic_sample_rate,
                device_index=self.settings.mic_device_index,
            )
            self._mic_owned = True
        else:
            self._mic._callback = self._on_audio_frame  # type: ignore[attr-defined]

        mic_ok = await asyncio.to_thread(self._mic.start)
        if not mic_ok:
            error = getattr(self._mic, "error", None) or "Microphone unavailable."
            self._mic_start_error = error
            if tts_ok:
                self._tts.stop()
            self._fail_start(error)
            return False

        if self.settings.mode == "wake_word":
            await asyncio.to_thread(self._wake.start)

        self._running = True
        self._muted = False
        self._started_at = _utc_now()
        self._audio_thread = threading.Thread(
            target=self._audio_worker, name="echo-voice-audio", daemon=True
        )
        self._audio_thread.start()
        self._sm.force(VoiceState.IDLE, "session_started")

        if self._warmup_stt and not self._stt.is_loaded:
            threading.Thread(target=self._warm_stt, name="echo-stt-warmup", daemon=True).start()

        self._emit(
            {
                "type": "voice_session",
                "active": True,
                "mode": self.settings.mode,
                "wake_word": self.settings.wake_word,
            }
        )
        self._emit_status()

        if self.settings.mode == "continuous":
            await self._begin_listening("continuous_start", seed=None)
        logger.info("Voice session started (mode=%s)", self.settings.mode)
        return True

    async def stop(self) -> None:
        if not self._running and self._mic is None:
            return
        self._running = False
        self._cancel_aux_tasks()
        task = self._turn_task
        if task and not task.done():
            task.cancel()
        self._turn_task = None
        try:
            self._tts.stop()
        except Exception:
            pass
        if self._mic is not None:
            await asyncio.to_thread(self._mic.stop)
        try:
            self._wake.stop()
        except Exception:
            pass
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass
        thread = self._audio_thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        self._audio_thread = None
        self._detector.reset()
        self._ring.clear()
        self._sm.force(VoiceState.IDLE, "session_stopped")
        self._muted = False
        self._emit({"type": "voice_session", "active": False})
        self._emit_status()
        logger.info("Voice session stopped")

    def _fail_start(self, message: str) -> None:
        self._last_error = message
        self._sm.force(VoiceState.ERROR, "start_failed")
        self._emit({"type": "voice_error", "code": "start_failed", "message": message})
        self._emit_status()

    def _warm_stt(self) -> None:
        if self._stt.load():
            self._emit({"type": "voice_engine", "engine": "stt", "ready": True})
        else:
            self._emit(
                {
                    "type": "voice_error",
                    "code": "stt_model_unavailable",
                    "message": self._stt.load_error or "Speech model could not be loaded.",
                }
            )
        self._emit_status()

    # ------------------------------------------------------------------ #
    # Controls
    # ------------------------------------------------------------------ #

    async def begin_push_to_talk(self) -> bool:
        if not self._running or self._muted:
            return False
        if self._sm.state in (VoiceState.PROCESSING, VoiceState.LISTENING):
            return self._sm.state == VoiceState.LISTENING
        if self._sm.state == VoiceState.SPEAKING:
            await self._stop_speech(cancel_turn=True, transition=False)
            self._sm.force(VoiceState.IDLE, "ptt_preempt")
        if self._sm.state == VoiceState.ERROR:
            self._sm.force(VoiceState.IDLE, "ptt_recover")
        return await self._begin_listening("push_to_talk", seed=self._ring.snapshot())

    async def end_push_to_talk(self) -> bool:
        if self._sm.state != VoiceState.LISTENING:
            return False
        self._schedule_finish("ptt_release", force=True)
        return True

    async def stop_speaking(self, *, cancel_generation: bool = True) -> None:
        await self._stop_speech(cancel_turn=cancel_generation, transition=True)
        if self.settings.mode == "continuous" and self._running and not self._muted:
            await self._begin_listening("continuous_resume", seed=None)
        elif self._sm.state in (VoiceState.SPEAKING, VoiceState.PROCESSING):
            self._sm.to_idle("stop_speaking")

    async def mute(self) -> None:
        if self._muted:
            return
        self._muted = True
        self._cancel_aux_tasks()
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        self._turn_task = None
        self._suppress_speech = True
        self._tts.stop_all()
        if self._mic is not None and self._mic.is_active:
            await asyncio.to_thread(self._mic.stop)
        self._detector.reset()
        self._ring.clear()
        self._sm.force(VoiceState.MUTED, "user_muted")
        self._emit({"type": "voice_speaking", "active": False})
        self._emit_status()

    async def unmute(self) -> bool:
        if not self._muted:
            return True
        self._muted = False
        self._suppress_speech = False
        if self._mic is not None:
            ok = await asyncio.to_thread(self._mic.start)
            if not ok:
                error = getattr(self._mic, "error", None) or "Microphone could not be reopened."
                self._last_error = error
                self._sm.force(VoiceState.ERROR, "unmute_failed")
                self._emit({"type": "voice_error", "code": "microphone_error", "message": error})
                self._emit_status()
                return False
        self._sm.force(VoiceState.IDLE, "user_unmuted")
        self._emit_status()
        return True

    async def dismiss_conversation(self) -> None:
        """End continuous conversation mode and return to idle."""
        self._cancel_aux_tasks()
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        self._turn_task = None
        self._tts.stop_all()
        self._detector.reset()
        if self._sm.state != VoiceState.MUTED:
            self._sm.force(VoiceState.IDLE, "conversation_dismissed")
        self._emit({"type": "voice_conversation_dismissed"})
        self._emit_status()

    async def speak_test(self, text: str = "Voice output is working.") -> bool:
        """Explicit user-triggered speaker check; never used implicitly."""
        if not self._running or self._muted or not self._tts.is_running:
            return False
        if self._sm.state in (VoiceState.LISTENING, VoiceState.SPEAKING):
            return False
        await self._speak_canned(prepare_speech_text(text))
        return True

    def update_live_settings(self, settings: VoiceSettings) -> None:
        """Apply changes that do not require reopening audio devices."""
        self.settings = settings
        self._tts.update_settings(
            voice_id=settings.tts_voice, rate=settings.tts_rate, volume=settings.tts_volume
        )
        self._wake.update(
            wake_word=settings.wake_word,
            aliases=settings.wake_aliases,
            sensitivity=settings.wake_sensitivity,
        )
        self._detector.silence_seconds = settings.silence_threshold_seconds
        self._detector.min_speech_seconds = settings.min_speech_seconds
        self._detector.max_seconds = settings.max_utterance_seconds
        self._emit_status()

    def set_conversation(self, conversation_id: Optional[str]) -> None:
        self.conversation_id = conversation_id

    # ------------------------------------------------------------------ #
    # Audio path
    # ------------------------------------------------------------------ #

    def _on_audio_frame(self, audio: "np.ndarray") -> None:
        if not self._running:
            return
        try:
            self._audio_queue.put_nowait(audio)
        except queue.Full:
            self._dropped_frames += 1

    def _audio_worker(self) -> None:
        while self._running:
            try:
                frame = self._audio_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if frame is None:
                break
            try:
                self._process_frame(frame)
            except Exception as exc:
                logger.warning("Voice audio processing error: %s", exc, exc_info=True)

    def _process_frame(self, frame: "np.ndarray") -> None:
        if self._muted or frame is None or len(frame) == 0:
            return
        level = rms(frame)
        now = time.monotonic()

        if now - self._last_level_emit >= 0.08:
            self._last_level_emit = now
            self._level = audio_level(frame)
            self._emit({"type": "voice_level", "level": round(self._level, 3)})

        state = self._sm.state
        threshold = max(self.settings.vad_rms_threshold, self._noise_floor * 2.5)

        if state != VoiceState.LISTENING and level < threshold:
            self._noise_floor = 0.97 * self._noise_floor + 0.03 * level

        if state == VoiceState.LISTENING:
            self._detector.threshold = threshold
            if level >= threshold:
                self._last_voice_activity = now
            if self._detector.feed(frame):
                self._schedule_finish("silence" if self._detector.has_speech else "no_speech")
            return

        self._ring.append(frame)

        if state == VoiceState.SPEAKING:
            self._track_barge_in(level, threshold, now)
            return

        if state == VoiceState.IDLE and self.settings.mode == "wake_word":
            self._wake.feed(frame)

    def _track_barge_in(self, level: float, threshold: float, now: float) -> None:
        if not self.settings.barge_in_enabled or self.settings.mode == "push_to_talk":
            return
        if now < self._barge_guard_until:
            return
        if level >= max(self.settings.barge_in_rms_threshold, threshold * 1.5):
            self._barge_speech_seconds += 0.03
            if self._barge_speech_seconds >= 0.24:
                self._barge_speech_seconds = 0.0
                self._submit(self._handle_barge_in())
        else:
            self._barge_speech_seconds = max(0.0, self._barge_speech_seconds - 0.06)

    # ------------------------------------------------------------------ #
    # Listening lifecycle
    # ------------------------------------------------------------------ #

    async def _begin_listening(
        self, reason: str, seed: Optional[List["np.ndarray"]]
    ) -> bool:
        if not self._running or self._muted:
            return False
        state = self._sm.state
        if state == VoiceState.LISTENING:
            return True
        if state not in (VoiceState.IDLE, VoiceState.PROCESSING, VoiceState.SPEAKING):
            return False
        self._cancel_timeout()
        self._cancel_partial()
        self._suppress_speech = False
        self._stream_finished = False
        self._barge_speech_seconds = 0.0
        self._detector.threshold = max(
            self.settings.vad_rms_threshold, self._noise_floor * 2.5
        )
        self._detector.reset(seed)
        self._last_voice_activity = time.monotonic()
        if not self._sm.transition(VoiceState.LISTENING, reason):
            self._sm.force(VoiceState.LISTENING, reason)
        self._emit(
            {
                "type": "voice_transcript",
                "text": "",
                "is_partial": True,
                "cleared": True,
            }
        )
        self._partial_token += 1
        if self.settings.partial_transcription:
            self._partial_task = asyncio.create_task(
                self._partial_loop(self._partial_token)
            )
        if self.settings.mode == "continuous":
            self._timeout_task = asyncio.create_task(self._continuous_timeout())
        elif self.settings.mode == "wake_word":
            self._timeout_task = asyncio.create_task(self._wake_command_timeout())
        self._emit_status()
        return True

    def _schedule_finish(self, reason: str, force: bool = False) -> None:
        if self._finish_task and not self._finish_task.done():
            return
        self._finish_task = asyncio.create_task(self._finish_listening(reason, force))

    async def _finish_listening(self, reason: str, force: bool) -> None:
        if self._sm.state != VoiceState.LISTENING:
            return
        lock = self._request_lock
        if lock is None:
            lock = asyncio.Lock()
            self._request_lock = lock
        async with lock:
            if self._sm.state != VoiceState.LISTENING:
                return
            self._cancel_partial()
            self._cancel_timeout()
            had_speech = self._detector.has_speech
            duration = self._detector.duration_seconds
            audio = self._detector.buffer()
            self._detector.reset()

            if not had_speech and not (force and len(audio) > 0):
                self._sm.force(VoiceState.IDLE, "no_speech")
                self._last_notice = "No speech detected."
                self._emit(
                    {"type": "voice_transcript", "text": "", "is_partial": False, "dropped": True}
                )
                self._emit_status()
                return

            self._save_recording(audio, duration)
            self._sm.force(VoiceState.PROCESSING, "transcribing")
            self._emit_status()

            started = time.monotonic()
            result = await asyncio.to_thread(
                self._stt.transcribe, audio, self.settings.mic_sample_rate
            )
            self._stt_latency_ms = round((time.monotonic() - started) * 1000.0, 1)
            del audio
            self._emit(
                {
                    "type": "voice_timing",
                    "stage": "stt",
                    "ms": self._stt_latency_ms,
                }
            )

            if result.error:
                self._last_error = result.error
                self._emit(
                    {
                        "type": "voice_error",
                        "code": "speech_recognition_failed",
                        "message": result.error,
                    }
                )
                await self._speak_canned("I couldn't process that. Check the voice diagnostics.")
                return

            text = result.text.strip()
            if not text or result.confidence < self.settings.min_transcript_confidence and len(text) < 3:
                self._last_notice = "I didn't catch that."
                self._emit(
                    {
                        "type": "voice_transcript",
                        "text": "",
                        "is_partial": False,
                        "dropped": True,
                        "confidence": round(result.confidence, 2),
                    }
                )
                await self._speak_canned("Sorry, I didn't catch that.")
                return

            command = text
            if self.settings.mode == "wake_word":
                command = strip_wake_word(
                    text,
                    self.settings.wake_word,
                    self.settings.wake_aliases,
                    self.settings.wake_sensitivity,
                )
            if not command:
                await self._speak_canned("I'm listening.")
                return

            self._last_transcript = command
            self._last_notice = None
            self._emit(
                {
                    "type": "voice_transcript",
                    "text": command,
                    "raw_text": text,
                    "is_partial": False,
                    "confidence": round(result.confidence, 2),
                }
            )
            await self._process_command(command)

    async def _partial_loop(self, token: int) -> None:
        last_text = ""
        try:
            while self._running and self._sm.state == VoiceState.LISTENING and token == self._partial_token:
                await asyncio.sleep(1.5)
                if self._sm.state != VoiceState.LISTENING or token != self._partial_token:
                    return
                if self._detector.duration_seconds < 1.2 or not self._detector.has_speech:
                    continue
                snapshot = self._detector.buffer()
                result = await asyncio.to_thread(
                    self._stt.transcribe,
                    snapshot,
                    self.settings.mic_sample_rate,
                    partial=True,
                )
                if (
                    result.text
                    and result.text != last_text
                    and self._sm.state == VoiceState.LISTENING
                    and token == self._partial_token
                ):
                    last_text = result.text
                    self._emit(
                        {
                            "type": "voice_transcript",
                            "text": result.text,
                            "is_partial": True,
                            "confidence": round(result.confidence, 2),
                        }
                    )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("Partial transcription stopped: %s", exc)

    async def _continuous_timeout(self) -> None:
        timeout = self.settings.continuous_timeout_seconds
        try:
            while self._running and self._sm.state == VoiceState.LISTENING:
                await asyncio.sleep(0.5)
                if (
                    self._sm.state == VoiceState.LISTENING
                    and time.monotonic() - self._last_voice_activity >= timeout
                ):
                    logger.info("Continuous conversation timed out after %.0fs", timeout)
                    self._detector.reset()
                    self._sm.force(VoiceState.IDLE, "continuous_timeout")
                    self._emit({"type": "voice_conversation_timeout", "seconds": timeout})
                    self._emit_status()
                    if self.settings.mode == "wake_word":
                        self._wake.reset()
                    return
        except asyncio.CancelledError:
            return

    async def _wake_command_timeout(self) -> None:
        """Abandon a wake activation if no command arrives, preserving privacy."""
        timeout = self.settings.wake_command_timeout_seconds
        try:
            while self._running and self._sm.state == VoiceState.LISTENING:
                await asyncio.sleep(0.5)
                if (
                    self._sm.state == VoiceState.LISTENING
                    and time.monotonic() - self._last_voice_activity >= timeout
                ):
                    self._detector.reset()
                    self._sm.force(VoiceState.IDLE, "wake_command_timeout")
                    self._last_notice = "Listening timed out."
                    self._wake.reset()
                    self._emit({"type": "voice_listen_timeout", "seconds": timeout})
                    self._emit_status()
                    return
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------ #
    # Conversation
    # ------------------------------------------------------------------ #

    async def _process_command(self, command: str) -> None:
        self._suppress_speech = False
        self._stream_finished = False
        self._first_token_ms = None
        self._turn_started_at = time.monotonic()
        self._turn_task = asyncio.create_task(self._converse(command))
        await self._turn_task

    async def _converse(self, command: str) -> None:
        chunker = SentenceChunker()
        first_chunk = True

        def on_chunk(delta: str) -> None:
            nonlocal first_chunk
            if first_chunk:
                first_chunk = False
                if self._turn_started_at:
                    self._first_token_ms = round(
                        (time.monotonic() - self._turn_started_at) * 1000.0, 1
                    )
                    self._emit(
                        {"type": "voice_timing", "stage": "first_token", "ms": self._first_token_ms}
                    )
            if self._suppress_speech:
                return
            for sentence in chunker.feed(delta):
                self._queue_speech(sentence)

        result = None
        try:
            result = await self._chat_turn(self.conversation_id, command, on_chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = f"Assistant request failed: {exc}"
            logger.error("Voice assistant turn failed: %s", exc, exc_info=True)
            self._emit(
                {"type": "voice_error", "code": "assistant_failed", "message": self._last_error}
            )
            await self._speak_canned("I couldn't reach the assistant. Please try again.")
            return

        if result is not None:
            new_conversation = getattr(result, "conversation_id", None)
            if new_conversation and new_conversation != self.conversation_id:
                self.conversation_id = new_conversation
                if self._on_conversation_changed:
                    try:
                        self._on_conversation_changed(new_conversation)
                    except Exception:
                        pass
                self._emit({"type": "voice_conversation", "conversation_id": new_conversation})

            reply = getattr(result, "content", "") or ""
            self._last_reply = reply
            if getattr(result, "error", None):
                if not self._suppress_speech and not self._tts.is_speaking:
                    self._queue_speech(
                        "I hit a problem reaching the language model. Please check the provider."
                    )
            elif reply and not self._suppress_speech:
                for sentence in chunker.flush():
                    self._queue_speech(sentence)

        self._stream_finished = True
        self._turns_completed += 1
        await self._wait_for_speech()
        self._complete_turn()

    def _queue_speech(self, text: str) -> None:
        clean = prepare_speech_text(text)
        if not clean or self._suppress_speech:
            return
        if self._sm.state == VoiceState.PROCESSING:
            self._barge_guard_until = time.monotonic() + 0.45
        if not self._tts.is_running:
            return
        if self._tts.speak(clean):
            self._emit({"type": "voice_speaking_text", "text": clean})

    async def _speak_canned(self, text: str) -> None:
        """Speak a short local acknowledgement, then return to idle/listening."""
        self._last_reply = text
        if self._sm.state in (VoiceState.PROCESSING, VoiceState.IDLE, VoiceState.LISTENING):
            self._sm.force(VoiceState.PROCESSING, "canned_speech")
        self._queue_speech(text)
        await self._wait_for_speech()
        self._complete_turn()

    async def _wait_for_speech(self) -> None:
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            if self._muted or not self._running:
                return
            if not self._tts.is_speaking and self._tts.queue_size == 0:
                return
            await asyncio.sleep(0.08)

    def _complete_turn(self) -> None:
        if not self._running or self._muted:
            return
        if self._sm.state not in (VoiceState.PROCESSING, VoiceState.SPEAKING):
            return
        self._emit({"type": "voice_speaking", "active": False})
        if self.settings.mode == "continuous":
            asyncio.create_task(self._begin_listening("continuous_resume", seed=None))
        else:
            self._sm.to_idle("turn_complete")
            self._wake.reset()
            self._emit_status()

    async def _handle_barge_in(self) -> None:
        if self._sm.state != VoiceState.SPEAKING:
            return
        if self._muted:
            return
        logger.info("Barge-in detected; stopping speech")
        self._suppress_speech = True
        self._tts.stop_all()
        task = self._turn_task
        if task and not task.done():
            task.cancel()
        self._last_notice = "Interrupted."
        self._emit({"type": "voice_interrupted"})
        self._emit({"type": "voice_speaking", "active": False})
        await self._begin_listening("barge_in", seed=self._ring.snapshot())

    async def _stop_speech(self, *, cancel_turn: bool, transition: bool) -> None:
        self._suppress_speech = True
        self._tts.stop_all()
        if cancel_turn and self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        self._turn_task = None
        self._emit({"type": "voice_speaking", "active": False})
        if transition and self._sm.state in (VoiceState.SPEAKING, VoiceState.PROCESSING):
            self._sm.force(VoiceState.IDLE, "speech_stopped")

    # ------------------------------------------------------------------ #
    # Wake word / TTS callbacks (thread-safe)
    # ------------------------------------------------------------------ #

    def _on_wake_word_threadsafe(self, hit: WakeHit) -> None:
        self._submit(self._handle_wake_hit(hit))

    async def _handle_wake_hit(self, hit: WakeHit) -> None:
        if not self._running or self._muted or self._sm.state != VoiceState.IDLE:
            return
        self._last_error = None
        self._emit(
            {
                "type": "voice_wake_word",
                "wake_word": self.settings.wake_word,
                "command": hit.command,
            }
        )
        if hit.command:
            self._last_transcript = hit.command
            self._sm.force(VoiceState.PROCESSING, "wake_word_command")
            self._emit(
                {
                    "type": "voice_transcript",
                    "text": hit.command,
                    "raw_text": hit.transcript,
                    "is_partial": False,
                }
            )
            await self._process_command(hit.command)
            return
        # The wake-word audio itself is intentionally not seeded into the
        # capture buffer; the user's command is recorded from this point.
        await self._begin_listening("wake_word", seed=None)

    def _on_tts_start_threadsafe(self, text: str) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._handle_tts_start(text), self._loop)

    async def _handle_tts_start(self, text: str) -> None:
        if self._muted:
            return
        self._tts_started_at = time.monotonic()
        if self._sm.state in (VoiceState.PROCESSING, VoiceState.IDLE, VoiceState.LISTENING):
            self._sm.transition(VoiceState.SPEAKING, "tts_start") or self._sm.force(
                VoiceState.SPEAKING, "tts_start"
            )
        self._emit({"type": "voice_speaking", "active": True, "text": text})
        self._emit_status()

    # ------------------------------------------------------------------ #
    # State listener
    # ------------------------------------------------------------------ #

    def _on_state_change(self, old: VoiceState, new: VoiceState, reason: str) -> None:
        self._emit(
            {
                "type": "voice_state",
                "state": new.value,
                "previous_state": old.value,
                "reason": reason,
            }
        )
        if new != VoiceState.SPEAKING:
            self._barge_guard_until = 0.0
        self._emit_status()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _submit(self, coro: Awaitable[None]) -> None:
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
        else:
            try:
                coro.close()  # type: ignore[union-attr]
            except Exception:
                pass

    def _cancel_partial(self) -> None:
        self._partial_token += 1
        task = self._partial_task
        if task and not task.done():
            task.cancel()
        self._partial_task = None

    def _cancel_timeout(self) -> None:
        task = self._timeout_task
        if task and not task.done():
            task.cancel()
        self._timeout_task = None

    def _cancel_aux_tasks(self) -> None:
        self._cancel_partial()
        self._cancel_timeout()

    def _emit_status(self) -> None:
        self._emit({"type": "voice_status", **self.status()})

    def _save_recording(self, audio: "np.ndarray", duration: float) -> None:
        if not self.settings.save_recordings or self._data_dir is None:
            return
        if audio is None or len(audio) == 0:
            return
        try:
            directory = self._data_dir / "voice-recordings"
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = directory / f"voice-{stamp}.wav"
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(self.settings.mic_sample_rate)
                handle.writeframes(pcm.tobytes())
            self._recordings_saved += 1
            self._enforce_retention(directory)
            self._emit(
                {
                    "type": "voice_privacy",
                    "event": "recording_saved",
                    "message": "Debug recording saved because recording storage is enabled.",
                    "file": path.name,
                }
            )
        except Exception as exc:
            logger.warning("Could not save debug recording: %s", exc)

    def _enforce_retention(self, directory: Path) -> None:
        limit = max(0, self.settings.recording_retention)
        files = sorted(directory.glob("voice-*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[limit:]:
            try:
                stale.unlink()
            except OSError:
                pass

    def clear_recordings(self) -> int:
        if self._data_dir is None:
            return 0
        directory = self._data_dir / "voice-recordings"
        if not directory.exists():
            return 0
        removed = 0
        for path in directory.glob("voice-*.wav"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        self._recordings_saved = 0
        return removed
