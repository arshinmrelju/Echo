"""Offline text-to-speech using Windows SAPI through pyttsx3.

A single engine is created and driven on its own thread. Speech is chunked
into short sentences so barge-in can stop output promptly and queued speech
can be revoked without waiting for a long paragraph to finish.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger("echo.voice.tts")

try:
    import pyttsx3  # type: ignore
    _PYTTSX3_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyttsx3 = None  # type: ignore
    _PYTTSX3_AVAILABLE = False
    logger.warning("pyttsx3 is not installed; speech output is unavailable")

StartCallback = Callable[[str], None]
EndCallback = Callable[[str], None]
IdleCallback = Callable[[], None]

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200D]+",
    flags=re.UNICODE,
)


def prepare_speech_text(text: str) -> str:
    """Turn model markdown into natural spoken prose."""
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)(\*|_)(.+?)\1(?!\w)", r"\2", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^\s*[-=]{3,}\s*$", " ", text, flags=re.MULTILINE)
    text = _EMOJI_RE.sub(" ", text)
    text = text.replace("&", " and ").replace("%", " percent ").replace("→", " to ")
    text = text.replace("•", " ").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


class SentenceChunker:
    """Streams model deltas into speakable chunks without cutting mid-word."""

    _BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
    _ABBREVIATIONS = ("e.g.", "i.e.", "mr.", "mrs.", "ms.", "dr.", "vs.", "etc.")

    def __init__(self, max_chars: int = 240) -> None:
        self.max_chars = max_chars
        self._buffer = ""

    def feed(self, delta: str) -> List[str]:
        if delta:
            self._buffer += delta
        chunks: List[str] = []
        search_from = 0
        while True:
            match = self._BOUNDARY.search(self._buffer, search_from)
            if not match:
                break
            end = match.end()
            candidate = self._buffer[:end].strip()
            lowered = candidate.lower()
            if any(lowered.endswith(abbr) for abbr in self._ABBREVIATIONS):
                # Not a real sentence boundary; keep scanning for the next one.
                search_from = end
                continue
            self._buffer = self._buffer[end:]
            search_from = 0
            if candidate:
                chunks.extend(self._split_long(candidate))
        if len(self._buffer) > self.max_chars:
            cut = self._buffer.rfind(" ", 0, self.max_chars)
            if cut <= 0:
                cut = self.max_chars
            chunks.extend(self._split_long(self._buffer[:cut].strip()))
            self._buffer = self._buffer[cut:].lstrip()
        return chunks

    def flush(self) -> List[str]:
        remainder = self._buffer.strip()
        self._buffer = ""
        return self._split_long(remainder) if remainder else []

    def _split_long(self, text: str) -> List[str]:
        if len(text) <= self.max_chars:
            return [text] if text else []
        parts: List[str] = []
        while len(text) > self.max_chars:
            window = text[: self.max_chars]
            cut = max(window.rfind(", "), window.rfind("; "), window.rfind(" "))
            if cut <= 40:
                cut = self.max_chars
            parts.append(text[:cut].strip())
            text = text[cut:].strip()
        if text:
            parts.append(text)
        return parts


class TTSEngine:
    """Queue-backed pyttsx3 engine with interrupt and voice selection."""

    def __init__(
        self,
        voice_id: Optional[str] = None,
        rate: int = 175,
        volume: float = 1.0,
        *,
        on_start: Optional[StartCallback] = None,
        on_end: Optional[EndCallback] = None,
        on_idle: Optional[IdleCallback] = None,
    ) -> None:
        self._voice_id = voice_id
        self._rate = rate
        self._volume = volume
        self._on_start = on_start
        self._on_end = on_end
        self._on_idle = on_idle
        self._queue: "queue.Queue[Tuple[str, int]]" = queue.Queue()
        self._engine: Optional[object] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._speaking = threading.Event()
        self._running = False
        self._generation = 0
        self._lock = threading.RLock()
        self.error: Optional[str] = None
        self._voices_cache: List[dict] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def is_available(self) -> bool:
        return _PYTTSX3_AVAILABLE

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def start(self, timeout: float = 8.0) -> bool:
        if not _PYTTSX3_AVAILABLE:
            self.error = "pyttsx3 is not installed. Run: pip install -r requirements.txt"
            return False
        if self._running:
            return True
        self._ready.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="echo-tts", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            self.error = "Speech engine did not start in time."
            self._running = False
            return False
        return self.error is None

    def stop(self) -> None:
        """Stop playback and terminate the engine thread."""
        self.stop_all()
        self._running = False
        self._queue.put(("", -1))  # wake the worker for shutdown
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self._engine = None
        self._voices_cache = []

    def stop_all(self) -> None:
        """Purge queued speech and interrupt the current utterance."""
        with self._lock:
            self._generation += 1
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()  # type: ignore[union-attr]
            except Exception as exc:
                logger.debug("TTS stop ignored: %s", exc)
        self._speaking.clear()

    # ------------------------------------------------------------------ #
    # Speech
    # ------------------------------------------------------------------ #

    def speak(self, text: str) -> bool:
        clean = prepare_speech_text(text)
        if not clean:
            return False
        if not self._running:
            return False
        with self._lock:
            generation = self._generation
        self._queue.put((clean, generation))
        return True

    def clear_queue(self) -> None:
        with self._lock:
            self._generation += 1
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break

    def update_settings(
        self,
        *,
        voice_id: Optional[str] = None,
        rate: Optional[int] = None,
        volume: Optional[float] = None,
    ) -> None:
        with self._lock:
            if voice_id is not None:
                self._voice_id = voice_id
            if rate is not None:
                self._rate = rate
            if volume is not None:
                self._volume = volume

    def list_voices(self) -> List[dict]:
        """Enumerate SAPI voices; safe to call before the engine has started."""
        if self._voices_cache:
            return list(self._voices_cache)
        if not _PYTTSX3_AVAILABLE:
            return []
        result: List[dict] = []
        error: List[Exception] = []

        def probe() -> None:
            try:
                engine = pyttsx3.init()
                for voice in engine.getProperty("voices"):
                    result.append(
                        {
                            "id": voice.id,
                            "name": voice.name,
                            "languages": list(getattr(voice, "languages", []) or []),
                        }
                    )
                try:
                    engine.stop()
                except Exception:
                    pass
            except Exception as exc:
                error.append(exc)

        thread = threading.Thread(target=probe, name="echo-tts-voices", daemon=True)
        thread.start()
        thread.join(timeout=10)
        if error:
            logger.warning("TTS voice enumeration failed: %s", error[0])
            return []
        self._voices_cache = result
        return list(result)

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        try:
            engine = pyttsx3.init()
            self._engine = engine
            self._apply(engine)
            self.error = None
            try:
                self._voices_cache = [
                    {"id": v.id, "name": v.name, "languages": list(getattr(v, "languages", []) or [])}
                    for v in engine.getProperty("voices")
                ]
            except Exception:
                self._voices_cache = []
            logger.info(
                "TTS ready (rate=%s, volume=%.2f, voices=%d)",
                self._rate,
                self._volume,
                len(self._voices_cache),
            )
        except Exception as exc:
            self.error = f"Speech output could not start: {exc}"
            logger.error(self.error)
            self._running = False
            self._ready.set()
            return
        self._ready.set()

        while self._running:
            try:
                text, generation = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self._speaking.is_set():
                    self._speaking.clear()
                self._notify_idle()
                continue
            try:
                with self._lock:
                    stale = generation != self._generation
                if stale or not text:
                    continue
                with self._lock:
                    engine = self._engine
                    self._apply(engine)
                if engine is None:
                    continue
                self._speaking.set()
                if self._on_start:
                    self._safe(self._on_start, text)
                try:
                    engine.say(text)  # type: ignore[union-attr]
                    engine.runAndWait()  # type: ignore[union-attr]
                except Exception as exc:
                    logger.warning("TTS utterance failed: %s", exc)
                finally:
                    with self._lock:
                        interrupted = generation != self._generation
                    if not interrupted and self._on_end:
                        self._safe(self._on_end, text)
                    self._speaking.clear()
                    if self._queue.empty():
                        self._notify_idle()
            finally:
                self._queue.task_done()

    def _apply(self, engine: Optional[object]) -> None:
        if engine is None:
            return
        try:
            engine.setProperty("rate", self._rate)  # type: ignore[union-attr]
            engine.setProperty("volume", self._volume)  # type: ignore[union-attr]
            if self._voice_id:
                engine.setProperty("voice", self._voice_id)  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("TTS settings could not be applied: %s", exc)

    def _notify_idle(self) -> None:
        if self._on_idle and not self._queue.qsize() and not self._speaking.is_set():
            self._safe(self._on_idle)

    @staticmethod
    def _safe(callback: Callable, *args) -> None:
        try:
            callback(*args)
        except Exception as exc:
            logger.warning("TTS callback failed: %s", exc)
