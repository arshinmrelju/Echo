"""SQLite persistence for the file index, approved roots, and action audit."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
import sqlite3

from echo.core.database import Database, get_database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    for key in ("recursive", "enabled", "pinned"):
        if key in data and data[key] is not None:
            data[key] = bool(data[key])
    if data.get("metadata"):
        try:
            data["metadata"] = json.loads(data["metadata"])
        except (TypeError, ValueError):
            data["metadata"] = {}
    return data


class FileStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    @property
    def database(self) -> Database:
        return self._db

    # ------------------------------------------------------------------ #
    # Approved directories
    # ------------------------------------------------------------------ #

    def list_directories(self) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT d.*, COUNT(f.id) AS file_count
                FROM approved_directories d
                LEFT JOIN file_index f ON f.directory_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at ASC;
                """
            ).fetchall()
        return [_row(row) for row in rows]

    def get_directory(self, directory_id: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT d.*, (
                    SELECT COUNT(*) FROM file_index f WHERE f.directory_id = d.id
                ) AS file_count
                FROM approved_directories d
                WHERE d.id = ?;
                """,
                (directory_id,),
            ).fetchone()
        return _row(row)

    def find_directory_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM approved_directories WHERE path = ?;", (path,)
            ).fetchone()
        return _row(row)

    def add_directory(self, path: str, label: Optional[str], recursive: bool) -> Dict[str, Any]:
        existing = self.find_directory_by_path(path)
        if existing:
            return existing
        directory_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO approved_directories
                    (id, path, label, recursive, enabled, created_at, last_indexed_at)
                VALUES (?, ?, ?, ?, 1, ?, NULL);
                """,
                (directory_id, path, label, int(recursive), _now()),
            )
        return self.get_directory(directory_id) or {}

    def remove_directory(self, directory_id: str) -> bool:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM file_index WHERE directory_id = ?;", (directory_id,))
            cur = conn.execute(
                "DELETE FROM approved_directories WHERE id = ?;", (directory_id,)
            )
            return cur.rowcount > 0

    def touch_directory(self, directory_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE approved_directories SET last_indexed_at = ? WHERE id = ?;",
                (_now(), directory_id),
            )

    # ------------------------------------------------------------------ #
    # File index
    # ------------------------------------------------------------------ #

    def get_file(self, path: str) -> Optional[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            row = conn.execute("SELECT * FROM file_index WHERE path = ?;", (path,)).fetchone()
        return _row(row)

    def upsert_file(self, record: Dict[str, Any]) -> None:
        file_id = record.get("id") or str(uuid.uuid4())
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO file_index (
                    id, directory_id, path, name, extension, category, size_bytes,
                    modified_at, created_at, content_hash, content_text,
                    content_status, metadata, indexed_at, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    directory_id = excluded.directory_id,
                    name = excluded.name,
                    extension = excluded.extension,
                    category = excluded.category,
                    size_bytes = excluded.size_bytes,
                    modified_at = excluded.modified_at,
                    created_at = excluded.created_at,
                    content_hash = excluded.content_hash,
                    content_text = excluded.content_text,
                    content_status = excluded.content_status,
                    metadata = excluded.metadata,
                    indexed_at = excluded.indexed_at,
                    error = excluded.error;
                """,
                (
                    file_id,
                    record["directory_id"],
                    record["path"],
                    record["name"],
                    record.get("extension", ""),
                    record.get("category", "other"),
                    int(record.get("size_bytes") or 0),
                    record.get("modified_at"),
                    record.get("created_at"),
                    record.get("content_hash"),
                    record.get("content_text"),
                    record.get("content_status", "not_indexed"),
                    json.dumps(record.get("metadata") or {}),
                    record.get("indexed_at") or _now(),
                    record.get("error"),
                ),
            )

    def relocate_file(self, old_path: str, new_path: str) -> None:
        from pathlib import Path

        target = Path(new_path)
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE file_index
                SET path = ?, name = ?, extension = ?, modified_at = ?
                WHERE path = ?;
                """,
                (
                    str(target),
                    target.name,
                    target.suffix.lower(),
                    target.stat().st_mtime if target.exists() else None,
                    old_path,
                ),
            )

    def remove_paths(self, paths: Iterable[str]) -> int:
        removed = 0
        with self._db.transaction() as conn:
            for path in paths:
                cur = conn.execute("DELETE FROM file_index WHERE path = ?;", (path,))
                removed += cur.rowcount
        return removed

    def prune_directory(self, directory_id: str, seen_paths: Iterable[str]) -> int:
        seen = set(seen_paths)
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT path FROM file_index WHERE directory_id = ?;", (directory_id,)
            ).fetchall()
        missing = [row["path"] for row in rows if row["path"] not in seen]
        return self.remove_paths(missing)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(
        self,
        *,
        query: Optional[str] = None,
        extension: Optional[str] = None,
        category: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[float] = None,
        modified_before: Optional[float] = None,
        directory_id: Optional[str] = None,
        sort: str = "modified",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        clauses: List[str] = []
        params: List[Any] = []

        tokens = [t for t in (query or "").replace("%", " ").replace("_", " ").split() if t]
        for token in tokens[:8]:
            like = f"%{token.lower()}%"
            clauses.append(
                "(LOWER(name) LIKE ? OR LOWER(path) LIKE ? OR LOWER(COALESCE(content_text, '')) LIKE ?)"
            )
            params.extend([like, like, like])

        if extension:
            ext = extension.lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            clauses.append("extension = ?")
            params.append(ext)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if min_size is not None:
            clauses.append("size_bytes >= ?")
            params.append(min_size)
        if max_size is not None:
            clauses.append("size_bytes <= ?")
            params.append(max_size)
        if modified_after is not None:
            clauses.append("modified_at >= ?")
            params.append(modified_after)
        if modified_before is not None:
            clauses.append("modified_at <= ?")
            params.append(modified_before)
        if directory_id:
            clauses.append("directory_id = ?")
            params.append(directory_id)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order = {
            "name": "name COLLATE NOCASE ASC",
            "size": "size_bytes DESC",
            "oldest": "modified_at ASC",
            "modified": "modified_at DESC",
        }.get(sort, "modified_at DESC")

        with self._db.get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM file_index{where};", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM file_index{where} ORDER BY {order} LIMIT ? OFFSET ?;",
                [*params, limit, offset],
            ).fetchall()

        results = []
        for row in rows:
            item = _row(row)
            item.pop("content_text", None)
            if tokens and item.get("path"):
                snippet = self._snippet(row["content_text"], tokens)
                if snippet:
                    item["snippet"] = snippet
            results.append(item)
        return {"results": results, "count": len(results), "total": total, "limit": limit, "offset": offset}

    @staticmethod
    def _snippet(text: Optional[str], tokens: List[str], radius: int = 90) -> Optional[str]:
        if not text:
            return None
        lowered = text.lower()
        for token in tokens:
            index = lowered.find(token.lower())
            if index >= 0:
                start = max(0, index - radius)
                end = min(len(text), index + len(token) + radius)
                prefix = "…" if start > 0 else ""
                suffix = "…" if end < len(text) else ""
                return prefix + text[start:end].replace("\n", " ").strip() + suffix
        return None

    def stats(self) -> Dict[str, Any]:
        with self._db.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM file_index;").fetchone()[0]
            total_bytes = conn.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM file_index;"
            ).fetchone()[0]
            by_category = [
                {"category": row["category"], "count": row["count"], "bytes": row["bytes"]}
                for row in conn.execute(
                    """
                    SELECT category, COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS bytes
                    FROM file_index GROUP BY category ORDER BY bytes DESC;
                    """
                ).fetchall()
            ]
            largest = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT path, name, size_bytes, modified_at, category
                    FROM file_index ORDER BY size_bytes DESC LIMIT 8;
                    """
                ).fetchall()
            ]
            last_indexed = conn.execute("SELECT MAX(indexed_at) FROM file_index;").fetchone()[0]
            duplicate_count = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT content_hash FROM file_index
                    WHERE content_hash IS NOT NULL AND size_bytes > 0
                    GROUP BY content_hash, size_bytes HAVING COUNT(*) > 1
                );
                """
            ).fetchone()[0]
            duplicate_bytes = conn.execute(
                """
                SELECT COALESCE(SUM((cnt - 1) * size_bytes), 0) FROM (
                    SELECT content_hash, size_bytes, COUNT(*) AS cnt
                    FROM file_index
                    WHERE content_hash IS NOT NULL AND size_bytes > 0
                    GROUP BY content_hash, size_bytes HAVING COUNT(*) > 1
                );
                """
            ).fetchone()[0]
        return {
            "total_files": total,
            "total_bytes": total_bytes,
            "by_category": by_category,
            "largest": largest,
            "last_indexed_at": last_indexed,
            "duplicate_groups": duplicate_count,
            "duplicate_wasted_bytes": duplicate_bytes,
        }

    def duplicate_groups(
        self, min_size: int = 1, directory_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        clauses = ["content_hash IS NOT NULL", "size_bytes >= ?"]
        params: List[Any] = [min_size]
        if directory_id:
            clauses.append("directory_id = ?")
            params.append(directory_id)
        where = " AND ".join(clauses)
        with self._db.get_connection() as conn:
            groups = conn.execute(
                f"""
                SELECT content_hash, size_bytes, COUNT(*) AS count
                FROM file_index WHERE {where}
                GROUP BY content_hash, size_bytes
                HAVING COUNT(*) > 1
                ORDER BY (COUNT(*) - 1) * size_bytes DESC
                LIMIT ?;
                """,
                [*params, limit],
            ).fetchall()
            result = []
            for group in groups:
                files = conn.execute(
                    "SELECT id, path, name, extension, category, size_bytes, modified_at "
                    "FROM file_index WHERE content_hash = ? AND size_bytes = ? ORDER BY modified_at ASC;",
                    (group["content_hash"], group["size_bytes"]),
                ).fetchall()
                result.append(
                    {
                        "content_hash": group["content_hash"],
                        "size_bytes": group["size_bytes"],
                        "count": group["count"],
                        "files": [dict(row) for row in files],
                    }
                )
        return result

    def large_files(self, min_size: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, path, name, extension, category, size_bytes, modified_at
                FROM file_index WHERE size_bytes >= ?
                ORDER BY size_bytes DESC LIMIT ?;
                """,
                (min_size, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Action audit
    # ------------------------------------------------------------------ #

    def log_action(
        self,
        action: str,
        *,
        status: str,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO file_actions
                    (id, action, source_path, target_path, status, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    action,
                    source_path,
                    target_path,
                    status,
                    json.dumps(details or {}),
                    _now(),
                ),
            )

    def list_actions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM file_actions ORDER BY created_at DESC LIMIT ?;", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item["details"]) if item["details"] else {}
            except (TypeError, ValueError):
                item["details"] = {}
            result.append(item)
        return result
