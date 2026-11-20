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
class MemoryCreateRequest(BaseModel):
    category: Literal["fact", "project", "preference", "context"]
    key: str
    content: str
    confidence: float = 1.0


class MemoryResponse(BaseModel):
    id: str
    category: Literal["fact", "project", "preference", "context"]
    key: str
    content: str
    confidence: float
    sensitivity: str
    created_at: str
    updated_at: str


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

