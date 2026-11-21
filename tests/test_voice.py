"""Voice subsystem tests: wake matching, VAD, speech formatting, state, session."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from echo.api.app import app
from echo.voice.config import VoiceSettings
from echo.voice.session import VoiceSession
from echo.voice.state_machine import VoiceState, VoiceStateMachine
from echo.voice.stt import TranscriptionResult, clean_transcript
from echo.voice.tts import SentenceChunker, prepare_speech_text
from echo.voice.vad import AudioRingBuffer, UtteranceDetector, audio_level, rms
from echo.voice.wake_word import WakeWordDetector, match_wake_hit, strip_wake_word

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeMic:
    def __init__(self, start_ok: bool = True) -> None:
        self.device_name = "Fake Microphone"
        self.is_active = False
        self._callback = None
        self.error = None
        self.start_ok = start_ok
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        self.is_active = self.start_ok
        return self.start_ok

    def stop(self) -> None:
        self.is_active = False
        self.stop_calls += 1

    def mute(self) -> None:
        self.is_active = False

    def unmute(self) -> None:
        self.is_active = True


class FakeWake:
    def __init__(self) -> None:
        self.started = False
        self.reset_calls = 0
        self.callback = None

    def set_callback(self, callback) -> None:
        self.callback = callback

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def reset(self) -> None:
        self.reset_calls += 1

    def update(self, **kwargs) -> None:
        pass

    def feed(self, frame) -> None:
        pass


class FakeSTT:
    is_available = True
    is_loaded = True
    load_error = None

    def __init__(self, text: str = "Open VS Code", confidence: float = 0.95) -> None:
        self.text = text
        self.confidence = confidence
        self.calls = 0

    def load(self) -> bool:
        return True

    def transcribe(self, audio, sample_rate: int = 16000, partial: bool = False) -> TranscriptionResult:
        self.calls += 1
        return TranscriptionResult(
            text=self.text,
            confidence=self.confidence,
            duration_seconds=len(audio) / float(sample_rate) if len(audio) else 0.0,
            is_partial=partial,
        )


class FakeTTS:
    is_available = True
    error = None

    def __init__(self) -> None:
        self.is_running = False
        self.is_speaking = False
        self.queue_size = 0
        self.spoken: list[str] = []
        self.stop_all_calls = 0

    def start(self) -> bool:
        self.is_running = True
        return True

    def stop(self) -> None:
        self.is_running = False

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        return True

    def stop_all(self) -> None:
        self.stop_all_calls += 1
        self.is_speaking = False
        self.queue_size = 0

    def update_settings(self, **kwargs) -> None:
        pass

    def list_voices(self):
        return []


def frame(seconds: float = 0.1, value: float = 0.0, sample_rate: int = 16000) -> np.ndarray:
    return np.full(int(sample_rate * seconds), value, dtype=np.float32)


async def wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition was not met before timeout")


def build_session(**settings_overrides):
    settings = VoiceSettings(
        mode="push_to_talk",
        auto_start=False,
        save_recordings=False,
        partial_transcription=False,
        silence_threshold_seconds=0.4,
        min_speech_seconds=0.1,
        max_utterance_seconds=10,
    )
    for key, value in settings_overrides.items():
        setattr(settings, key, value)

    events: list[dict] = []
    calls: list[tuple] = []
    mic = FakeMic()
    tts = FakeTTS()
    stt = FakeSTT("open vs code")
    wake = FakeWake()

    def emit(payload):
        events.append(payload)

    async def chat_turn(conversation_id, text, on_chunk):
        calls.append((conversation_id, text))
        on_chunk("Opening ")
        on_chunk("VS Code.")
        return SimpleNamespace(
            conversation_id="conv-voice", content="Opening VS Code.", error=None
        )

    session = VoiceSession(
        settings,
        emit=emit,
        chat_turn=chat_turn,
        stt=stt,
        tts=tts,
        microphone=mic,
        wake=wake,
        data_dir=None,
        warmup_stt=False,
    )
    return session, events, calls, mic, tts, stt, wake


# ---------------------------------------------------------------------------
# Wake word matching
# ---------------------------------------------------------------------------


def test_wake_hit_captures_trailing_command():
    hit = match_wake_hit("Echo, open Chrome", "echo", ["hey echo"], 0.5)
    assert hit is not None
    assert hit.alias == "echo"
    assert hit.command == "open Chrome"


def test_wake_alias_with_multiword_phrase():
    hit = match_wake_hit("Hey Echo, what time is it?", "echo", ["hey echo"], 0.5)
    assert hit is not None
    assert hit.command == "what time is it?"


def test_wake_word_requires_start_at_default_sensitivity():
    assert match_wake_hit("So echo what now", "echo", [], 0.5) is None
    hit = match_wake_hit("So echo what now", "echo", [], 0.85)
    assert hit is not None
    assert hit.command == "So what now"


def test_wake_word_tolerates_small_transcription_drift():
    hit = match_wake_hit("Echo open the terminal", "echo", [], 0.5)
    assert hit is not None
    assert match_wake_hit("Each open the terminal", "echo", [], 0.5) is None


def test_strip_wake_word_leaves_plain_command():
    assert strip_wake_word("open the terminal", "echo") == "open the terminal"
    assert strip_wake_word("Echo open the terminal", "echo") == "open the terminal"


def test_clean_transcript_removes_artifacts():
    assert clean_transcript("  [BLANK_AUDIO]  Hello\u200b there. ") == "Hello there."


# ---------------------------------------------------------------------------
# VAD and audio helpers
# ---------------------------------------------------------------------------


def test_utterance_detector_endpoints_after_silence():
    detector = UtteranceDetector(16000, threshold=0.01, silence_seconds=0.2, min_speech_seconds=0.1)
    assert detector.feed(frame(value=0.0)) is False
    assert detector.feed(frame(value=0.2)) is False
    assert detector.has_speech is True
    assert detector.feed(frame(value=0.0)) is False
    assert detector.feed(frame(value=0.0)) is True
    audio = detector.buffer()
    assert len(audio) == 4 * 1600


def test_audio_level_and_rms_are_bounded():
    assert rms(np.zeros(1600, dtype=np.float32)) == 0.0
    assert 0.0 <= audio_level(np.zeros(1600, dtype=np.float32)) <= 1.0
    assert 0.0 < audio_level(frame(value=0.2)) <= 1.0


def test_ring_buffer_keeps_recent_frames():
    ring = AudioRingBuffer(16000, capacity_seconds=0.1)
    for _ in range(10):
        ring.append(frame())
    assert 0 < len(ring) <= max(1, int(16000 * 0.1 / 480))
    assert len(ring.snapshot()) == len(ring)


# ---------------------------------------------------------------------------
# Speech formatting and chunking
# ---------------------------------------------------------------------------


def test_prepare_speech_text_strips_markdown_and_emoji():
    text = "## Status\n**Running** normally ✅. See https://example.com or `echo --help`."
    spoken = prepare_speech_text(text)
    assert "**" not in spoken
    assert "https://" not in spoken
    assert "✅" not in spoken
    assert spoken.startswith("Status")


def test_sentence_chunker_splits_without_cutting_abbreviations():
    chunker = SentenceChunker()
    chunks = chunker.feed("Use e.g. this option. Then continue.")
    assert chunks == ["Use e.g. this option."]
    assert chunker.flush() == ["Then continue."]


def test_sentence_chunker_splits_long_text():
    chunker = SentenceChunker(max_chars=40)
    chunks = chunker.feed("word " * 40)
    chunks += chunker.feed("word " * 40)
    chunks += chunker.flush()
    assert len(chunks) > 1
    assert all(len(c) <= 40 for c in chunks)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_state_machine_enforces_allowed_transitions():
    changes = []
    sm = VoiceStateMachine(listener=lambda old, new, reason: changes.append((old, new, reason)))
    assert sm.state == VoiceState.IDLE
    assert sm.transition(VoiceState.LISTENING, "wake") is True
    assert sm.transition(VoiceState.SPEAKING, "illegal") is False
    assert sm.transition(VoiceState.PROCESSING, "stt") is True
    assert sm.transition(VoiceState.SPEAKING, "tts") is True
    assert sm.to_idle("done") is True
    assert [c[1] for c in changes] == [
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]


# ---------------------------------------------------------------------------
# Session pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_to_talk_turn_transcribes_and_speaks(tmp_path: Path):
    session, events, calls, mic, tts, stt, _ = build_session()
    session._data_dir = tmp_path

    assert await session.start() is True
    assert mic.is_active is True

    assert await session.begin_push_to_talk() is True
    for _ in range(4):
        session._process_frame(frame(value=0.2))
    for _ in range(6):
        session._process_frame(frame(value=0.0))
    assert await session.end_push_to_talk() is True

    await wait_until(lambda: session.state == VoiceState.IDLE)

    assert calls == [(None, "open vs code")]
    assert tts.spoken and "Opening" in tts.spoken[0]

    final = [
        e for e in events
        if e.get("type") == "voice_transcript" and e.get("text") == "open vs code" and not e.get("is_partial")
    ]
    assert final
    assert any(e.get("type") == "voice_speaking" for e in events)

    await session.stop()
    assert mic.is_active is False


@pytest.mark.asyncio
async def test_short_capture_is_dropped_without_stt(tmp_path: Path):
    session, events, calls, mic, tts, stt, _ = build_session()
    session._data_dir = tmp_path

    assert await session.start()
    assert await session.begin_push_to_talk()
    # Released immediately: nothing was captured, so no recogniser call.
    assert await session.end_push_to_talk()

    await wait_until(lambda: session.state == VoiceState.IDLE)
    assert calls == []
    assert stt.calls == 0
    assert any(e.get("type") == "voice_transcript" and e.get("dropped") for e in events)
    await session.stop()


@pytest.mark.asyncio
async def test_mute_stops_capture_and_unmute_reopens(tmp_path: Path):
    session, events, calls, mic, tts, _, _ = build_session()
    session._data_dir = tmp_path
    assert await session.start()
    assert await session.begin_push_to_talk()

    await session.mute()
    assert session.state == VoiceState.MUTED
    assert mic.is_active is False
    assert tts.stop_all_calls >= 1

    # Frames while muted must never reach the detector or STT.
    for _ in range(6):
        session._process_frame(frame(value=0.3))
    assert calls == []
    assert any(e.get("type") == "voice_status" and e.get("muted") for e in events)

    assert await session.unmute() is True
    assert session.state == VoiceState.IDLE
    assert mic.is_active is True
    assert mic.start_calls >= 2
    await session.stop()


@pytest.mark.asyncio
async def test_stop_speaking_cancels_active_turn(tmp_path: Path):
    session, events, _, _, tts, _, _ = build_session()
    session._data_dir = tmp_path
    assert await session.start()

    async def slow_turn(conversation_id, text, on_chunk):
        on_chunk("First sentence. ")
        await asyncio.sleep(5)
        return SimpleNamespace(conversation_id="conv-1", content="First sentence.", error=None)

    session._chat_turn = slow_turn
    task = asyncio.create_task(session._process_command("say something"))
    session._turn_task = task
    await wait_until(lambda: bool(tts.spoken))
    session._sm.force(VoiceState.SPEAKING, "test")

    await session.stop_speaking()
    await asyncio.gather(task, return_exceptions=True)
    assert tts.stop_all_calls >= 1
    assert task.done()
    assert session.state in (VoiceState.IDLE, VoiceState.MUTED)
    await session.stop()


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


def test_recordings_are_memory_only_by_default(tmp_path: Path):
    session, *_ = build_session()
    session._data_dir = tmp_path
    session._save_recording(frame(value=0.2), 0.1)
    assert not (tmp_path / "voice-recordings").exists()


def test_opt_in_recording_respects_retention(tmp_path: Path):
    session, *_ = build_session()
    session._data_dir = tmp_path
    session.settings.save_recordings = True
    session.settings.recording_retention = 2

    for _ in range(4):
        session._save_recording(frame(value=0.2), 0.1)

    files = list((tmp_path / "voice-recordings").glob("voice-*.wav"))
    assert len(files) == 2
    assert session.clear_recordings() == 2
    assert not list((tmp_path / "voice-recordings").glob("voice-*.wav"))


# ---------------------------------------------------------------------------
# Wake detector worker
# ---------------------------------------------------------------------------


def test_wake_detector_calls_back_with_command():
    stt = FakeSTT("Echo, open Finder")
    detector = WakeWordDetector(
        "echo",
        ["hey echo"],
        0.5,
        stt=stt,
        sample_rate=16000,
        energy_threshold=0.01,
        silence_seconds=0.1,
        min_speech_seconds=0.05,
        cooldown_seconds=0.0,
    )
    hits = []
    detector.set_callback(hits.append)
    detector.start()
    try:
        for _ in range(3):
            detector.feed(frame(value=0.2))
        for _ in range(3):
            detector.feed(frame(value=0.0))

        deadline = 2.0
        while deadline > 0 and not hits:
            import time

            time.sleep(0.05)
            deadline -= 0.05
        assert hits, "wake detector never produced a hit"
        assert hits[0].command == "open Finder"
        assert detector.transcriptions_checked >= 1
    finally:
        detector.stop()


# ---------------------------------------------------------------------------
# Settings normalization
# ---------------------------------------------------------------------------


def test_voice_settings_normalize_wake_word_and_aliases():
    settings = VoiceSettings(wake_word="  Echo  ", wake_aliases=["Hey ECHO", "  ok echo "])
    assert settings.wake_word == "echo"
    assert settings.wake_aliases == ["hey echo", "ok echo"]


def test_public_settings_hide_nothing_sensitive():
    payload = VoiceSettings().public_dict()
    assert "wake_word" in payload
    assert payload["save_recordings"] is False


# ---------------------------------------------------------------------------
# Voice API
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_voice_status_endpoint(async_client):
    res = await async_client.get("/api/v1/voice/status")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] in {"idle", "error"}
    assert "running" in data
    assert "settings" in data
    assert data["settings"]["save_recordings"] is False


@pytest.mark.asyncio
async def test_voice_settings_partial_update(async_client):
    original = (await async_client.get("/api/v1/voice/settings")).json()["settings"]
    target = "push_to_talk" if original["mode"] != "push_to_talk" else "wake_word"
    try:
        res = await async_client.put(
            "/api/v1/voice/settings", json={"mode": target, "partial_transcription": False}
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["success"] is True
        assert payload["settings"]["mode"] == target
        assert payload["settings"]["partial_transcription"] is False
        assert payload["settings"]["wake_word"] == original["wake_word"]
    finally:
        await async_client.put(
            "/api/v1/voice/settings",
            json={
                "mode": original["mode"],
                "partial_transcription": original["partial_transcription"],
            },
        )


@pytest.mark.asyncio
async def test_voice_settings_rejects_out_of_range(async_client):
    res = await async_client.put("/api/v1/voice/settings", json={"tts_rate": 9000})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_voice_devices_and_diagnostics(async_client):
    devices = await async_client.get("/api/v1/voice/devices")
    assert devices.status_code == 200
    assert isinstance(devices.json()["devices"], list)

    diagnostics = await async_client.get("/api/v1/voice/diagnostics")
    assert diagnostics.status_code == 200
    data = diagnostics.json()
    assert data["wake_word"]["word"]
    assert data["privacy"]["raw_audio_default"] == "memory only"


@pytest.mark.asyncio
async def test_voice_control_endpoints_without_running_session(async_client):
    res = await async_client.post("/api/v1/voice/mute")
    assert res.status_code == 200
    assert res.json()["success"] is False
    assert res.json()["error"]

    res = await async_client.post("/api/v1/voice/ptt/stop")
    assert res.status_code == 200
    assert res.json()["success"] is False
