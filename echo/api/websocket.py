import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Optional
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from echo.brain.prompts import build_system_prompt
from echo.brain.provider import ChatMessage
from echo.brain.router import get_brain_router
from echo.core.database import get_database
from echo.core.events import Event, get_event_bus
from echo.memory.store import get_memory_store

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger("echo.websocket")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def send_json(self, websocket: WebSocket, data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            pass

    def cancel_task(self, session_or_conv_id: str):
        if session_or_conv_id in self._active_tasks:
            task = self._active_tasks[session_or_conv_id]
            if not task.done():
                task.cancel()
            del self._active_tasks[session_or_conv_id]


manager = ConnectionManager()


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = get_database()
    memory_store = get_memory_store()
    brain_router = get_brain_router()
    event_bus = get_event_bus()

    # Send initial welcome and state frame
    await manager.send_json(
        websocket,
        {
            "type": "connection_established",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
        },
    )

    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                await manager.send_json(websocket, {"type": "error", "message": "Invalid JSON format"})
                continue

            msg_type = data.get("type")

            # 1. Heartbeat Ping
            if msg_type == "ping":
                await manager.send_json(websocket, {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                continue

            # 2. Stop / Cancel generation
            elif msg_type == "stop":
                conv_id = data.get("conversation_id", "default")
                manager.cancel_task(conv_id)
                await manager.send_json(websocket, {"type": "generation_stopped", "conversation_id": conv_id})
                continue

            # 3. Chat Message
            elif msg_type == "chat_message":
                conv_id = data.get("conversation_id")
                content = data.get("content", "").strip()

                if not content:
                    await manager.send_json(websocket, {"type": "error", "message": "Message content cannot be empty"})
                    continue

                now_str = datetime.now(timezone.utc).isoformat()

                # Ensure conversation exists or create one
                with db.transaction() as conn:
                    if not conv_id:
                        conv_id = str(uuid.uuid4())
                        title = content[:30] + ("..." if len(content) > 30 else "")
                        conn.execute(
                            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                            (conv_id, title, now_str, now_str),
                        )
                    else:
                        cur = conn.execute("SELECT id FROM conversations WHERE id = ?;", (conv_id,))
                        if not cur.fetchone():
                            title = content[:30] + ("..." if len(content) > 30 else "")
                            conn.execute(
                                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                                (conv_id, title, now_str, now_str),
                            )
                        else:
                            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?;", (now_str, conv_id))

                    # Persist User Message
                    user_msg_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?);",
                        (user_msg_id, conv_id, content, now_str),
                    )

                # Broadcast user message confirmation
                await manager.send_json(
                    websocket,
                    {
                        "type": "message_received",
                        "conversation_id": conv_id,
                        "message": {
                            "id": user_msg_id,
                            "role": "user",
                            "content": content,
                            "created_at": now_str,
                        },
                    },
                )

                # Prepare context and messages for AI
                with db.get_connection() as conn:
                    cur = conn.execute(
                        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
                        (conv_id,),
                    )
                    db_messages = cur.fetchall()

                # Retrieve relevant memory
                memory_ctx = memory_store.get_memory_context(query=content, limit=5)
                system_prompt = build_system_prompt(memory_context=memory_ctx)

                ai_messages = [ChatMessage(role="system", content=system_prompt)]
                for r in db_messages:
                    ai_messages.append(ChatMessage(role=r["role"], content=r["content"]))

                # Asynchronous streaming runner
                async def run_ai_stream(c_id: str, msgs: List[ChatMessage]):
                    provider = brain_router.get_provider()
                    assistant_msg_id = str(uuid.uuid4())
                    collected_chunks = []
                    start_time_str = datetime.now(timezone.utc).isoformat()

                    # Notify stream starting
                    await manager.send_json(
                        websocket,
                        {
                            "type": "stream_start",
                            "conversation_id": c_id,
                            "message_id": assistant_msg_id,
                            "role": "assistant",
                            "created_at": start_time_str,
                        },
                    )

                    try:
                        async for chunk in provider.stream_chat(msgs):
                            if chunk.error:
                                await manager.send_json(
                                    websocket,
                                    {
                                        "type": "stream_error",
                                        "conversation_id": c_id,
                                        "message_id": assistant_msg_id,
                                        "error": chunk.error,
                                    },
                                )
                                return

                            if chunk.content:
                                collected_chunks.append(chunk.content)
                                await manager.send_json(
                                    websocket,
                                    {
                                        "type": "stream_chunk",
                                        "conversation_id": c_id,
                                        "message_id": assistant_msg_id,
                                        "content": chunk.content,
                                    },
                                )

                        full_reply = "".join(collected_chunks)
                        end_time_str = datetime.now(timezone.utc).isoformat()

                        # Persist assistant reply
                        with db.transaction() as conn:
                            conn.execute(
                                """
                                INSERT INTO messages (id, conversation_id, role, content, token_count, created_at)
                                VALUES (?, ?, 'assistant', ?, ?, ?);
                                """,
                                (assistant_msg_id, c_id, full_reply, len(full_reply.split()), end_time_str),
                            )
                            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?;", (end_time_str, c_id))

                        await manager.send_json(
                            websocket,
                            {
                                "type": "stream_end",
                                "conversation_id": c_id,
                                "message_id": assistant_msg_id,
                                "full_content": full_reply,
                            },
                        )

                    except asyncio.CancelledError:
                        interrupted_reply = "".join(collected_chunks) + " *(Generation cancelled)*"
                        end_time_str = datetime.now(timezone.utc).isoformat()
                        with db.transaction() as conn:
                            conn.execute(
                                """
                                INSERT INTO messages (id, conversation_id, role, content, created_at)
                                VALUES (?, ?, 'assistant', ?, ?);
                                """,
                                (assistant_msg_id, c_id, interrupted_reply, end_time_str),
                            )
                        await manager.send_json(
                            websocket,
                            {
                                "type": "stream_cancelled",
                                "conversation_id": c_id,
                                "message_id": assistant_msg_id,
                                "partial_content": interrupted_reply,
                            },
                        )
                    except Exception as ex:
                        logger.error("Error during AI streaming: %s", ex, exc_info=True)
                        await manager.send_json(
                            websocket,
                            {
                                "type": "stream_error",
                                "conversation_id": c_id,
                                "message_id": assistant_msg_id,
                                "error": f"Internal assistant error: {str(ex)}",
                            },
                        )

                # Spawn streaming task
                stream_task = asyncio.create_task(run_ai_stream(conv_id, ai_messages))
                manager._active_tasks[conv_id] = stream_task

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("WebSocket exception: %s", e)
        manager.disconnect(websocket)

