from datetime import datetime, timezone
import platform
import time
from fastapi import APIRouter
import psutil
from echo.api.schemas import HealthStatusResponse, SystemMetricsResponse
from echo.brain.router import get_brain_router
from echo.core.config import get_settings
from echo.core.database import get_database

router = APIRouter(tags=["Health & System"])
_start_time = time.time()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    db = get_database()
    try:
        with db.get_connection() as conn:
            conn.execute("SELECT 1;").fetchone()
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}


@router.get("/api/v1/system/status", response_model=HealthStatusResponse)
async def system_status():
    db = get_database()
    db_status = "connected"
    try:
        with db.get_connection() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception:
        db_status = "error"

    router_inst = get_brain_router()
    provider = router_inst.get_provider()
    ai_available = await provider.is_available()

    return HealthStatusResponse(
        status="healthy" if db_status == "connected" else "degraded",
        version="0.1.0",
        database=db_status,
        ai_provider=provider.config.provider_name,
        ai_available=ai_available,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/api/v1/system/metrics", response_model=SystemMetricsResponse)
async def system_metrics():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return SystemMetricsResponse(
        cpu_percent=psutil.cpu_percent(interval=None),
        memory_percent=mem.percent,
        memory_used_mb=round(mem.used / (1024 * 1024), 1),
        memory_total_mb=round(mem.total / (1024 * 1024), 1),
        disk_percent=disk.percent,
        uptime_seconds=round(time.time() - _start_time, 1),
        platform=f"{platform.system()} {platform.release()}",
    )

