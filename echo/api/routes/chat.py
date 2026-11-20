from datetime import datetime, timezone
import json
from typing import List
import uuid
from fastapi import APIRouter, HTTPException
from echo.api.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
)
from echo.core.database import get_database

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


@router.get("", response_model=List[ConversationResponse])
async def list_conversations():
    db = get_database()
    with db.get_connection() as conn:
        cur = conn.execute(
            """
            SELECT c.*, 
                   COUNT(m.id) as message_count,
                   (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) as latest_message
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC;
            """
        )
        rows = cur.fetchall()
        return [
            ConversationResponse(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["message_count"],
                latest_message=r["latest_message"],
            )
            for r in rows
        ]


@router.post("", response_model=ConversationResponse)
async def create_conversation(req: ConversationCreateRequest):
    db = get_database()
    conv_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    title = req.title.strip() if req.title and req.title.strip() else "New Conversation"

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
            (conv_id, title, now_str, now_str),
        )

    return ConversationResponse(
        id=conv_id,
        title=title,
        created_at=now_str,
        updated_at=now_str,
        message_count=0,
        latest_message=None,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str):
    db = get_database()
    with db.get_connection() as conn:
        cur = conn.execute("SELECT * FROM conversations WHERE id = ?;", (conversation_id,))
        conv = cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cur = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
            (conversation_id,),
        )
        messages = [
            MessageResponse(
                id=m["id"],
                conversation_id=m["conversation_id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                token_count=m["token_count"],
                metadata=json.loads(m["metadata"]) if m["metadata"] else None,
            )
            for m in cur.fetchall()
        ]

        return ConversationDetailResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=len(messages),
            latest_message=messages[-1].content if messages else None,
            messages=messages,
        )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, req: ConversationUpdateRequest):
    db = get_database()
    now_str = datetime.now(timezone.utc).isoformat()
    with db.transaction() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?;",
            (req.title.strip(), now_str, conversation_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cur = conn.execute("SELECT * FROM conversations WHERE id = ?;", (conversation_id,))
        conv = cur.fetchone()

        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            message_count=0,
            latest_message=None,
        )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    db = get_database()
    with db.transaction() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?;", (conversation_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "id": conversation_id}

