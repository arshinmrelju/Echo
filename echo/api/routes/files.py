import asyncio
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from echo.api.schemas import (
    FileBulkRenameRequest,
    FileCopyMoveRequest,
    FileDirectoryCreateRequest,
    FileIndexRequest,
    FileOpenRequest,
    FileOrganizeRequest,
    FileQuarantineRequest,
    FileRenameRequest,
    FileSettingsUpdateRequest,
    FileSummarizeRequest,
)
from echo.files.service import (
    ConfirmationRequired,
    FileIntelligenceError,
    FileIntelligenceService,
    get_file_service,
    parse_timestamp,
)

router = APIRouter(prefix="/api/v1/files", tags=["File Intelligence"])

_index_lock = threading.Lock()


def _service() -> FileIntelligenceService:
    return get_file_service()


def _run_index(service: FileIntelligenceService, directory_id: Optional[str], force: bool):
    with _index_lock:
        return service.index_directory(directory_id=directory_id, force=force)


def _raise(exc: FileIntelligenceError):
    if isinstance(exc, ConfirmationRequired):
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "plan": exc.plan},
        ) from exc
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/status")
async def file_status():
    service = _service()
    stats = service.stats()
    return {
        **stats,
        "approved_directory_count": len(stats.get("directories") or []),
        "locked": _index_lock.locked(),
    }


@router.get("/directories")
async def list_directories():
    return {"directories": _service().store.list_directories()}


@router.post("/directories")
async def add_directory(req: FileDirectoryCreateRequest):
    service = _service()
    try:
        directory = service.add_directory(req.path, req.label, req.recursive)
    except FileIntelligenceError as exc:
        _raise(exc)

    index_result = None
    if req.index_now:
        try:
            index_result = await asyncio.to_thread(
                _run_index, service, directory["id"], False
            )
            directory = service.store.get_directory(directory["id"]) or directory
        except FileIntelligenceError as exc:
            _raise(exc)
    return {"success": True, "directory": directory, "index": index_result}


@router.delete("/directories/{directory_id}")
async def remove_directory(directory_id: str):
    if not _service().remove_directory(directory_id):
        raise HTTPException(status_code=404, detail="Approved directory not found")
    return {"success": True, "id": directory_id}


@router.post("/index")
async def index_files(req: Optional[FileIndexRequest] = None):
    service = _service()
    try:
        result = await asyncio.to_thread(
            _run_index,
            service,
            req.directory_id if req else None,
            req.force if req else False,
        )
    except FileIntelligenceError as exc:
        _raise(exc)
    return {"success": True, "result": result}


@router.get("/search")
async def search_files(
    q: Optional[str] = Query(None),
    extension: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_size_mb: Optional[float] = Query(None, ge=0),
    max_size_mb: Optional[float] = Query(None, ge=0),
    modified_after: Optional[str] = Query(None),
    modified_before: Optional[str] = Query(None),
    directory_id: Optional[str] = Query(None),
    sort: str = Query("modified"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    service = _service()
    result = service.search(
        query=q,
        extension=extension,
        category=category,
        min_size=int(min_size_mb * 1024 * 1024) if min_size_mb is not None else None,
        max_size=int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None,
        modified_after=parse_timestamp(modified_after),
        modified_before=parse_timestamp(modified_before),
        directory_id=directory_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/stats")
async def file_stats():
    return _service().stats()


@router.get("/categories")
async def file_categories():
    return {"categories": _service().list_categories()}


@router.get("/duplicates")
async def duplicate_files(
    min_size_mb: float = Query(0, ge=0),
    directory_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    groups = _service().store.duplicate_groups(
        min_size=int(min_size_mb * 1024 * 1024),
        directory_id=directory_id,
        limit=limit,
    )
    return {
        "groups": groups,
        "count": len(groups),
        "file_count": sum(len(group["files"]) for group in groups),
    }


@router.get("/large")
async def large_files(
    min_size_mb: float = Query(100, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    files = _service().store.large_files(
        min_size=int(min_size_mb * 1024 * 1024), limit=limit
    )
    return {"files": files, "count": len(files)}


@router.get("/details")
async def file_details(path: str = Query(...)):
    try:
        return _service().details(path)
    except FileIntelligenceError as exc:
        _raise(exc)


@router.get("/activity")
async def file_activity(limit: int = Query(100, ge=1, le=500)):
    actions = _service().store.list_actions(limit)
    return {"actions": actions, "count": len(actions)}


@router.put("/settings")
async def update_file_settings(req: FileSettingsUpdateRequest):
    settings = _service().update_settings(req.model_dump(exclude_none=True))
    return {"success": True, "settings": settings.model_dump()}


@router.post("/open")
async def open_file(req: FileOpenRequest):
    try:
        return await asyncio.to_thread(_service().open_file, req.path)
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/rename")
async def rename_file(req: FileRenameRequest):
    try:
        return await asyncio.to_thread(
            _service().rename, req.path, req.new_name, req.confirm
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/copy")
async def copy_file(req: FileCopyMoveRequest):
    try:
        return await asyncio.to_thread(
            _service().copy, req.path, req.destination, req.confirm
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/move")
async def move_file(req: FileCopyMoveRequest):
    try:
        return await asyncio.to_thread(
            _service().move, req.path, req.destination, req.confirm
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/organize")
async def organize_files(req: FileOrganizeRequest):
    try:
        return await asyncio.to_thread(
            _service().organize,
            req.directory,
            req.destination_root,
            req.confirm,
            req.dry_run,
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/bulk-rename")
async def bulk_rename(req: FileBulkRenameRequest):
    try:
        return await asyncio.to_thread(
            _service().bulk_rename,
            req.directory,
            req.find,
            req.replace,
            req.confirm,
            req.dry_run,
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/duplicates/quarantine")
async def quarantine_duplicates(req: FileQuarantineRequest):
    try:
        return await asyncio.to_thread(
            _service().quarantine_duplicates,
            req.directory,
            req.confirm,
            req.dry_run,
        )
    except FileIntelligenceError as exc:
        _raise(exc)


@router.post("/summarize")
async def summarize_file(req: FileSummarizeRequest):
    try:
        return await _service().summarize(req.path, use_ai=req.use_ai)
    except FileIntelligenceError as exc:
        _raise(exc)
