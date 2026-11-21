"""Shared conversation turn pipeline used by text chat and voice.

Both the WebSocket chat gateway and the voice subsystem run through this
service so a spoken turn is persisted, streamed to the UI, and rendered
exactly like a typed turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from echo.brain.prompts import build_system_prompt
from echo.brain.provider import ChatMessage
from echo.brain.router import get_brain_router
from echo.core.database import get_database
from echo.memory.store import get_memory_store

logger = logging.getLogger("echo.chat_service")

EventEmitter = Callable[[Dict[str, Any]], Awaitable[None]]
ChunkListener = Callable[[str], None]


@dataclass
class TurnResult:
    conversation_id: str
    message_id: Optional[str]
    content: str
    cancelled: bool = False
    error: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatTurnService:
    """Persists and streams a single assistant turn.

    ``start_turn`` returns immediately with a task so transports can keep
    reading frames and call ``cancel`` for a given task key.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}

    def is_running(self, task_key: str) -> bool:
        task = self._tasks.get(task_key)
        return bool(task and not task.done())

    def cancel(self, task_key: str) -> bool:
        task = self._tasks.get(task_key)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def start_turn(
        self,
        *,
        conversation_id: Optional[str],
        content: str,
        emit: EventEmitter,
        source: str = "text",
        voice_mode: bool = False,
        on_chunk: Optional[ChunkListener] = None,
        task_key: Optional[str] = None,
    ) -> asyncio.Task:
        """Schedule a turn and return its task. The previous task for the same key is cancelled."""
        key = task_key or conversation_id or f"anon:{uuid.uuid4()}"
        self.cancel(key)
        task = asyncio.create_task(
            self._run_turn(
                conversation_id=conversation_id,
                content=content,
                emit=emit,
                source=source,
                voice_mode=voice_mode,
                on_chunk=on_chunk,
                task_key=key,
            )
        )
        self._tasks[key] = task

        def _cleanup(done: asyncio.Task) -> None:
            if self._tasks.get(key) is done:
                self._tasks.pop(key, None)
            # Surface unexpected exceptions instead of letting them vanish.
            if not done.cancelled():
                exc = done.exception()
                if exc:
                    logger.error("Chat turn failed: %s", exc, exc_info=exc)

        task.add_done_callback(_cleanup)
        return task

    async def run_turn(
        self,
        *,
        conversation_id: Optional[str],
        content: str,
        emit: EventEmitter,
        source: str = "text",
        voice_mode: bool = False,
        on_chunk: Optional[ChunkListener] = None,
        task_key: Optional[str] = None,
    ) -> TurnResult:
        """Awaitable form used by voice, where the caller needs the reply text."""
        key = task_key or conversation_id or f"anon:{uuid.uuid4()}"
        self.cancel(key)
        return await self._run_turn(
            conversation_id=conversation_id,
            content=content,
            emit=emit,
            source=source,
            voice_mode=voice_mode,
            on_chunk=on_chunk,
            task_key=key,
        )

    @staticmethod
    def _capture_conversation_memory(db, memory_store, conversation_id: str) -> None:
        """Store a deterministic, extractive summary after a completed turn."""
        try:
            with db.get_connection() as conn:
                rows = conn.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
                    (conversation_id,),
                ).fetchall()
                title_row = conn.execute(
                    "SELECT title FROM conversations WHERE id = ?;", (conversation_id,)
                ).fetchone()
            messages = [{"role": row["role"], "content": row["content"]} for row in rows]
            summary = memory_store.build_conversation_summary(messages)
            if summary:
                memory_store.record_conversation_summary(
                    conversation_id,
                    summary,
                    message_count=len(messages),
                    title=title_row["title"] if title_row else None,
                )
        except Exception as exc:
            logger.debug("Conversation memory capture failed: %s", exc)

    async def _run_turn(
        self,
        *,
        conversation_id: Optional[str],
        content: str,
        emit: EventEmitter,
        source: str,
        voice_mode: bool,
        on_chunk: Optional[ChunkListener],
        task_key: str,
    ) -> TurnResult:
        db = get_database()
        memory_store = get_memory_store()
        brain_router = get_brain_router()

        async def safe_emit(payload: Dict[str, Any]) -> None:
            try:
                await emit(payload)
            except Exception as exc:  # a dead UI must not break the turn
                logger.debug("Chat event emit failed: %s", exc)

        now_str = _now()
        conv_id = conversation_id
        user_msg_id = str(uuid.uuid4())
        title = content[:30] + ("..." if len(content) > 30 else "")
        metadata = json.dumps({"source": source})

        with db.transaction() as conn:
            if not conv_id:
                conv_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                    (conv_id, title, now_str, now_str),
                )
            else:
                cur = conn.execute("SELECT id FROM conversations WHERE id = ?;", (conv_id,))
                if not cur.fetchone():
                    conn.execute(
                        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                        (conv_id, title, now_str, now_str),
                    )
                else:
                    conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?;", (now_str, conv_id)
                    )

            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
                VALUES (?, ?, 'user', ?, ?, ?);
                """,
                (user_msg_id, conv_id, content, now_str, metadata),
            )

        await safe_emit(
            {
                "type": "message_received",
                "conversation_id": conv_id,
                "source": source,
                "message": {
                    "id": user_msg_id,
                    "conversation_id": conv_id,
                    "role": "user",
                    "content": content,
                    "created_at": now_str,
                    "metadata": {"source": source},
                },
            }
        )

        with db.get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
                (conv_id,),
            )
            db_messages = cur.fetchall()

        memory_ctx = memory_store.get_memory_context(query=content, limit=5)
        system_prompt = build_system_prompt(memory_context=memory_ctx, voice_mode=voice_mode)

        ai_messages = [ChatMessage(role="system", content=system_prompt)]
        for row in db_messages:
            ai_messages.append(ChatMessage(role=row["role"], content=row["content"]))

        provider = brain_router.get_provider()
        assistant_msg_id = str(uuid.uuid4())
        collected_chunks: List[str] = []
        start_time_str = _now()

        await safe_emit(
            {
                "type": "stream_start",
                "conversation_id": conv_id,
                "message_id": assistant_msg_id,
                "role": "assistant",
                "source": source,
                "created_at": start_time_str,
            }
        )

        try:
            async for chunk in provider.stream_chat(ai_messages):
                if chunk.error:
                    await safe_emit(
                        {
                            "type": "stream_error",
                            "conversation_id": conv_id,
                            "message_id": assistant_msg_id,
                            "source": source,
                            "error": chunk.error,
                        }
                    )
                    return TurnResult(
                        conversation_id=conv_id,
                        message_id=assistant_msg_id,
                        content="".join(collected_chunks),
                        error=chunk.error,
                    )

                if not chunk.content:
                    continue

                collected_chunks.append(chunk.content)
                if on_chunk:
                    try:
                        on_chunk(chunk.content)
                    except Exception as exc:
                        logger.warning("Stream listener failed: %s", exc)
                await safe_emit(
                    {
                        "type": "stream_chunk",
                        "conversation_id": conv_id,
                        "message_id": assistant_msg_id,
                        "source": source,
                        "content": chunk.content,
                    }
                )

            full_reply = "".join(collected_chunks)
            end_time_str = _now()

            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, token_count, created_at, metadata)
                    VALUES (?, ?, 'assistant', ?, ?, ?, ?);
                    """,
                    (
                        assistant_msg_id,
                        conv_id,
                        full_reply,
                        len(full_reply.split()),
                        end_time_str,
                        metadata,
                    ),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?;", (end_time_str, conv_id)
                )

            await safe_emit(
                {
                    "type": "stream_end",
                    "conversation_id": conv_id,
                    "message_id": assistant_msg_id,
                    "source": source,
                    "full_content": full_reply,
                }
            )
            self._capture_conversation_memory(db, memory_store, conv_id)
            return TurnResult(
                conversation_id=conv_id, message_id=assistant_msg_id, content=full_reply
            )

        except asyncio.CancelledError:
            partial = "".join(collected_chunks)
            end_time_str = _now()
            persisted_partial = partial + (" *[interrupted]*" if partial else "")
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
                    VALUES (?, ?, 'assistant', ?, ?, ?);
                    """,
                    (assistant_msg_id, conv_id, persisted_partial, end_time_str, metadata),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?;", (end_time_str, conv_id)
                )
            await safe_emit(
                {
                    "type": "stream_cancelled",
                    "conversation_id": conv_id,
                    "message_id": assistant_msg_id,
                    "source": source,
                    "partial_content": persisted_partial,
                }
            )
            self._capture_conversation_memory(db, memory_store, conv_id)
            return TurnResult(
                conversation_id=conv_id,
                message_id=assistant_msg_id,
                content=partial,
                cancelled=True,
            )

        except Exception as exc:
            logger.error("Error during AI streaming: %s", exc, exc_info=True)
            await safe_emit(
                {
                    "type": "stream_error",
                    "conversation_id": conv_id,
                    "message_id": assistant_msg_id,
                    "source": source,
                    "error": f"Internal assistant error: {exc}",
                }
            )
            return TurnResult(
                conversation_id=conv_id,
                message_id=assistant_msg_id,
                content="".join(collected_chunks),
                error=str(exc),
            )


_service: Optional[ChatTurnService] = None


def get_chat_turn_service() -> ChatTurnService:
    global _service
    if _service is None:
        _service = ChatTurnService()
    return _service
