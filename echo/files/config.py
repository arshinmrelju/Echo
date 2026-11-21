"""File intelligence settings and approved-directory policy."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from echo.core.database import Database, get_database

logger = logging.getLogger("echo.files.config")

SETTINGS_KEY = "file_intelligence_settings"


class FileSettings(BaseModel):
    content_indexing: bool = True
    ocr_enabled: bool = False
    include_hidden: bool = False
    max_file_size_mb: int = Field(default=25, ge=1, le=1024)
    max_hash_size_mb: int = Field(default=512, ge=1, le=4096)
    max_content_chars: int = Field(default=20000, ge=500, le=100000)
    max_index_files: int = Field(default=20000, ge=100, le=200000)
    bulk_confirm_threshold: int = Field(default=5, ge=2, le=500)

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_hash_size_bytes(self) -> int:
        return self.max_hash_size_mb * 1024 * 1024


class FileSettingsStore:
    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db or get_database()

    @property
    def database(self) -> Database:
        return self._db

    def load(self) -> FileSettings:
        try:
            with self._db.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?;", (SETTINGS_KEY,)
                ).fetchone()
            if row and row["value"]:
                return FileSettings(**json.loads(row["value"]))
        except Exception as exc:
            logger.warning("Could not load file settings: %s", exc)
        return FileSettings()

    def save(self, settings: FileSettings) -> FileSettings:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (SETTINGS_KEY, json.dumps(settings.model_dump())),
            )
        return settings
