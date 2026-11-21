"""Thread-safe voice state machine with explicit legal transitions."""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable, Optional, Set

logger = logging.getLogger("echo.voice.state_machine")

StateListener = Callable[["VoiceState", "VoiceState", str], None]


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    MUTED = "muted"
    ERROR = "error"


_ALLOWED: dict[VoiceState, Set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING, VoiceState.PROCESSING, VoiceState.MUTED, VoiceState.ERROR},
    VoiceState.LISTENING: {VoiceState.PROCESSING, VoiceState.IDLE, VoiceState.MUTED, VoiceState.ERROR},
    VoiceState.PROCESSING: {
        VoiceState.SPEAKING,
        VoiceState.LISTENING,
        VoiceState.IDLE,
        VoiceState.MUTED,
        VoiceState.ERROR,
    },
    VoiceState.SPEAKING: {
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.IDLE,
        VoiceState.MUTED,
        VoiceState.ERROR,
    },
    VoiceState.MUTED: {VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.ERROR: {VoiceState.IDLE, VoiceState.MUTED},
}


class VoiceStateMachine:
    """Small deterministic state machine; listeners fire outside the lock."""

    def __init__(self, listener: Optional[StateListener] = None) -> None:
        self._state = VoiceState.IDLE
        self._listener = listener
        self._lock = threading.RLock()

    @property
    def state(self) -> VoiceState:
        with self._lock:
            return self._state

    def set_listener(self, listener: Optional[StateListener]) -> None:
        with self._lock:
            self._listener = listener

    def transition(self, new_state: VoiceState, reason: str = "") -> bool:
        with self._lock:
            old = self._state
            if old == new_state:
                return False
            if new_state not in _ALLOWED[old]:
                logger.debug("Ignoring voice transition %s -> %s (%s)", old.value, new_state.value, reason)
                return False
            self._state = new_state

        logger.info(
            "Voice state: %s -> %s%s",
            old.value,
            new_state.value,
            f" ({reason})" if reason else "",
        )
        self._notify(old, new_state, reason)
        return True

    def force(self, new_state: VoiceState, reason: str = "") -> bool:
        with self._lock:
            old = self._state
            if old == new_state:
                return False
            self._state = new_state
        logger.info(
            "Voice state forced: %s -> %s%s",
            old.value,
            new_state.value,
            f" ({reason})" if reason else "",
        )
        self._notify(old, new_state, reason)
        return True

    def to_idle(self, reason: str = "") -> bool:
        return self.transition(VoiceState.IDLE, reason or "idle") or self.force(VoiceState.IDLE, reason)

    def to_listening(self, reason: str = "") -> bool:
        return self.transition(VoiceState.LISTENING, reason or "listening")

    def to_processing(self, reason: str = "") -> bool:
        return self.transition(VoiceState.PROCESSING, reason or "processing")

    def to_speaking(self, reason: str = "") -> bool:
        return self.transition(VoiceState.SPEAKING, reason or "speaking")

    def to_muted(self, reason: str = "muted") -> bool:
        return self.transition(VoiceState.MUTED, reason)

    def to_error(self, reason: str = "error") -> bool:
        return self.transition(VoiceState.ERROR, reason)

    def _notify(self, old: VoiceState, new: VoiceState, reason: str) -> None:
        listener = self._listener
        if not listener:
            return
        try:
            listener(old, new, reason)
        except Exception as exc:
            logger.warning("Voice state listener failed: %s", exc)
