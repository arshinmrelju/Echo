"""Configurable, offline wake-word detection.

The default ``echo`` wake word is detected by endpointing short speech
segments and running one lightweight Whisper pass per segment. Silence and
noise never hit the recogniser, and a single worker with a bounded queue
keeps idle CPU cost low. A shared STT model instance is reused for commands.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, List, Optional, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from echo.voice.stt import WhisperSTT
from echo.voice.vad import frame_duration_seconds, rms

logger = logging.getLogger("echo.voice.wake_word")

WakeCallback = Callable[["WakeHit"], None]


@dataclass
class WakeHit:
    transcript: str
    command: str
    alias: str


def _normalize_tokens(text: str) -> List[str]:
    cleaned = re.sub(r"[^\w\s']", " ", (text or "").lower())
    return [token for token in cleaned.split() if token]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


def _alias_variants(wake_word: str, aliases: Sequence[str]) -> List[List[str]]:
    variants: List[List[str]] = []
    for phrase in [wake_word, *aliases]:
        tokens = _normalize_tokens(phrase)
        if tokens and tokens not in variants:
            variants.append(tokens)
    variants.sort(key=len, reverse=True)
    return variants


def match_wake_hit(
    transcript: str,
    wake_word: str = "echo",
    aliases: Sequence[str] = (),
    sensitivity: float = 0.5,
) -> Optional[WakeHit]:
    """Return a wake hit and any trailing command, or None.

    Higher sensitivity allows one-character transcription drift and a match
    anywhere in the utterance. At the default 0.5 the wake word must begin
    the utterance, which keeps false positives down in normal conversation.
    """
    if not transcript:
        return None
    raw_tokens = transcript.split()
    tokens = [_normalize_tokens(token) for token in raw_tokens]
    normalized = [" ".join(token) if token else "" for token in tokens]
    variants = _alias_variants(wake_word, aliases)
    tolerance = 1 if sensitivity >= 0.35 else 0
    allow_anywhere = sensitivity >= 0.75

    for variant in variants:
        width = len(variant)
        if width == 0 or len(normalized) < width:
            continue
        positions = range(len(normalized) - width + 1) if allow_anywhere else [0]
        for start in positions:
            window = normalized[start : start + width]
            matched = True
            for observed, expected in zip(window, variant):
                if observed == expected:
                    continue
                if len(expected) >= 4 and tolerance and _levenshtein(observed, expected) <= tolerance:
                    continue
                matched = False
                break
            if not matched:
                continue
            remainder = raw_tokens[:start] + raw_tokens[start + width :]
            command = " ".join(remainder)
            command = re.sub(r"^[\s,.:;!?\-–—]+", "", command).strip()
            return WakeHit(transcript=transcript.strip(), command=command, alias=" ".join(variant))
    return None


def strip_wake_word(
    transcript: str,
    wake_word: str = "echo",
    aliases: Sequence[str] = (),
    sensitivity: float = 0.5,
) -> str:
    hit = match_wake_hit(transcript, wake_word, aliases, sensitivity)
    if hit:
        return hit.command
    return transcript.strip()


class WakeWordDetector:
    """Speech-segment wake detector; one recogniser worker, zero idle STT."""

    def __init__(
        self,
        wake_word: str = "echo",
        aliases: Optional[Sequence[str]] = None,
        sensitivity: float = 0.5,
        *,
        stt: Optional[WhisperSTT] = None,
        sample_rate: int = 16000,
        energy_threshold: float = 0.015,
        silence_seconds: float = 0.45,
        min_speech_seconds: float = 0.2,
        max_segment_seconds: float = 2.2,
        cooldown_seconds: float = 1.6,
    ) -> None:
        self.wake_word = wake_word
        self.aliases = list(aliases or [])
        self.sensitivity = sensitivity
        self.energy_threshold = energy_threshold
        self.silence_seconds = silence_seconds
        self.min_speech_seconds = min_speech_seconds
        self.max_segment_seconds = max_segment_seconds
        self.cooldown_seconds = cooldown_seconds
        self.sample_rate = sample_rate
        self._stt = stt or WhisperSTT()
        self._callback: Optional[WakeCallback] = None
        self._active = False
        self._enabled = True
        self._segments: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=3)
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()
        self._preroll: Deque["np.ndarray"] = deque(maxlen=14)
        self._segment: List["np.ndarray"] = []
        self._speech = False
        self._speech_seconds = 0.0
        self._silence_run = 0.0
        self._segment_seconds = 0.0
        self._last_detection = 0.0
        self._last_error: Optional[str] = None
        self._noise_floor = 0.002
        self.transcriptions_checked = 0
        self.detections = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def set_callback(self, callback: WakeCallback) -> None:
        self._callback = callback

    def start(self) -> None:
        if self._running:
            self._active = True
            return
        self._running = True
        self._active = True
        self._worker = threading.Thread(
            target=self._detect_loop, name="echo-wake-word", daemon=True
        )
        self._worker.start()
        logger.info(
            "Wake word detector armed (word=%r, aliases=%s)",
            self.wake_word,
            self.aliases,
        )

    def stop(self) -> None:
        self._active = False
        self._running = False
        try:
            while True:
                self._segments.get_nowait()
        except queue.Empty:
            pass
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=1.5)
        self._worker = None
        logger.info("Wake word detector stopped")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self.reset()

    def reset(self) -> None:
        with self._lock:
            self._preroll.clear()
            self._segment = []
            self._speech = False
            self._speech_seconds = 0.0
            self._silence_run = 0.0
            self._segment_seconds = 0.0

    def update(
        self,
        *,
        wake_word: Optional[str] = None,
        aliases: Optional[Sequence[str]] = None,
        sensitivity: Optional[float] = None,
    ) -> None:
        if wake_word is not None:
            self.wake_word = wake_word
        if aliases is not None:
            self.aliases = list(aliases)
        if sensitivity is not None:
            self.sensitivity = sensitivity

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def noise_floor(self) -> float:
        return self._noise_floor

    @property
    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------ #
    # Audio segmentation
    # ------------------------------------------------------------------ #

    def feed(self, frame: "np.ndarray") -> None:
        if not self._active or not self._enabled or np is None:
            return
        if frame is None or len(frame) == 0:
            return
        level = rms(frame)
        threshold = max(self.energy_threshold, self._noise_floor * 2.5)
        if self.sensitivity >= 0.8:
            threshold *= 0.85

        with self._lock:
            if not self._speech:
                if level < threshold:
                    self._noise_floor = 0.98 * self._noise_floor + 0.02 * level
                    self._preroll.append(frame.copy())
                    return
                self._speech = True
                self._segment = list(self._preroll)
                self._preroll.clear()
                self._segment.append(frame.copy())
                self._segment_seconds = sum(
                    frame_duration_seconds(f, self.sample_rate) for f in self._segment
                )
                self._speech_seconds = frame_duration_seconds(frame, self.sample_rate)
                self._silence_run = 0.0
                return

            self._segment.append(frame.copy())
            duration = frame_duration_seconds(frame, self.sample_rate)
            self._segment_seconds += duration
            if level >= threshold:
                self._speech_seconds += duration
                self._silence_run = 0.0
            else:
                self._silence_run += duration

            finished = (
                self._silence_run >= self.silence_seconds
                or self._segment_seconds >= self.max_segment_seconds
            )
            if not finished:
                return
            should_check = self._speech_seconds >= self.min_speech_seconds
            segment = np.concatenate(self._segment) if self._segment else None
            self._segment = []
            self._speech = False
            self._speech_seconds = 0.0
            self._silence_run = 0.0
            self._segment_seconds = 0.0

        if not should_check or segment is None:
            return
        try:
            self._segments.put_nowait(segment)
        except queue.Full:
            logger.debug("Wake word queue full; dropping segment")

    # ------------------------------------------------------------------ #
    # Recognition worker
    # ------------------------------------------------------------------ #

    def _detect_loop(self) -> None:
        while self._running:
            try:
                segment = self._segments.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if not self._active or not self._enabled:
                    continue
                if time.monotonic() - self._last_detection < self.cooldown_seconds:
                    continue
                result = self._stt.transcribe(segment, sample_rate=self.sample_rate)
                self.transcriptions_checked += 1
                if result.error:
                    self._last_error = result.error
                    continue
                hit = match_wake_hit(
                    result.text, self.wake_word, self.aliases, self.sensitivity
                )
                if not hit:
                    continue
                self._last_detection = time.monotonic()
                self.detections += 1
                logger.info("Wake word detected (%r)", hit.alias)
                callback = self._callback
                if callback:
                    try:
                        callback(hit)
                    except Exception as exc:
                        logger.warning("Wake callback failed: %s", exc)
            finally:
                self._segments.task_done()
