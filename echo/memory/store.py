from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, Field
from echo.core.database import Database, get_database


SENSITIVE_KEYWORD_PATTERNS = [
    re.compile(r"(?i)(password|secret|credit_card|cvv|ssn|auth_token|bearer|private_key)"),
]


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: Literal["fact", "project", "preference", "context"]
    key: str
    content: str
    confidence: float = 1.0
    sensitivity: Literal["normal", "high"] = "normal"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MemoryStore:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def add_memory(
        self,
        category: Literal["fact", "project", "preference", "context"],
        key: str,
        content: str,
        confidence: float = 1.0,
        sensitivity: Literal["normal", "high"] = "normal",
    ) -> MemoryEntry:
        for pat in SENSITIVE_KEYWORD_PATTERNS:
            if pat.search(key) or pat.search(content):
                sensitivity = "high"

        now_str = datetime.now(timezone.utc).isoformat()
        entry_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            cur = conn.execute(
                "SELECT id FROM memories WHERE category = ? AND key = ?;",
                (category, key),
            )
            existing = cur.fetchone()
            if existing:
                entry_id = existing["id"]
                conn.execute(
                    """
                    UPDATE memories 
                    SET content = ?, confidence = ?, sensitivity = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (content, confidence, sensitivity, now_str, entry_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO memories (id, category, key, content, confidence, sensitivity, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (entry_id, category, key, content, confidence, sensitivity, now_str, now_str),
                )

            # Sync FTS
            conn.execute("DELETE FROM memories_fts WHERE id = ?;", (entry_id,))
            conn.execute(
                "INSERT INTO memories_fts (id, key, content, category) VALUES (?, ?, ?, ?);",
                (entry_id, key, content, category),
            )

        return MemoryEntry(
            id=entry_id,
            category=category,
            key=key,
            content=content,
            confidence=confidence,
            sensitivity=sensitivity,
            created_at=now_str,
            updated_at=now_str,
        )

    def list_memories(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryEntry]:
        with self.db.get_connection() as conn:
            if query and query.strip():
                clean_q = re.sub(r"[^\w\s]", "", query).strip()
                if clean_q:
                    cur = conn.execute(
                        """
                        SELECT m.* FROM memories m
                        JOIN memories_fts fts ON m.id = fts.id
                        WHERE memories_fts MATCH ?
                        ORDER BY m.updated_at DESC
                        LIMIT ?;
                        """,
                        (f"{clean_q}*", limit),
                    )
                else:
                    cur = conn.execute("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?;", (limit,))
            elif category:
                cur = conn.execute(
                    "SELECT * FROM memories WHERE category = ? ORDER BY updated_at DESC LIMIT ?;",
                    (category, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?;",
                    (limit,),
                )

            rows = cur.fetchall()
            return [
                MemoryEntry(
                    id=row["id"],
                    category=row["category"],
                    key=row["key"],
                    content=row["content"],
                    confidence=row["confidence"],
                    sensitivity=row["sensitivity"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def delete_memory(self, memory_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
            conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory_id,))
            return cur.rowcount > 0

    def get_memory_context(self, query: str = "", limit: int = 5) -> str:
        entries = self.list_memories(query=query if query else None, limit=limit)
        if not entries:
            return ""
        lines = []
        for e in entries:
            if e.sensitivity != "high":
                lines.append(f"• [{e.category.upper()}] {e.key}: {e.content}")
        return "\n".join(lines)


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
