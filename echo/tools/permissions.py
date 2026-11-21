import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Callable, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, Field
from echo.core.database import Database, get_database
from echo.core.events import Event, get_event_bus


ResolutionListener = Callable[["ApprovalRequest"], None]


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    args: Dict[str, Any]
    category: str
    description: str
    status: Literal["pending", "approved", "denied", "expired"] = "pending"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved_at: Optional[str] = None


class PermissionManager:
    """Manages approvals, session grants, and interactive permission evaluation."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
        self._pending_approvals: Dict[str, ApprovalRequest] = {}
        self._resolution_listeners: List[ResolutionListener] = []

    def add_resolution_listener(self, listener: ResolutionListener) -> None:
        if listener not in self._resolution_listeners:
            self._resolution_listeners.append(listener)

    def remove_resolution_listener(self, listener: ResolutionListener) -> None:
        if listener in self._resolution_listeners:
            self._resolution_listeners.remove(listener)

    def request_approval(
        self,
        tool_name: str,
        args: Dict[str, Any],
        category: str,
        description: str,
    ) -> ApprovalRequest:
        req_id = str(uuid.uuid4())
        req = ApprovalRequest(
            id=req_id,
            tool_name=tool_name,
            args=args,
            category=category,
            description=description,
            status="pending",
        )
        self._pending_approvals[req_id] = req
        self._emit(
            "approval_request",
            {
                "approval": {
                    "id": req.id,
                    "tool_name": req.tool_name,
                    "args": req.args,
                    "category": req.category,
                    "description": req.description,
                    "status": req.status,
                    "created_at": req.created_at,
                }
            },
        )
        return req

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(get_event_bus().publish(Event(topic=topic, payload=payload)))

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._pending_approvals.get(request_id)

    def list_pending(self) -> List[ApprovalRequest]:
        return [r for r in self._pending_approvals.values() if r.status == "pending"]

    def resolve_request(self, request_id: str, approved: bool) -> Optional[ApprovalRequest]:
        req = self._pending_approvals.get(request_id)
        if not req:
            return None
        now_str = datetime.now(timezone.utc).isoformat()
        req.status = "approved" if approved else "denied"
        req.resolved_at = now_str
        for listener in list(self._resolution_listeners):
            try:
                listener(req)
            except Exception:
                pass
        self._emit(
            "approval_resolved",
            {
                "approval": {
                    "id": req.id,
                    "tool_name": req.tool_name,
                    "status": req.status,
                    "resolved_at": req.resolved_at,
                }
            },
        )
        return req


_permission_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
