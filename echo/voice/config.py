"""Voice subsystem configuration and capability models."""
from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _normalize_wake_word(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.strip().lower())
    value = re.sub(r"\s+", " ", value)
    return value.strip() or "echo"


class VoiceSettings(BaseModel):
    """All persisted voice preferences. Audio is never recorded unless opted in."""

    # Session
    auto_start: bool = False
    mode: Literal["push_to_talk", "wake_word", "continuous"] = "wake_word"

    # Wake word
    wake_word: str = "echo"
    wake_aliases: List[str] = Field(default_factory=lambda: ["hey echo", "ok echo", "eco"])
    wake_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)

    # Speech to text (offline faster-whisper)
    stt_model: str = "tiny.en"
    stt_device: Literal["cpu", "cuda", "auto"] = "cpu"
    stt_compute_type: str = "int8"
    stt_language: str = "en"
    partial_transcription: bool = True
    min_transcript_confidence: float = Field(default=0.15, ge=0.0, le=1.0)

    # Text to speech (offline Windows SAPI via pyttsx3)
    tts_engine: Literal["pyttsx3"] = "pyttsx3"
    tts_voice: Optional[str] = None
    tts_rate: int = Field(default=175, ge=80, le=350)
    tts_volume: float = Field(default=1.0, ge=0.0, le=1.0)

    # Microphone and endpointing
    mic_device_index: Optional[int] = None
    mic_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    silence_threshold_seconds: float = Field(default=1.2, ge=0.4, le=5.0)
    vad_rms_threshold: float = Field(default=0.012, ge=0.001, le=0.3)
    min_speech_seconds: float = Field(default=0.25, ge=0.1, le=2.0)
    max_utterance_seconds: float = Field(default=15.0, ge=3.0, le=60.0)

    # Conversation
    barge_in_enabled: bool = True
    barge_in_rms_threshold: float = Field(default=0.03, ge=0.005, le=0.5)
    continuous_timeout_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    wake_command_timeout_seconds: float = Field(default=12.0, ge=3.0, le=60.0)

    # Privacy
    save_recordings: bool = False
    recording_retention: int = Field(default=20, ge=0, le=200)

    model_config = {"extra": "ignore"}

    @field_validator("wake_word")
    @classmethod
    def _validate_wake_word(cls, value: str) -> str:
        return _normalize_wake_word(value)

    @field_validator("wake_aliases")
    @classmethod
    def _validate_aliases(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            normalized = _normalize_wake_word(value)
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def public_dict(self) -> dict:
        return self.model_dump()


DEFAULT_SETTINGS = VoiceSettings()
