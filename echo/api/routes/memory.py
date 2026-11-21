from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from echo.api.schemas import (
    MemoryClearRequest,
    MemoryCreateRequest,
    MemoryResponse,
    MemoryStatsResponse,
    MemoryUpdateRequest,
)
from echo.memory.store import MemoryEntry, MemoryStore, get_memory_store

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


def _response(entry: MemoryEntry) -> MemoryResponse:
    return MemoryResponse(
        id=entry.id,
        category=entry.category,
        key=entry.key,
        content=entry.content,
        confidence=entry.confidence,
        sensitivity=entry.sensitivity,
        source=entry.source,
        tags=entry.tags,
        pinned=entry.pinned,
        archived=entry.archived,
        permission_granted=entry.permission_granted,
        last_used_at=entry.last_used_at,
        use_count=entry.use_count,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _store() -> MemoryStore:
    return get_memory_store()


@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    category: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
):
    entries = _store().list_memories(
        category=category,
        query=query,
        source=source,
        include_archived=include_archived,
        limit=limit,
    )
    return [_response(e) for e in entries]


@router.get("/stats", response_model=MemoryStatsResponse)
async def memory_stats():
    return _store().stats()


@router.get("/export")
async def export_memories():
    return _store().export_memories()


@router.post("", response_model=MemoryResponse)
async def create_memory(req: MemoryCreateRequest):
    try:
        entry = _store().add_memory(
            category=req.category,
            key=req.key,
            content=req.content,
            confidence=req.confidence,
            source=req.source or "user",
            tags=req.tags,
            pinned=req.pinned,
            allow_sensitive=req.allow_sensitive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(entry)


@router.post("/clear")
async def clear_memories(req: MemoryClearRequest):
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Clearing memory requires confirm=true. Export first if you want a backup.",
        )
    removed = _store().clear_memories(category=req.category)
    return {"success": True, "removed": removed, "category": req.category}


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: str):
    entry = _store().get_memory(memory_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return _response(entry)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(memory_id: str, req: MemoryUpdateRequest):
    try:
        entry = _store().update_memory(
            memory_id,
            category=req.category,
            key=req.key,
            content=req.content,
            confidence=req.confidence,
            source=req.source,
            tags=req.tags,
            pinned=req.pinned,
            archived=req.archived,
            sensitivity=req.sensitivity,
            allow_sensitive=bool(req.allow_sensitive),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(entry)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    success = _store().delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"success": True, "id": memory_id}
