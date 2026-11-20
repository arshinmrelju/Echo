import asyncio
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional
import uuid
from pydantic import BaseModel, ValidationError
from echo.core.database import Database, get_database
from echo.tools.base import PermissionLevel, ToolCategory, ToolDefinition, ToolExecutionResult
from echo.tools.permissions import get_permission_manager

logger = logging.getLogger("echo.tools")


class ToolRegistry:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
        self.permission_manager = get_permission_manager()
        self._tools: Dict[str, ToolDefinition] = {}
        self._executors: Dict[str, Callable[[Any], Coroutine[Any, Any, Any]]] = {}

    def register(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        permission_level: PermissionLevel,
        input_schema: type[BaseModel],
        executor: Callable[[Any], Coroutine[Any, Any, Any]],
        timeout_seconds: float = 15.0,
    ) -> None:
        tool_def = ToolDefinition(
            name=name,
            description=description,
            category=category,
            permission_level=permission_level,
            input_schema=input_schema,
            timeout_seconds=timeout_seconds,
        )
        self._tools[name] = tool_def
        self._executors[name] = executor
        logger.debug("Registered tool: %s (%s, %s)", name, category.value, permission_level.value)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for name, t in self._tools.items():
            if category and t.category.value != category:
                continue
            result.append({
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "permission_level": t.permission_level.value,
                "schema": t.input_schema.model_json_schema(),
                "timeout_seconds": t.timeout_seconds,
            })
        return result

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        approval_id: Optional[str] = None,
    ) -> ToolExecutionResult:
        start_time = time.time()
        tool = self._tools.get(name)
        if not tool:
            return ToolExecutionResult(
                success=False,
                error=f"Tool '{name}' is not registered in the system.",
                execution_time_ms=0.0,
            )

        # 1. Input Validation against schema
        try:
            validated_args = tool.input_schema.model_validate(arguments)
        except ValidationError as val_err:
            elapsed = (time.time() - start_time) * 1000
            self._log_action(name, arguments, "failed", f"Validation error: {val_err}")
            return ToolExecutionResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {val_err}",
                execution_time_ms=elapsed,
            )

        # 2. Permission Evaluation
        if tool.permission_level == PermissionLevel.APPROVAL_REQUIRED:
            if not approval_id:
                # Issue pending approval request
                req = self.permission_manager.request_approval(
                    tool_name=name,
                    args=arguments,
                    category=tool.category.value,
                    description=tool.description,
                )
                elapsed = (time.time() - start_time) * 1000
                return ToolExecutionResult(
                    success=False,
                    requires_approval=True,
                    approval_request_id=req.id,
                    error=f"Execution of '{name}' requires user approval.",
                    execution_time_ms=elapsed,
                )
            else:
                # Check provided approval
                req = self.permission_manager.get_request(approval_id)
                if not req or req.status != "approved" or req.tool_name != name:
                    elapsed = (time.time() - start_time) * 1000
                    return ToolExecutionResult(
                        success=False,
                        error="Action was not approved or approval has expired.",
                        execution_time_ms=elapsed,
                    )

        # 3. Execution within timeout
        executor = self._executors[name]
        try:
            res_data = await asyncio.wait_for(
                executor(validated_args),
                timeout=tool.timeout_seconds,
            )
            elapsed = (time.time() - start_time) * 1000
            self._log_action(name, arguments, "success", "Executed successfully")
            return ToolExecutionResult(
                success=True,
                data=res_data,
                execution_time_ms=elapsed,
                verified=True,
            )
        except asyncio.TimeoutError:
            elapsed = (time.time() - start_time) * 1000
            err_msg = f"Tool '{name}' timed out after {tool.timeout_seconds} seconds."
            self._log_action(name, arguments, "timeout", err_msg)
            return ToolExecutionResult(
                success=False,
                error=err_msg,
                execution_time_ms=elapsed,
            )
        except Exception as ex:
            elapsed = (time.time() - start_time) * 1000
            err_msg = f"Tool execution failed: {str(ex)}"
            self._log_action(name, arguments, "error", err_msg)
            return ToolExecutionResult(
                success=False,
                error=err_msg,
                execution_time_ms=elapsed,
            )

    def _log_action(self, tool_name: str, args: Dict[str, Any], status: str, details: str):
        try:
            now_str = datetime.now(timezone.utc).isoformat()
            log_id = str(uuid.uuid4())
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO action_logs (id, action, actor, details, status, created_at)
                    VALUES (?, ?, 'agent', ?, ?, ?);
                    """,
                    (log_id, f"tool:{tool_name}", json.dumps({"args": args, "details": details}), status, now_str),
                )
        except Exception as log_err:
            logger.error("Failed to write to action log: %s", log_err)


_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
