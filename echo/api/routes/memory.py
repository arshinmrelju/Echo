from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from echo.api.schemas import MemoryCreateRequest, MemoryResponse
from echo.memory.store import get_memory_store

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    category: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    store = get_memory_store()
    entries = store.list_memories(category=category, query=query, limit=limit)
    return [
        MemoryResponse(
            id=e.id,
            category=e.category,
            key=e.key,
            content=e.content,
            confidence=e.confidence,
            sensitivity=e.sensitivity,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in entries
    ]


@router.post("", response_model=MemoryResponse)
async def create_memory(req: MemoryCreateRequest):
    store = get_memory_store()
    entry = store.add_memory(
        category=req.category,
        key=req.key.strip(),
        content=req.content.strip(),
        confidence=req.confidence,
    )
    return MemoryResponse(
        id=entry.id,
        category=entry.category,
        key=entry.key,
        content=entry.content,
        confidence=entry.confidence,
        sensitivity=entry.sensitivity,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    store = get_memory_store()
    success = store.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"success": True, "id": memory_id}

