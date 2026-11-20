from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from echo.core.database import get_database
from echo.tools.base import ToolExecutionResult
from echo.tools.bootstrap import initialize_all_tools
from echo.tools.permissions import ApprovalRequest, get_permission_manager
from echo.tools.registry import get_tool_registry

router = APIRouter(prefix="/api/v1/tools", tags=["Desktop Tools & Permissions"])

# Ensure tools are registered
initialize_all_tools()


class ExecuteToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    approval_id: Optional[str] = None


class ResolveApprovalRequest(BaseModel):
    approved: bool


@router.get("")
async def list_tools(category: Optional[str] = Query(None)):
    registry = get_tool_registry()
    tools = registry.list_tools(category=category)
    return {"tools": tools, "count": len(tools)}


@router.post("/execute", response_model=ToolExecutionResult)
async def execute_tool(req: ExecuteToolRequest):
    registry = get_tool_registry()
    result = await registry.execute(
        name=req.tool_name,
        arguments=req.arguments,
        approval_id=req.approval_id,
    )
    return result


@router.get("/approvals", response_model=List[ApprovalRequest])
async def list_pending_approvals():
    pm = get_permission_manager()
    return pm.list_pending()


@router.post("/approvals/{request_id}/resolve")
async def resolve_approval(request_id: str, req: ResolveApprovalRequest):
    pm = get_permission_manager()
    resolved = pm.resolve_request(request_id, req.approved)
    if not resolved:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"resolved": True, "request": resolved}


@router.get("/logs")
async def get_tool_logs(limit: int = Query(50, ge=1, le=100)):
    db = get_database()
    with db.get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, action, actor, details, status, created_at
            FROM action_logs
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "action": r["action"],
                "actor": r["actor"],
                "details": r["details"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
