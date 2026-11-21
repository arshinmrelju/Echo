"""Offline speech-to-text using faster-whisper (CTranslate2)."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

logger = logging.getLogger("echo.voice.stt")

try:
    from faster_whisper import WhisperModel  # type: ignore
    _WHISPER_AVAILABLE = True
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore
    _WHISPER_AVAILABLE = False
    logger.warning("faster-whisper is not installed; speech-to-text is unavailable")


_HALLUCINATIONS = {
    "thank you.",
    "thanks for watching.",
    "thanks for watching!",
    "thank you for watching.",
    "please subscribe.",
    "you",
    "bye.",
    "[blank_audio]",
    "(silence)",
    "♪",
}


def clean_transcript(text: str) -> str:
    """Normalize recognizer output without changing its meaning."""
    if not text:
        return ""
    text = text.replace("\u200b", " ")
    text = re.sub(r"\[(?:blank_audio|music|silence|inaudible)\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s\-–—,.;:]+", "", text)
    return text


@dataclass
class TranscriptionResult:
    text: str = ""
    confidence: float = 0.0
    language: str = "en"
    duration_seconds: float = 0.0
    error: Optional[str] = None
    is_partial: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)


class WhisperSTT:
    """Lazy, thread-safe wrapper around a single faster-whisper model instance."""

    def __init__(
        self,
        model_name: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language or "en"
        self._model: Optional[object] = None
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()
        self.last_latency_ms: float = 0.0

    @property
    def is_available(self) -> bool:
        return _WHISPER_AVAILABLE

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def load(self) -> bool:
        """Load the model once. Returns False with an actionable error on failure."""
        if self._model is not None:
            return True
        if not _WHISPER_AVAILABLE:
            self._load_error = (
                "faster-whisper is not installed. Run: pip install -r requirements.txt"
            )
            return False
        with self._lock:
            if self._model is not None:
                return True
            try:
                started = time.monotonic()
                logger.info(
                    "Loading Whisper model %r (device=%s, compute=%s)",
                    self.model_name,
                    self.device,
                    self.compute_type,
                )
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                self._load_error = None
                logger.info(
                    "Whisper model ready in %.1fs", time.monotonic() - started
                )
                return True
            except Exception as exc:
                self._model = None
                self._load_error = (
                    f"Speech model '{self.model_name}' could not be loaded: {exc}. "
                    "Check your network connection for the first download or choose a cached model."
                )
                logger.error("Whisper model load failed: %s", exc)
                return False

    def transcribe(
        self,
        audio: "np.ndarray",
        sample_rate: int = 16000,
        *,
        partial: bool = False,
    ) -> TranscriptionResult:
        if np is None:
            return TranscriptionResult(error="numpy is not installed; audio capture is unavailable")
        if audio is None or len(audio) == 0:
            return TranscriptionResult(error=None)
        if sample_rate not in (16000, 16000.0):
            from echo.voice.vad import resample_linear

            audio = resample_linear(audio, int(sample_rate), 16000)
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.reshape(-1)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1.0:
            audio = audio / 32768.0
        duration = len(audio) / 16000.0

        if not self.load():
            return TranscriptionResult(
                duration_seconds=duration, error=self._load_error, is_partial=partial
            )

        started = time.monotonic()
        try:
            with self._lock:
                segments, info = self._model.transcribe(  # type: ignore[union-attr]
                    audio,
                    language=self.language,
                    beam_size=1,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 350},
                    condition_on_previous_text=False,
                    without_timestamps=True,
                )
                parts = []
                logprobs = []
                for segment in segments:
                    parts.append(segment.text)
                    logprobs.append(float(getattr(segment, "avg_logprob", -1.0)))

            self.last_latency_ms = (time.monotonic() - started) * 1000.0
            text = clean_transcript(" ".join(parts))
            if text.strip().lower() in _HALLUCINATIONS and duration < 1.4:
                text = ""
            confidence = 0.0
            if logprobs:
                confidence = max(0.0, min(1.0, (sum(logprobs) / len(logprobs)) + 1.0))
            return TranscriptionResult(
                text=text,
                confidence=confidence,
                language=getattr(info, "language", self.language) or self.language,
                duration_seconds=duration,
                is_partial=partial,
            )
        except Exception as exc:
            self.last_latency_ms = (time.monotonic() - started) * 1000.0
            logger.error("Whisper transcription failed: %s", exc)
            return TranscriptionResult(
                duration_seconds=duration,
                error=f"Speech recognition failed: {exc}",
                is_partial=partial,
            )
