"""Approved-directory file indexing, search, and safe file actions."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from echo.brain.provider import ChatMessage
from echo.brain.router import get_brain_router
from echo.files.config import FileSettings, FileSettingsStore
from echo.files.extractors import (
    SKIP_DIR_NAMES,
    capabilities,
    category_for,
    compute_hash,
    extract_text,
    should_skip,
)
from echo.files.store import FileStore
from echo.tools.security import RESTRICTED_EXECUTABLE_EXTENSIONS, is_path_safe, validate_path

logger = logging.getLogger("echo.files")

CATEGORY_FOLDERS = {
    "document": "Documents",
    "spreadsheet": "Spreadsheets",
    "presentation": "Presentations",
    "image": "Images",
    "audio": "Audio",
    "video": "Video",
    "code": "Code",
    "archive": "Archives",
    "executable": "Executables",
    "other": "Other",
}

BLOCKED_OPEN_EXTENSIONS = set(RESTRICTED_EXECUTABLE_EXTENSIONS) | {
    ".exe", ".msi", ".com", ".dll", ".scr", ".lnk", ".url", ".sys",
}


class FileIntelligenceError(Exception):
    status_code = 400


class PathNotApproved(FileIntelligenceError):
    status_code = 403


class ConfirmationRequired(FileIntelligenceError):
    status_code = 409

    def __init__(self, message: str, plan: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.plan = plan or {}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        return path == parent or parent in path.parents
    except OSError:
        return False


def parse_timestamp(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class FileIntelligenceService:
    def __init__(self, db=None) -> None:
        self.store = FileStore(db=db)
        self.settings_store = FileSettingsStore(db=self.store.database)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Paths and directories
    # ------------------------------------------------------------------ #

    def approved_roots(self) -> List[Path]:
        return [
            Path(directory["path"])
            for directory in self.store.list_directories()
            if directory.get("enabled", True)
        ]

    def require_approved(self, path: Path | str, must_exist: bool = True) -> Path:
        resolved = Path(path).expanduser().resolve(strict=False)
        safe, reason = is_path_safe(resolved)
        if not safe:
            raise PathNotApproved(reason)
        roots = self.approved_roots()
        if not roots:
            raise PathNotApproved("No approved directories. Add a directory in File Intelligence first.")
        if not any(_is_within(resolved, root) for root in roots):
            raise PathNotApproved(
                f"'{resolved}' is outside the approved directories. Add its parent directory first."
            )
        if must_exist and not resolved.exists():
            raise FileIntelligenceError(f"Path does not exist: '{resolved}'")
        return resolved

    def add_directory(
        self, path: str, label: Optional[str] = None, recursive: bool = True
    ) -> Dict[str, Any]:
        resolved = validate_path(path, must_exist=True)
        if not resolved.is_dir():
            raise FileIntelligenceError(f"Not a directory: '{resolved}'")
        safe, reason = is_path_safe(resolved)
        if not safe:
            raise PathNotApproved(reason)
        if resolved.parent == resolved:
            raise PathNotApproved("A drive root cannot be approved. Choose a folder instead.")
        directory = self.store.add_directory(str(resolved), label, recursive)
        self.store.log_action(
            "directory.add",
            status="ok",
            target_path=str(resolved),
            details={"directory_id": directory.get("id"), "recursive": recursive},
        )
        return directory

    def remove_directory(self, directory_id: str) -> bool:
        directory = self.store.get_directory(directory_id)
        if not directory:
            return False
        removed = self.store.remove_directory(directory_id)
        self.store.log_action(
            "directory.remove",
            status="ok" if removed else "missing",
            target_path=directory["path"],
            details={"directory_id": directory_id},
        )
        return removed

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    def _index_single(self, path: Path, directory_id: str, settings: FileSettings, force: bool = False) -> Dict[str, Any]:
        stat = path.stat()
        existing = self.store.get_file(str(path))
        if (
            existing
            and not force
            and existing.get("size_bytes") == stat.st_size
            and abs(float(existing.get("modified_at") or 0) - stat.st_mtime) < 1
            and existing.get("content_status") not in ("error", "not_indexed")
        ):
            return {"status": "unchanged", "path": str(path)}

        extraction: Dict[str, Any] = {
            "text": "",
            "status": "not_indexed",
            "extractor": "none",
            "metadata": {},
        }
        if settings.content_indexing and stat.st_size <= settings.max_file_size_bytes:
            extraction = extract_text(
                path,
                max_chars=settings.max_content_chars,
                ocr_enabled=settings.ocr_enabled,
            )
        elif stat.st_size > settings.max_file_size_bytes:
            extraction["status"] = "skipped_size"

        metadata = extraction.get("metadata") or {}
        metadata["extractor"] = extraction.get("extractor")
        if extraction.get("error"):
            metadata["error"] = extraction["error"]

        self.store.upsert_file(
            {
                "directory_id": directory_id,
                "path": str(path),
                "name": path.name,
                "extension": path.suffix.lower(),
                "category": category_for(path),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "created_at": datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(),
                "content_hash": compute_hash(path, settings.max_hash_size_bytes),
                "content_text": extraction.get("text") or None,
                "content_status": extraction.get("status") or "not_indexed",
                "metadata": metadata,
                "indexed_at": _now(),
                "error": extraction.get("error"),
            }
        )
        return {"status": "indexed", "path": str(path), "content_status": extraction.get("status")}

    def index_directory(self, directory_id: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        settings = self.settings_store.load()
        if directory_id:
            directory = self.store.get_directory(directory_id)
            if not directory:
                raise FileIntelligenceError("Approved directory not found")
            directories = [directory]
        else:
            directories = [d for d in self.store.list_directories() if d.get("enabled", True)]

        if not directories:
            raise FileIntelligenceError("No approved directories to index.")

        started = time.time()
        totals = {
            "files_seen": 0,
            "indexed": 0,
            "unchanged": 0,
            "skipped": 0,
            "errors": 0,
            "removed": 0,
            "truncated": False,
            "directories": [],
        }

        for directory in directories:
            root = Path(directory["path"])
            if not root.exists():
                totals["errors"] += 1
                totals["directories"].append(
                    {"directory_id": directory["id"], "path": str(root), "error": "missing"}
                )
                self.store.log_action(
                    "index", status="error", target_path=str(root), details={"error": "missing"}
                )
                continue

            seen: set[str] = set()
            seen_count = 0
            indexed = 0
            unchanged = 0
            skipped = 0
            errors = 0
            truncated = False

            for current, dirs, files in os.walk(root):
                if not directory.get("recursive", True):
                    dirs[:] = []
                else:
                    dirs[:] = [
                        d
                        for d in dirs
                        if d.lower() not in SKIP_DIR_NAMES
                        and (settings.include_hidden or not d.startswith("."))
                    ]

                for name in files:
                    path = Path(current) / name
                    if not settings.include_hidden and name.startswith("."):
                        skipped += 1
                        continue
                    reason = should_skip(path)
                    if reason:
                        skipped += 1
                        continue
                    try:
                        result = self._index_single(path, directory["id"], settings, force=force)
                    except Exception as exc:
                        errors += 1
                        logger.debug("Indexing failed for %s: %s", path, exc)
                        continue
                    seen.add(result["path"])
                    seen_count += 1
                    if result["status"] == "indexed":
                        indexed += 1
                    else:
                        unchanged += 1
                    if seen_count >= settings.max_index_files:
                        truncated = True
                        break
                if truncated:
                    break

            removed = 0
            if not truncated:
                removed = self.store.prune_directory(directory["id"], seen)
            self.store.touch_directory(directory["id"])
            self.store.log_action(
                "index",
                status="ok",
                target_path=str(root),
                details={
                    "indexed": indexed,
                    "unchanged": unchanged,
                    "skipped": skipped,
                    "errors": errors,
                    "removed": removed,
                    "truncated": truncated,
                },
            )

            totals["files_seen"] += seen_count
            totals["indexed"] += indexed
            totals["unchanged"] += unchanged
            totals["skipped"] += skipped
            totals["errors"] += errors
            totals["removed"] += removed
            totals["truncated"] = totals["truncated"] or truncated
            totals["directories"].append(
                {
                    "directory_id": directory["id"],
                    "path": str(root),
                    "files_seen": seen_count,
                    "indexed": indexed,
                    "unchanged": unchanged,
                    "skipped": skipped,
                    "errors": errors,
                    "removed": removed,
                    "truncated": truncated,
                }
            )

        totals["duration_ms"] = round((time.time() - started) * 1000, 1)
        return totals

    def _directory_for_path(self, path: Path) -> Optional[Dict[str, Any]]:
        for directory in self.store.list_directories():
            if _is_within(path, Path(directory["path"])):
                return directory
        return None

    def _index_after_action(self, path: Path) -> None:
        directory = self._directory_for_path(path)
        if not directory or not path.exists():
            return
        try:
            self._index_single(path, directory["id"], self.settings_store.load(), force=True)
        except Exception as exc:
            logger.debug("Post-action indexing failed for %s: %s", path, exc)

    # ------------------------------------------------------------------ #
    # Search and read models
    # ------------------------------------------------------------------ #

    def search(self, **filters: Any) -> Dict[str, Any]:
        return self.store.search(**filters)

    def stats(self) -> Dict[str, Any]:
        settings = self.settings_store.load()
        return {
            **self.store.stats(),
            "directories": self.store.list_directories(),
            "settings": settings.model_dump(),
            "capabilities": capabilities(),
        }

    def update_settings(self, updates: Dict[str, Any]) -> FileSettings:
        current = self.settings_store.load()
        merged = current.model_dump()
        for key, value in updates.items():
            if value is not None and key in merged:
                merged[key] = value
        return self.settings_store.save(FileSettings(**merged))

    def details(self, path: str) -> Dict[str, Any]:
        resolved = self.require_approved(path)
        if not resolved.is_file():
            raise FileIntelligenceError(f"Not a file: '{resolved}'")
        row = self.store.get_file(str(resolved))
        stat = resolved.stat()
        if not row:
            return {
                "path": str(resolved),
                "name": resolved.name,
                "extension": resolved.suffix.lower(),
                "category": category_for(resolved),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "indexed": False,
                "content_status": "not_indexed",
                "metadata": {},
                "preview": None,
            }
        row.pop("content_text", None)
        preview = None
        with self.store.database.get_connection() as conn:
            content = conn.execute(
                "SELECT content_text FROM file_index WHERE path = ?;", (str(resolved),)
            ).fetchone()
        if content and content["content_text"]:
            preview = content["content_text"][:4000]
        return {**row, "indexed": True, "preview": preview}

    def list_categories(self) -> List[Dict[str, Any]]:
        return self.store.stats().get("by_category", [])

    # ------------------------------------------------------------------ #
    # File actions
    # ------------------------------------------------------------------ #

    def open_file(self, path: str) -> Dict[str, Any]:
        resolved = self.require_approved(path)
        if not resolved.is_file():
            raise FileIntelligenceError(f"Not a file: '{resolved}'")
        if resolved.suffix.lower() in BLOCKED_OPEN_EXTENSIONS:
            self.store.log_action("open", status="blocked", source_path=str(resolved))
            raise FileIntelligenceError(
                f"ECHO will not launch executable or shortcut files: '{resolved.name}'"
            )
        try:
            os.startfile(str(resolved))  # type: ignore[attr-defined]
        except OSError as exc:
            self.store.log_action(
                "open", status="error", source_path=str(resolved), details={"error": str(exc)}
            )
            raise FileIntelligenceError(f"Could not open file: {exc}") from exc
        self.store.log_action("open", status="ok", source_path=str(resolved))
        return {"success": True, "path": str(resolved)}

    def rename(self, path: str, new_name: str, confirm: bool = False) -> Dict[str, Any]:
        source = self.require_approved(path)
        if not source.is_file():
            raise FileIntelligenceError(f"Not a file: '{source}'")
        clean = new_name.strip()
        if not clean or clean in (".", "..") or any(sep in clean for sep in ("/", "\\")):
            raise FileIntelligenceError("new_name must be a file name, not a path.")
        target = source.parent / clean
        self.require_approved(target.parent)
        overwritten = False
        if target.exists() and target != source:
            if not confirm:
                raise ConfirmationRequired(
                    f"'{target.name}' already exists. Confirm overwrite to continue.",
                    {"target": str(target)},
                )
            os.replace(str(source), str(target))
            overwritten = True
        else:
            source.rename(target)
        self.store.relocate_file(str(source), str(target))
        self._index_after_action(target)
        self.store.log_action(
            "rename",
            status="ok",
            source_path=str(source),
            target_path=str(target),
            details={"overwrite": overwritten},
        )
        return {"success": True, "old_path": str(source), "new_path": str(target)}

    def copy(self, path: str, destination: str, confirm: bool = False) -> Dict[str, Any]:
        source = self.require_approved(path)
        if not source.is_file():
            raise FileIntelligenceError(f"Not a file: '{source}'")
        dest = Path(destination).expanduser().resolve(strict=False)
        if dest.is_dir():
            dest = dest / source.name
        self.require_approved(dest.parent)
        if dest.exists() and not confirm:
            raise ConfirmationRequired(
                f"'{dest.name}' already exists at the destination. Confirm overwrite.",
                {"target": str(dest)},
            )
        shutil.copy2(str(source), str(dest))
        self._index_after_action(dest)
        self.store.log_action(
            "copy",
            status="ok",
            source_path=str(source),
            target_path=str(dest),
            details={"overwrite": confirm},
        )
        return {"success": True, "source": str(source), "destination": str(dest)}

    def move(self, path: str, destination: str, confirm: bool = False) -> Dict[str, Any]:
        source = self.require_approved(path)
        if not source.is_file():
            raise FileIntelligenceError(f"Not a file: '{source}'")
        dest = Path(destination).expanduser().resolve(strict=False)
        if dest.is_dir():
            dest = dest / source.name
        self.require_approved(dest.parent)
        if dest.exists() and not confirm:
            raise ConfirmationRequired(
                f"'{dest.name}' already exists at the destination. Confirm overwrite.",
                {"target": str(dest)},
            )
        if dest.exists():
            os.replace(str(source), str(dest))
        else:
            shutil.move(str(source), str(dest))
        self.store.remove_paths([str(source)])
        self._index_after_action(dest)
        self.store.log_action(
            "move",
            status="ok",
            source_path=str(source),
            target_path=str(dest),
            details={"overwrite": confirm},
        )
        return {"success": True, "source": str(source), "destination": str(dest)}

    def _top_level_files(self, directory: Path) -> List[Path]:
        files = []
        for entry in directory.iterdir():
            if entry.is_dir() or entry.is_symlink():
                continue
            if should_skip(entry):
                continue
            if entry.name.startswith("."):
                continue
            files.append(entry)
        return sorted(files, key=lambda p: p.name.lower())

    def organize(
        self,
        directory: str,
        destination_root: Optional[str] = None,
        confirm: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        source = self.require_approved(directory)
        if not source.is_dir():
            raise FileIntelligenceError(f"Not a directory: '{source}'")
        root = (
            self.require_approved(destination_root)
            if destination_root
            else source
        )
        if not root.is_dir():
            raise FileIntelligenceError(f"Destination is not a directory: '{root}'")

        settings = self.settings_store.load()
        plan = []
        for file_path in self._top_level_files(source):
            folder = CATEGORY_FOLDERS.get(category_for(file_path), "Other")
            target = root / folder / file_path.name
            if target == file_path or target.exists():
                continue
            plan.append(
                {
                    "source": str(file_path),
                    "target": str(target),
                    "category": category_for(file_path),
                    "folder": folder,
                }
            )

        result = {
            "directory": str(source),
            "destination_root": str(root),
            "planned": len(plan),
            "plan": plan[:500],
            "threshold": settings.bulk_confirm_threshold,
            "dry_run": dry_run,
        }
        if dry_run:
            return result
        if len(plan) > settings.bulk_confirm_threshold and not confirm:
            raise ConfirmationRequired(
                f"Organizing {len(plan)} files exceeds the bulk threshold "
                f"({settings.bulk_confirm_threshold}). Confirm to continue.",
                result,
            )

        moved = 0
        skipped = 0
        for item in plan:
            target = Path(item["target"])
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(item["source"], str(target))
                self.store.remove_paths([item["source"]])
                self._index_after_action(target)
                moved += 1
            except OSError as exc:
                skipped += 1
                logger.debug("Organize move failed: %s", exc)
        result.update({"moved": moved, "skipped": skipped})
        self.store.log_action(
            "organize",
            status="ok",
            target_path=str(root),
            details={"moved": moved, "skipped": skipped, "planned": len(plan)},
        )
        return result

    def bulk_rename(
        self,
        directory: str,
        find: str,
        replace: str,
        confirm: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        source = self.require_approved(directory)
        if not source.is_dir():
            raise FileIntelligenceError(f"Not a directory: '{source}'")
        if not find:
            raise FileIntelligenceError("Find text must not be empty.")
        if any(sep in replace for sep in ("/", "\\")):
            raise FileIntelligenceError("Replacement must not contain path separators.")

        settings = self.settings_store.load()
        pattern = re.compile(re.escape(find), re.IGNORECASE)
        plan = []
        for file_path in self._top_level_files(source):
            new_name = pattern.sub(replace, file_path.name)
            if new_name == file_path.name or not new_name.strip():
                continue
            target = file_path.parent / new_name
            if target.exists():
                continue
            plan.append({"source": str(file_path), "target": str(target)})

        result = {
            "directory": str(source),
            "planned": len(plan),
            "plan": plan[:500],
            "threshold": settings.bulk_confirm_threshold,
            "dry_run": dry_run,
        }
        if dry_run:
            return result
        if len(plan) > 1 and not confirm:
            raise ConfirmationRequired(
                f"Renaming {len(plan)} files requires confirmation.",
                result,
            )

        renamed = 0
        skipped = 0
        for item in plan:
            try:
                Path(item["source"]).rename(item["target"])
                self.store.relocate_file(item["source"], item["target"])
                renamed += 1
            except OSError:
                skipped += 1
        result.update({"renamed": renamed, "skipped": skipped})
        self.store.log_action(
            "bulk_rename",
            status="ok",
            target_path=str(source),
            details={"renamed": renamed, "skipped": skipped, "find": find, "replace": replace},
        )
        return result

    def quarantine_duplicates(
        self,
        directory: Optional[str] = None,
        confirm: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        directory_row = None
        if directory:
            resolved = self.require_approved(directory)
            if not resolved.is_dir():
                raise FileIntelligenceError(f"Not a directory: '{resolved}'")
            directory_row = next(
                (
                    d
                    for d in self.store.list_directories()
                    if Path(d["path"]) == resolved
                ),
                None,
            )
            if directory_row is None:
                raise PathNotApproved("Duplicate quarantine requires an approved root directory.")

        groups = self.store.duplicate_groups(
            directory_id=directory_row["id"] if directory_row else None
        )
        plan = []
        for group in groups:
            files = group["files"]
            if len(files) < 2:
                continue
            keeper = files[0]
            keeper_path = Path(keeper["path"])
            quarantine_dir = keeper_path.parent / "_ECHO_DUPLICATES" / group["content_hash"][:12]
            for duplicate in files[1:]:
                target = quarantine_dir / Path(duplicate["path"]).name
                counter = 1
                while target.exists():
                    target = quarantine_dir / f"{Path(duplicate['path']).stem}_{counter}{Path(duplicate['path']).suffix}"
                    counter += 1
                plan.append(
                    {
                        "source": duplicate["path"],
                        "target": str(target),
                        "kept": keeper["path"],
                        "content_hash": group["content_hash"],
                        "size_bytes": group["size_bytes"],
                    }
                )

        result = {"planned": len(plan), "plan": plan[:500], "dry_run": dry_run}
        if dry_run:
            return result
        if not plan:
            return {**result, "moved": 0, "skipped": 0}
        if not confirm:
            raise ConfirmationRequired(
                f"Quarantining {len(plan)} duplicate files requires confirmation. "
                "Files are moved, never deleted.",
                result,
            )

        moved = 0
        skipped = 0
        for item in plan:
            try:
                target = Path(item["target"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(item["source"], str(target))
                self.store.relocate_file(item["source"], str(target))
                moved += 1
            except OSError:
                skipped += 1
        result.update({"moved": moved, "skipped": skipped})
        self.store.log_action(
            "duplicates.quarantine",
            status="ok",
            details={"moved": moved, "skipped": skipped, "planned": len(plan)},
        )
        return result

    # ------------------------------------------------------------------ #
    # Summaries
    # ------------------------------------------------------------------ #

    async def summarize(self, path: str, use_ai: bool = True) -> Dict[str, Any]:
        resolved = self.require_approved(path)
        if not resolved.is_file():
            raise FileIntelligenceError(f"Not a file: '{resolved}'")
        settings = self.settings_store.load()
        extraction = extract_text(
            resolved,
            max_chars=min(settings.max_content_chars, 12000),
            ocr_enabled=settings.ocr_enabled,
        )
        text = extraction.get("text") or ""
        if not text.strip():
            return {
                "path": str(resolved),
                "summary": "",
                "ai_used": False,
                "status": extraction.get("status"),
                "extractor": extraction.get("extractor"),
                "message": extraction.get("error") or "No extractable text was found in this file.",
            }

        summary = ""
        ai_used = False
        warning = None
        if use_ai:
            try:
                provider = get_brain_router().get_provider()
                prompt = (
                    "Summarize this local file for its owner. Use short paragraphs and bullet points. "
                    "Do not invent details, do not repeat secrets, and state clearly if the content is "
                    "incomplete.\n\n"
                    f"File: {resolved.name}\n\n{text[:10000]}"
                )
                summary = await asyncio.wait_for(
                    provider.generate_chat(
                        [
                            ChatMessage(role="system", content="You summarize local documents factually."),
                            ChatMessage(role="user", content=prompt),
                        ],
                        temperature=0.2,
                        max_tokens=700,
                    ),
                    timeout=25,
                )
                ai_used = bool(summary.strip())
            except Exception as exc:
                warning = f"AI summary unavailable: {exc}"

        if not summary.strip():
            summary = text[:1200].strip()
            if len(text) > 1200:
                summary += " …"
        return {
            "path": str(resolved),
            "summary": summary,
            "ai_used": ai_used,
            "status": extraction.get("status"),
            "extractor": extraction.get("extractor"),
            "chars": len(text),
            "warning": warning,
        }


_service: Optional[FileIntelligenceService] = None


def get_file_service() -> FileIntelligenceService:
    global _service
    if _service is None:
        _service = FileIntelligenceService()
    return _service


def set_file_service(service: Optional[FileIntelligenceService]) -> None:
    global _service
    _service = service
