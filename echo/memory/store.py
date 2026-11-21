"""Persistent memory with provenance, task/conversation capture, and FTS5 search."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, Field

from echo.core.database import Database, get_database

MemoryCategory = Literal[
    "fact", "project", "preference", "context", "task", "conversation"
]
Sensitivity = Literal["normal", "high"]

# Credentials and high-risk personal data. Storing these requires an explicit
# permission flag from the user; otherwise the write is refused.
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|passphrase|secret|api[\s_-]?key|private[\s_-]?key|token|bearer|seed[\s_-]?phrase|recovery[\s_-]?code|one[\s_-]?time[\s_-]?code|otp|2fa)\b"),
    re.compile(r"(?i)\b(credit[\s_-]?card|cvv|cvc|social[\s_-]?security|ssn)\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"(?i)\b(diagnosis|medication|prescription|home address|passport number)\b"),
]

REDACTION_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|passphrase|secret|api[\s_-]?key|private[\s_-]?key|token)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{10,})\b"), "[REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED]"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_text(text: str) -> str:
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def is_sensitive_text(text: str) -> bool:
    raw = text or ""
    normalized = re.sub(r"[_\-]+", " ", raw)
    return any(
        pattern.search(raw) or pattern.search(normalized)
        for pattern in SENSITIVE_PATTERNS
    )


def _normalize_tags(tags: Optional[List[str]]) -> List[str]:
    result: List[str] = []
    for tag in tags or []:
        clean = re.sub(r"[^\w\-: ]", "", str(tag)).strip().lower()[:32]
        if clean and clean not in result:
            result.append(clean)
    return result[:12]


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: MemoryCategory
    key: str
    content: str
    confidence: float = 1.0
    sensitivity: Sensitivity = "normal"
    source: str = "user"
    tags: List[str] = Field(default_factory=list)
    pinned: bool = False
    archived: bool = False
    permission_granted: bool = False
    last_used_at: Optional[str] = None
    use_count: int = 0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


def _entry_from_row(row: Any) -> MemoryEntry:
    tags: List[str] = []
    try:
        raw_tags = row["tags"]
        if raw_tags:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                tags = [str(t) for t in parsed]
    except (KeyError, TypeError, ValueError):
        tags = []
    return MemoryEntry(
        id=row["id"],
        category=row["category"],
        key=row["key"],
        content=row["content"],
        confidence=float(row["confidence"] or 1.0),
        sensitivity=row["sensitivity"] or "normal",
        source=row["source"] if "source" in row.keys() else "user",
        tags=tags,
        pinned=bool(row["pinned"]) if "pinned" in row.keys() else False,
        archived=bool(row["archived"]) if "archived" in row.keys() else False,
        permission_granted=bool(row["permission_granted"])
        if "permission_granted" in row.keys()
        else False,
        last_used_at=row["last_used_at"] if "last_used_at" in row.keys() else None,
        use_count=int(row["use_count"] or 0) if "use_count" in row.keys() else 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryStore:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    # ------------------------------------------------------------------ #
    # Write paths
    # ------------------------------------------------------------------ #

    def _evaluate_sensitivity(
        self,
        key: str,
        content: str,
        requested: Sensitivity,
        allow_sensitive: bool,
        existing_grant: bool = False,
    ) -> tuple[Sensitivity, bool]:
        detected = is_sensitive_text(key) or is_sensitive_text(content)
        if requested == "high" or detected:
            if not (allow_sensitive or existing_grant):
                raise ValueError(
                    "This memory looks like a secret or sensitive personal information. "
                    "Confirm explicit permission to store it, or remove the sensitive detail."
                )
            return "high", True
        return "normal", False

    def _sync_fts(
        self,
        conn: Any,
        entry_id: str,
        key: str,
        content: str,
        category: str,
        tags: List[str],
    ) -> None:
        conn.execute("DELETE FROM memories_fts WHERE id = ?;", (entry_id,))
        conn.execute(
            "INSERT INTO memories_fts (id, key, content, category, tags) VALUES (?, ?, ?, ?, ?);",
            (entry_id, key, content, category, " ".join(tags)),
        )

    def add_memory(
        self,
        category: MemoryCategory,
        key: str,
        content: str,
        confidence: float = 1.0,
        sensitivity: Sensitivity = "normal",
        source: str = "user",
        tags: Optional[List[str]] = None,
        pinned: bool = False,
        allow_sensitive: bool = False,
    ) -> MemoryEntry:
        key = key.strip()[:160]
        content = content.strip()[:12000]
        if not key or not content:
            raise ValueError("Memory key and content must not be empty.")
        clean_tags = _normalize_tags(tags)
        now_str = _now()

        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM memories WHERE category = ? AND key = ?;",
                (category, key),
            ).fetchone()

            grant = bool(existing["permission_granted"]) if existing else False
            effective_sensitivity, granted = self._evaluate_sensitivity(
                key, content, sensitivity, allow_sensitive, grant
            )

            if existing:
                entry_id = existing["id"]
                created_at = existing["created_at"]
                merged_tags = sorted(set(_normalize_tags(existing["tags"] and json.loads(existing["tags"])) + clean_tags))
                conn.execute(
                    """
                    UPDATE memories
                    SET content = ?, confidence = ?, sensitivity = ?, source = ?,
                        tags = ?, pinned = ?, permission_granted = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (
                        content,
                        confidence,
                        effective_sensitivity,
                        source,
                        json.dumps(merged_tags),
                        int(pinned),
                        int(granted),
                        now_str,
                        entry_id,
                    ),
                )
                clean_tags = merged_tags
            else:
                entry_id = str(uuid.uuid4())
                created_at = now_str
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, category, key, content, confidence, sensitivity, source,
                        tags, pinned, archived, permission_granted, last_used_at,
                        use_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, 0, ?, ?);
                    """,
                    (
                        entry_id,
                        category,
                        key,
                        content,
                        confidence,
                        effective_sensitivity,
                        source,
                        json.dumps(clean_tags),
                        int(pinned),
                        int(granted),
                        now_str,
                        now_str,
                    ),
                )

            self._sync_fts(conn, entry_id, key, content, category, clean_tags)

        return MemoryEntry(
            id=entry_id,
            category=category,
            key=key,
            content=content,
            confidence=confidence,
            sensitivity=effective_sensitivity,
            source=source,
            tags=clean_tags,
            pinned=pinned,
            permission_granted=granted,
            created_at=created_at,
            updated_at=now_str,
        )

    def update_memory(
        self,
        memory_id: str,
        *,
        category: Optional[MemoryCategory] = None,
        key: Optional[str] = None,
        content: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
        tags: Optional[List[str]] = None,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
        sensitivity: Optional[Sensitivity] = None,
        allow_sensitive: bool = False,
    ) -> MemoryEntry:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,)).fetchone()
            if not row:
                raise KeyError("Memory entry not found")

            existing = _entry_from_row(row)
            new_category = category or existing.category
            new_key = (key or existing.key).strip()[:160]
            new_content = (content or existing.content).strip()[:12000]
            if not new_key or not new_content:
                raise ValueError("Memory key and content must not be empty.")

            effective_sensitivity, granted = self._evaluate_sensitivity(
                new_key,
                new_content,
                sensitivity or existing.sensitivity,
                allow_sensitive,
                existing.permission_granted,
            )
            new_tags = _normalize_tags(tags) if tags is not None else existing.tags
            now_str = _now()
            conn.execute(
                """
                UPDATE memories
                SET category = ?, key = ?, content = ?, confidence = ?, sensitivity = ?,
                    source = ?, tags = ?, pinned = ?, archived = ?, permission_granted = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    new_category,
                    new_key,
                    new_content,
                    confidence if confidence is not None else existing.confidence,
                    effective_sensitivity,
                    source or existing.source,
                    json.dumps(new_tags),
                    int(pinned if pinned is not None else existing.pinned),
                    int(archived if archived is not None else existing.archived),
                    int(granted),
                    now_str,
                    memory_id,
                ),
            )
            self._sync_fts(
                conn, memory_id, new_key, new_content, new_category, new_tags
            )
            created_at = existing.created_at

        return MemoryEntry(
            id=memory_id,
            category=new_category,
            key=new_key,
            content=new_content,
            confidence=confidence if confidence is not None else existing.confidence,
            sensitivity=effective_sensitivity,
            source=source or existing.source,
            tags=new_tags,
            pinned=pinned if pinned is not None else existing.pinned,
            archived=archived if archived is not None else existing.archived,
            permission_granted=granted,
            last_used_at=existing.last_used_at,
            use_count=existing.use_count,
            created_at=created_at,
            updated_at=now_str,
        )

    # ------------------------------------------------------------------ #
    # Read paths
    # ------------------------------------------------------------------ #

    def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,)).fetchone()
        return _entry_from_row(row) if row else None

    def list_memories(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
        source: Optional[str] = None,
        include_archived: bool = False,
        pinned_first: bool = True,
    ) -> List[MemoryEntry]:
        params: List[Any] = []
        clauses: List[str] = []
        if not include_archived:
            clauses.append("m.archived = 0")
        if category:
            clauses.append("m.category = ?")
            params.append(category)
        if source:
            clauses.append("m.source = ?")
            params.append(source)

        order = "m.pinned DESC, m.updated_at DESC" if pinned_first else "m.updated_at DESC"
        sql: str
        if query and query.strip():
            tokens = [t for t in re.sub(r"[^\w\s]", " ", query).split() if t]
            if tokens:
                match = " ".join(f"{token}*" for token in tokens)
                sql = (
                    "SELECT m.* FROM memories m JOIN memories_fts fts ON m.id = fts.id "
                    "WHERE memories_fts MATCH ?"
                )
                params.insert(0, match)
            else:
                sql = "SELECT m.* FROM memories m WHERE 1=1"
        else:
            sql = "SELECT m.* FROM memories m WHERE 1=1"

        if clauses:
            sql += " AND " + " AND ".join(clauses)
        sql += f" ORDER BY {order} LIMIT ?;"
        params.append(limit)

        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_entry_from_row(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories WHERE archived = 0;").fetchone()[0]
            by_category = {
                row["category"]: row["count"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS count FROM memories WHERE archived = 0 GROUP BY category;"
                ).fetchall()
            }
            by_source = {
                row["source"]: row["count"]
                for row in conn.execute(
                    "SELECT source, COUNT(*) AS count FROM memories WHERE archived = 0 GROUP BY source;"
                ).fetchall()
            }
            sensitive = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE archived = 0 AND sensitivity = 'high';"
            ).fetchone()[0]
            pinned = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE archived = 0 AND pinned = 1;"
            ).fetchone()[0]
            latest = conn.execute(
                "SELECT MAX(updated_at) FROM memories WHERE archived = 0;"
            ).fetchone()[0]
        return {
            "total": total,
            "by_category": by_category,
            "by_source": by_source,
            "sensitive": sensitive,
            "pinned": pinned,
            "last_updated_at": latest,
        }

    def export_memories(self) -> Dict[str, Any]:
        entries = self.list_memories(limit=100000, include_archived=True, pinned_first=False)
        return {
            "exported_at": _now(),
            "count": len(entries),
            "memories": [
                {
                    **entry.model_dump(),
                    "tags": entry.tags,
                }
                for entry in entries
            ],
        }

    # ------------------------------------------------------------------ #
    # Deletion / clearing
    # ------------------------------------------------------------------ #

    def delete_memory(self, memory_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
            conn.execute("DELETE FROM memories_fts WHERE id = ?;", (memory_id,))
            return cur.rowcount > 0

    def clear_memories(self, category: Optional[str] = None) -> int:
        with self.db.transaction() as conn:
            if category:
                ids = [
                    row["id"]
                    for row in conn.execute(
                        "SELECT id FROM memories WHERE category = ?;", (category,)
                    ).fetchall()
                ]
                conn.execute("DELETE FROM memories WHERE category = ?;", (category,))
            else:
                ids = [row["id"] for row in conn.execute("SELECT id FROM memories;").fetchall()]
                conn.execute("DELETE FROM memories;")
            for entry_id in ids:
                conn.execute("DELETE FROM memories_fts WHERE id = ?;", (entry_id,))
        return len(ids)

    # ------------------------------------------------------------------ #
    # Context injection
    # ------------------------------------------------------------------ #

    def get_memory_context(self, query: str = "", limit: int = 5) -> str:
        selected: List[MemoryEntry] = []
        seen: set[str] = set()

        def include(entries: List[MemoryEntry]) -> None:
            for entry in entries:
                if entry.id in seen or entry.sensitivity == "high":
                    continue
                selected.append(entry)
                seen.add(entry.id)

        if query and query.strip():
            include(self.list_memories(query=query, limit=limit))
        include([e for e in self.list_memories(limit=limit) if e.pinned])
        if len(selected) < limit:
            include(
                self.list_memories(
                    category="conversation", limit=min(2, limit - len(selected))
                )
            )
        if len(selected) < limit:
            include(self.list_memories(limit=limit - len(selected)))

        if not selected:
            return ""

        for entry in selected:
            try:
                with self.db.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE memories
                        SET last_used_at = ?, use_count = use_count + 1
                        WHERE id = ?;
                        """,
                        (_now(), entry.id),
                    )
            except Exception:
                pass

        lines = []
        for entry in selected:
            stamp = entry.updated_at[:10]
            lines.append(
                f"- [{entry.category.upper()} · {entry.source} · {stamp}] {entry.key}: {entry.content}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Automatic capture
    # ------------------------------------------------------------------ #

    def record_task_memory(
        self,
        task_id: str,
        goal: str,
        status: str,
        error: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        content = f"Goal: {redact_text(goal.strip())[:500]}\nStatus: {status}"
        if error:
            content += f"\nOutcome: {redact_text(str(error))[:500]}"
        try:
            return self.add_memory(
                category="task",
                key=f"task:{task_id}",
                content=content,
                source="task",
                tags=["task", status],
            )
        except ValueError:
            return None

    def record_conversation_summary(
        self,
        conversation_id: str,
        summary: str,
        message_count: int,
        title: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        cleaned = redact_text(summary.strip())[:6000]
        if not cleaned:
            return None
        try:
            return self.add_memory(
                category="conversation",
                key=f"conversation:{conversation_id}",
                content=cleaned,
                source="conversation",
                tags=["conversation", f"messages:{message_count}"]
                + ([f"title:{title[:60]}"] if title else []),
            )
        except ValueError:
            return None

    @staticmethod
    def build_conversation_summary(messages: List[Dict[str, str]], max_messages: int = 8) -> str:
        """Deterministic summary from the tail of a conversation.

        This is intentionally extractive. It never invents facts and survives
        provider outages.
        """
        tail = messages[-max_messages:]
        lines = []
        for message in tail:
            role = "User" if message.get("role") == "user" else "ECHO"
            content = re.sub(r"\s+", " ", redact_text(message.get("content") or "")).strip()
            if content:
                lines.append(f"{role}: {content[:280]}")
        return "\n".join(lines)


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
