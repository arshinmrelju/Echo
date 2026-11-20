from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, HTTPException, Query
from echo.api.schemas import TaskCreateRequest, TaskResponse, TaskUpdateRequest
from echo.core.database import get_database

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


@router.get("", response_model=List[TaskResponse])
async def list_tasks(limit: int = Query(50, ge=1, le=100)):
    db = get_database()
    with db.get_connection() as conn:
        cur = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?;", (limit,))
        rows = cur.fetchall()
        return [
            TaskResponse(
                id=r["id"],
                conversation_id=r["conversation_id"],
                goal=r["goal"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


@router.post("", response_model=TaskResponse)
async def create_task(req: TaskCreateRequest):
    db = get_database()
    task_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, conversation_id, goal, status, created_at, updated_at)
            VALUES (?, ?, ?, 'created', ?, ?);
            """,
            (task_id, req.conversation_id, req.goal.strip(), now_str, now_str),
        )
    return TaskResponse(
        id=task_id,
        conversation_id=req.conversation_id,
        goal=req.goal.strip(),
        status="created",
        created_at=now_str,
        updated_at=now_str,
    )


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, req: TaskUpdateRequest):
    db = get_database()
    now_str = datetime.now(timezone.utc).isoformat()
    with db.transaction() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?;",
            (req.status, now_str, task_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")

        cur = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,))
        r = cur.fetchone()
        return TaskResponse(
            id=r["id"],
            conversation_id=r["conversation_id"],
            goal=r["goal"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    db = get_database()
    with db.transaction() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "id": task_id}

