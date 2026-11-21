"""Audio helpers: RMS, linear resampling, ring buffers, and utterance endpointing."""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Iterable, List, Optional, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only without voice extras
    np = None


AudioFrame = Sequence[float]


def rms(frame: AudioFrame) -> float:
    """Root-mean-square level of a mono float frame in [-1, 1]."""
    if frame is None or len(frame) == 0:
        return 0.0
    if np is not None:
        arr = np.asarray(frame, dtype=np.float32)
        return float(np.sqrt(np.mean(np.square(arr))))
    return math.sqrt(sum(float(sample) * float(sample) for sample in frame) / len(frame))


def audio_level(frame: AudioFrame) -> float:
    """Map RMS to a perceptually useful 0..1 meter value."""
    value = rms(frame)
    if value <= 0.0:
        return 0.0
    # -55 dBFS .. -6 dBFS -> 0 .. 1
    db = 20.0 * math.log10(max(value, 1e-7))
    return max(0.0, min(1.0, (db + 55.0) / 49.0))


def frame_duration_seconds(frame: AudioFrame, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return len(frame) / float(sample_rate)


def resample_linear(
    frame: AudioFrame, source_rate: int, target_rate: int
) -> "np.ndarray":
    """Cheap linear resampling for device fallback rates (e.g. 44.1 kHz capture)."""
    if np is None:
        raise RuntimeError("numpy is required for audio resampling")
    if source_rate == target_rate or len(frame) == 0:
        return np.asarray(frame, dtype=np.float32)
    source = np.asarray(frame, dtype=np.float32)
    target_length = max(1, int(round(len(source) * target_rate / float(source_rate))))
    source_positions = np.linspace(0.0, 1.0, num=len(source), endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, source).astype(np.float32)


class AudioRingBuffer:
    """Bounded history of recent frames used for wake/PTT/barge-in pre-roll."""

    def __init__(self, sample_rate: int, capacity_seconds: float = 0.6) -> None:
        self._frames: Deque["np.ndarray"] = deque(maxlen=max(1, int(sample_rate * capacity_seconds / 480)))

    def append(self, frame: "np.ndarray") -> None:
        self._frames.append(frame.copy())

    def snapshot(self) -> List["np.ndarray"]:
        return [frame.copy() for frame in self._frames]

    def clear(self) -> None:
        self._frames.clear()

    def __len__(self) -> int:
        return len(self._frames)


class UtteranceDetector:
    """Energy-gated endpoint detector.

    It only decides when an utterance starts and ends; speech recognition is
    deliberately kept out of the audio callback path.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        threshold: float = 0.012,
        silence_seconds: float = 1.2,
        min_speech_seconds: float = 0.25,
        max_seconds: float = 15.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_seconds = silence_seconds
        self.min_speech_seconds = min_speech_seconds
        self.max_seconds = max_seconds
        self._frames: List["np.ndarray"] = []
        self._total_seconds = 0.0
        self._speech_seconds = 0.0
        self._silence_run = 0.0
        self._speech_started = False

    def reset(self, seed_frames: Optional[Iterable["np.ndarray"]] = None) -> None:
        self._frames = []
        self._total_seconds = 0.0
        self._speech_seconds = 0.0
        self._silence_run = 0.0
        self._speech_started = False
        if seed_frames:
            for frame in seed_frames:
                self._append(frame, speech=rms(frame) >= self.threshold)

    def _append(self, frame: "np.ndarray", speech: bool) -> None:
        duration = frame_duration_seconds(frame, self.sample_rate)
        self._frames.append(frame.copy())
        self._total_seconds += duration
        if speech:
            self._speech_started = True
            self._speech_seconds += duration
            self._silence_run = 0.0
        elif self._speech_started:
            self._silence_run += duration

    def feed(self, frame: "np.ndarray") -> bool:
        """Add a frame; return True when the utterance should be finalised."""
        self._append(frame, speech=rms(frame) >= self.threshold)
        if not self._speech_started:
            # Do not buffer an endless quiet stream; keep only the recent tail.
            if self._total_seconds > max(0.6, self.silence_seconds):
                self._frames = self._frames[-3:]
                self._total_seconds = sum(
                    frame_duration_seconds(f, self.sample_rate) for f in self._frames
                )
            return False
        if self._silence_run >= self.silence_seconds:
            return True
        if self._total_seconds >= self.max_seconds:
            return True
        return False

    def finish(self) -> None:
        """External stop (push-to-talk release)."""

    @property
    def has_speech(self) -> bool:
        return self._speech_started and self._speech_seconds >= self.min_speech_seconds

    @property
    def speech_seconds(self) -> float:
        return self._speech_seconds

    @property
    def duration_seconds(self) -> float:
        return self._total_seconds

    def buffer(self) -> "np.ndarray":
        if np is None:
            raise RuntimeError("numpy is required for audio capture")
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).astype(np.float32)
