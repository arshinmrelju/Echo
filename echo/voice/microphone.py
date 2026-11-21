"""Microphone capture management built on sounddevice."""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import sounddevice as sd  # type: ignore

    _SD_AVAILABLE = True
except ImportError:  # pragma: no cover
    sd = None  # type: ignore
    _SD_AVAILABLE = False
    logging.getLogger("echo.voice.microphone").warning(
        "sounddevice is not installed; microphone capture is unavailable"
    )

from echo.voice.vad import resample_linear

logger = logging.getLogger("echo.voice.microphone")

AudioCallback = Callable[["np.ndarray"], None]
ErrorCallback = Callable[[str], None]


def list_input_devices() -> List[dict]:
    if not _SD_AVAILABLE:
        return []
    devices: List[dict] = []
    try:
        default_input = sd.default.device[0]  # type: ignore[union-attr]
    except Exception:
        default_input = -1
    try:
        for index, device in enumerate(sd.query_devices()):  # type: ignore[union-attr]
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            devices.append(
                {
                    "index": index,
                    "name": device["name"],
                    "channels": int(device["max_input_channels"]),
                    "sample_rate": int(device.get("default_samplerate", 16000)),
                    "default": index == default_input,
                }
            )
    except Exception as exc:
        logger.error("Failed to enumerate microphone devices: %s", exc)
    return devices


class MicrophoneStream:
    """Continuous mono capture normalised to the requested sample rate.

    Opening a device at 16 kHz is attempted first; some Windows drivers only
    accept 44.1/48 kHz, so the stream falls back to the device default and
    linearly resamples each frame.
    """

    def __init__(
        self,
        callback: AudioCallback,
        sample_rate: int = 16000,
        device_index: Optional[int] = None,
        frame_duration_ms: int = 30,
        on_error: Optional[ErrorCallback] = None,
    ) -> None:
        self._callback = callback
        self._sample_rate = int(sample_rate)
        self._device_index = device_index
        self._frame_duration_ms = frame_duration_ms
        self._on_error = on_error
        self._stream: Optional[object] = None
        self._stream_rate = self._sample_rate
        self._channels = 1
        self._muted = False
        self._lock = threading.RLock()
        self.error: Optional[str] = None
        self.status_message: Optional[str] = None
        self.device_name: Optional[str] = None
        self.is_resampling = False

    @property
    def is_available(self) -> bool:
        return _SD_AVAILABLE and np is not None

    @property
    def is_active(self) -> bool:
        return self._stream is not None

    @property
    def is_muted(self) -> bool:
        with self._lock:
            return self._muted

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def mute(self) -> None:
        with self._lock:
            self._muted = True

    def unmute(self) -> None:
        with self._lock:
            self._muted = False

    def start(self) -> bool:
        if not _SD_AVAILABLE or np is None:
            self.error = "Microphone support is unavailable. Run: pip install -r requirements.txt"
            return False
        if self._stream is not None:
            return True

        candidate_rates = [self._sample_rate]
        device_default = self._device_default_rate()
        if device_default and device_default not in candidate_rates:
            candidate_rates.append(device_default)

        last_error: Optional[Exception] = None
        for rate in candidate_rates:
            for channels in (1, 2):
                stream = None
                try:
                    stream = sd.InputStream(  # type: ignore[union-attr]
                        samplerate=rate,
                        channels=channels,
                        dtype="float32",
                        device=self._device_index,
                        blocksize=max(1, int(rate * self._frame_duration_ms / 1000)),
                        callback=self._sd_callback,
                    )
                    stream.start()
                    self._stream = stream
                    self._stream_rate = rate
                    self._channels = channels
                    self.is_resampling = rate != self._sample_rate
                    self.error = None
                    self.device_name = self._resolve_name()
                    logger.info(
                        "Microphone started: %s @ %d Hz (%d ch, target %d Hz)",
                        self.device_name,
                        rate,
                        channels,
                        self._sample_rate,
                    )
                    return True
                except Exception as exc:
                    last_error = exc
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
        self.error = f"Microphone could not be opened: {last_error}"
        logger.error(self.error)
        if self._on_error:
            self._on_error(self.error)
        return False

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                stream.close()  # type: ignore[union-attr]
            except Exception:
                pass
        logger.info("Microphone stopped")

    def _device_default_rate(self) -> Optional[int]:
        try:
            index = self._device_index
            if index is None:
                index = sd.default.device[0]  # type: ignore[union-attr]
            info = sd.query_devices(index)  # type: ignore[union-attr]
            return int(info.get("default_samplerate", 0)) or None
        except Exception:
            return None

    def _resolve_name(self) -> Optional[str]:
        try:
            index = self._device_index
            if index is None:
                index = sd.default.device[0]  # type: ignore[union-attr]
            return str(sd.query_devices(index)["name"])  # type: ignore[union-attr]
        except Exception:
            return None

    def _sd_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.status_message = str(status)
            logger.debug("Microphone status: %s", status)
        with self._lock:
            if self._muted:
                return
        try:
            audio = np.asarray(indata, dtype=np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=1) if self._channels > 1 else audio[:, 0]
            audio = audio.reshape(-1).copy()
            if self.is_resampling:
                audio = resample_linear(audio, self._stream_rate, self._sample_rate)
            self._callback(audio)
        except Exception as exc:
            logger.warning("Microphone callback error: %s", exc, exc_info=True)
