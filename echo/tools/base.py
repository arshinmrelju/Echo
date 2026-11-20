from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional, Type
from pydantic import BaseModel, Field


class PermissionLevel(str, Enum):
    AUTOMATIC = "automatic"
    APPROVAL_REQUIRED = "approval_required"


class ToolCategory(str, Enum):
    SCREEN = "screen"
    WINDOW = "window"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    APPLICATION = "application"
    FILESYSTEM = "filesystem"
    CLIPBOARD = "clipboard"
    SYSTEM = "system"


class ToolExecutionResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    verified: bool = False
    requires_approval: bool = False
    approval_request_id: Optional[str] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    category: ToolCategory
    permission_level: PermissionLevel
    input_schema: Type[BaseModel]
    timeout_seconds: float = 15.0

    model_config = {
        "arbitrary_types_allowed": True
    }
