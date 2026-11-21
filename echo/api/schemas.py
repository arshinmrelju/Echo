from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# Health & System Status
class HealthStatusResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    database: Literal["connected", "error"]
    ai_provider: str
    ai_available: bool
    timestamp: str


class SystemMetricsResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    uptime_seconds: float
    platform: str


# Conversation & Chat
class MessageCreateRequest(BaseModel):
    content: str
    conversation_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: str
    token_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    latest_message: Optional[str] = None


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = None


class ConversationUpdateRequest(BaseModel):
    title: str


# Settings
class SettingsResponse(BaseModel):
    ai_provider: str
    ai_model: str
    ai_api_key_configured: bool
    ai_api_base: Optional[str] = None
    ai_temperature: float
    ai_max_tokens: int
    theme: str
    startup_behavior: str
    data_dir: str


class SettingsUpdateRequest(BaseModel):
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_api_base: Optional[str] = None
    ai_temperature: Optional[float] = None
    ai_max_tokens: Optional[int] = None
    theme: Optional[str] = None
    startup_behavior: Optional[str] = None


# Memory
MemoryCategory = Literal["fact", "project", "preference", "context", "task", "conversation"]


class MemoryCreateRequest(BaseModel):
    category: MemoryCategory
    key: str
    content: str
    confidence: float = 1.0
    source: str = "user"
    tags: List[str] = []
    pinned: bool = False
    allow_sensitive: bool = False


class MemoryUpdateRequest(BaseModel):
    category: Optional[MemoryCategory] = None
    key: Optional[str] = None
    content: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None
    sensitivity: Optional[Literal["normal", "high"]] = None
    allow_sensitive: Optional[bool] = None


class MemoryClearRequest(BaseModel):
    category: Optional[MemoryCategory] = None
    confirm: bool = False


class MemoryResponse(BaseModel):
    id: str
    category: MemoryCategory
    key: str
    content: str
    confidence: float
    sensitivity: str
    source: str = "user"
    tags: List[str] = []
    pinned: bool = False
    archived: bool = False
    permission_granted: bool = False
    last_used_at: Optional[str] = None
    use_count: int = 0
    created_at: str
    updated_at: str


class MemoryStatsResponse(BaseModel):
    total: int
    by_category: Dict[str, int]
    by_source: Dict[str, int]
    sensitive: int
    pinned: int
    last_updated_at: Optional[str] = None


# File intelligence (Stage 6)
class FileDirectoryCreateRequest(BaseModel):
    path: str
    label: Optional[str] = None
    recursive: bool = True
    index_now: bool = False


class FileDirectoryResponse(BaseModel):
    id: str
    path: str
    label: Optional[str] = None
    recursive: bool = True
    enabled: bool = True
    created_at: str
    last_indexed_at: Optional[str] = None
    file_count: int = 0


class FileIndexRequest(BaseModel):
    directory_id: Optional[str] = None
    force: bool = False


class FileEntryResponse(BaseModel):
    id: str
    directory_id: str
    path: str
    name: str
    extension: str
    category: str
    size_bytes: int
    modified_at: Optional[float] = None
    created_at: Optional[str] = None
    content_hash: Optional[str] = None
    content_status: str = "not_indexed"
    indexed_at: str
    snippet: Optional[str] = None


class FileSearchResponse(BaseModel):
    results: List[FileEntryResponse]
    count: int
    limit: int
    offset: int


class FileOpenRequest(BaseModel):
    path: str


class FileRenameRequest(BaseModel):
    path: str
    new_name: str
    confirm: bool = False


class FileCopyMoveRequest(BaseModel):
    path: str
    destination: str
    confirm: bool = False


class FileOrganizeRequest(BaseModel):
    directory: str
    destination_root: Optional[str] = None
    confirm: bool = False
    dry_run: bool = True


class FileBulkRenameRequest(BaseModel):
    directory: str
    find: str
    replace: str
    confirm: bool = False
    dry_run: bool = True


class FileQuarantineRequest(BaseModel):
    directory: Optional[str] = None
    confirm: bool = False
    dry_run: bool = True


class FileSummarizeRequest(BaseModel):
    path: str
    use_ai: bool = True


class FileSettingsUpdateRequest(BaseModel):
    content_indexing: Optional[bool] = None
    ocr_enabled: Optional[bool] = None
    include_hidden: Optional[bool] = None
    max_file_size_mb: Optional[int] = Field(default=None, ge=1, le=1024)
    max_hash_size_mb: Optional[int] = Field(default=None, ge=1, le=4096)
    max_content_chars: Optional[int] = Field(default=None, ge=500, le=100000)
    max_index_files: Optional[int] = Field(default=None, ge=100, le=200000)
    bulk_confirm_threshold: Optional[int] = Field(default=None, ge=2, le=500)


# Tasks
class TaskCreateRequest(BaseModel):
    goal: str
    conversation_id: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    status: Literal["created", "planning", "in_progress", "completed", "failed", "cancelled"]
    error: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    conversation_id: Optional[str]
    goal: str
    status: str
    created_at: str
    updated_at: str


# Voice
class VoiceSettingsUpdateRequest(BaseModel):
    auto_start: Optional[bool] = None
    mode: Optional[Literal["push_to_talk", "wake_word", "continuous"]] = None
    wake_word: Optional[str] = None
    wake_aliases: Optional[List[str]] = None
    wake_sensitivity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stt_model: Optional[str] = None
    stt_device: Optional[Literal["cpu", "cuda", "auto"]] = None
    stt_compute_type: Optional[str] = None
    stt_language: Optional[str] = None
    partial_transcription: Optional[bool] = None
    min_transcript_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tts_engine: Optional[Literal["pyttsx3"]] = None
    tts_voice: Optional[str] = None
    tts_rate: Optional[int] = Field(default=None, ge=80, le=350)
    tts_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mic_device_index: Optional[int] = None
    mic_sample_rate: Optional[int] = Field(default=None, ge=8000, le=48000)
    silence_threshold_seconds: Optional[float] = Field(default=None, ge=0.4, le=5.0)
    vad_rms_threshold: Optional[float] = Field(default=None, ge=0.001, le=0.3)
    min_speech_seconds: Optional[float] = Field(default=None, ge=0.1, le=2.0)
    max_utterance_seconds: Optional[float] = Field(default=None, ge=3.0, le=60.0)
    barge_in_enabled: Optional[bool] = None
    barge_in_rms_threshold: Optional[float] = Field(default=None, ge=0.005, le=0.5)
    continuous_timeout_seconds: Optional[float] = Field(default=None, ge=5.0, le=300.0)
    wake_command_timeout_seconds: Optional[float] = Field(default=None, ge=3.0, le=60.0)
    save_recordings: Optional[bool] = None
    recording_retention: Optional[int] = Field(default=None, ge=0, le=200)


class VoicePushToTalkRequest(BaseModel):
    conversation_id: Optional[str] = None


class VoiceConversationRequest(BaseModel):
    conversation_id: Optional[str] = None


class VoiceSpeakTestRequest(BaseModel):
    text: Optional[str] = None


# Remote relay
class RemoteSettingsUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    bot_token: Optional[str] = None
    owner_user_id: Optional[int] = None
    allowed_user_ids: Optional[List[int]] = None

    pairing_ttl_seconds: Optional[int] = Field(default=None, ge=60, le=3600)
    command_rate_limit: Optional[int] = Field(default=None, ge=1, le=120)
    pairing_attempt_limit: Optional[int] = Field(default=None, ge=1, le=20)
    pairing_attempt_window_seconds: Optional[int] = Field(default=None, ge=60, le=3600)

    poll_timeout_seconds: Optional[int] = Field(default=None, ge=5, le=50)
    reconnect_max_seconds: Optional[int] = Field(default=None, ge=5, le=600)
    screenshot_enabled: Optional[bool] = None
    max_screenshot_mb: Optional[int] = Field(default=None, ge=1, le=20)

    notify_critical_alerts: Optional[bool] = None
    notify_warnings: Optional[bool] = None
    notify_task_results: Optional[bool] = None
    notify_approval_requests: Optional[bool] = None
    notify_connectivity: Optional[bool] = None
    notify_monitor_events: Optional[bool] = None
    monitor_event_min_severity: Optional[Literal["info", "notice", "warning", "critical"]] = None
    monitor_event_categories: Optional[List[str]] = None

    queue_ttl_hours: Optional[int] = Field(default=None, ge=1, le=168)
    queue_max_items: Optional[int] = Field(default=None, ge=10, le=2000)
    queue_batch_size: Optional[int] = Field(default=None, ge=1, le=50)
    send_rate_per_second: Optional[float] = Field(default=None, ge=0.2, le=20.0)

    paused: Optional[bool] = None
    pause_reason: Optional[str] = None


class RemoteUserRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    username: Optional[str] = None


class RemotePauseRequest(BaseModel):
    reason: Optional[str] = None


# Monitoring
class MonitoringSettingsUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    profile: Optional[Literal["quiet", "balanced", "strict"]] = None

    poll_interval_seconds: Optional[int] = Field(default=None, ge=2, le=120)
    retention_days: Optional[int] = Field(default=None, ge=1, le=365)

    monitor_cpu: Optional[bool] = None
    monitor_memory: Optional[bool] = None
    monitor_disk: Optional[bool] = None
    monitor_battery: Optional[bool] = None
    monitor_network: Optional[bool] = None
    monitor_temperature: Optional[bool] = None
    monitor_processes: Optional[bool] = None
    monitor_hung_windows: Optional[bool] = None
    monitor_windows_events: Optional[bool] = None

    cpu_warning_percent: Optional[float] = Field(default=None, ge=1, le=100)
    cpu_critical_percent: Optional[float] = Field(default=None, ge=1, le=100)
    cpu_sustained_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    memory_warning_percent: Optional[float] = Field(default=None, ge=1, le=100)
    memory_critical_percent: Optional[float] = Field(default=None, ge=1, le=100)
    memory_sustained_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

    disk_paths: Optional[List[str]] = None
    disk_free_warning_gb: Optional[float] = Field(default=None, ge=0.1, le=1000)
    disk_free_critical_gb: Optional[float] = Field(default=None, ge=0.1, le=1000)
    disk_percent_warning: Optional[float] = Field(default=None, ge=1, le=100)
    disk_percent_critical: Optional[float] = Field(default=None, ge=1, le=100)
    disk_sustained_seconds: Optional[int] = Field(default=None, ge=5, le=3600)

    battery_warning_percent: Optional[float] = Field(default=None, ge=1, le=100)
    battery_critical_percent: Optional[float] = Field(default=None, ge=1, le=100)
    battery_sustained_seconds: Optional[int] = Field(default=None, ge=5, le=600)

    network_targets: Optional[List[str]] = None
    network_check_interval_seconds: Optional[int] = Field(default=None, ge=5, le=300)
    network_timeout_seconds: Optional[float] = Field(default=None, ge=0.5, le=30)
    network_failure_seconds: Optional[int] = Field(default=None, ge=10, le=1800)

    temperature_warning_celsius: Optional[float] = Field(default=None, ge=20, le=120)
    temperature_critical_celsius: Optional[float] = Field(default=None, ge=20, le=130)
    temperature_sustained_seconds: Optional[int] = Field(default=None, ge=5, le=1800)
    temperature_interval_seconds: Optional[int] = Field(default=None, ge=15, le=600)

    windows_event_interval_seconds: Optional[int] = Field(default=None, ge=15, le=600)
    windows_event_lookback_seconds: Optional[int] = Field(default=None, ge=30, le=3600)
    windows_event_max_per_log: Optional[int] = Field(default=None, ge=5, le=100)

    monitored_applications: Optional[List[str]] = None
    hung_window_seconds: Optional[int] = Field(default=None, ge=5, le=600)

    alert_cooldown_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    escalation_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    recovery_margin_percent: Optional[float] = Field(default=None, ge=0, le=30)
    recovery_margin_gb: Optional[float] = Field(default=None, ge=0, le=100)
    notification_on_recovery: Optional[bool] = None

    top_process_count: Optional[int] = Field(default=None, ge=0, le=20)

    model_config = {"extra": "ignore"}

