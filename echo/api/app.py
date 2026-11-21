import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from echo.api.routes import chat, files, health, memory, monitoring, remote, settings, tasks, tools, voice
from echo.api.websocket import router as ws_router
from echo.core.config import get_settings
from echo.core.database import get_database
from echo.core.events import get_event_bus
from echo.core.logging import setup_logging
from echo.monitoring.service import get_monitoring_service
from echo.remote.service import get_remote_service
from echo.tools.bootstrap import initialize_all_tools
from echo.voice.service import get_voice_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup sequence
    cfg = get_settings()
    logger = setup_logging(debug=cfg.debug)
    logger.info("Initializing ECHO Core Daemon on %s:%d...", cfg.host, cfg.port)

    # Initialize SQLite database & migrations
    db = get_database()
    logger.info("SQLite database verified at: %s", db.db_path)

    # Register all tools
    initialize_all_tools()
    logger.info("Desktop Tools Registry initialized.")

    # Start Event Bus
    bus = get_event_bus()
    bus.start()
    logger.info("In-process Event Bus started.")

    # System monitoring runs independently of any open UI. It only starts when
    # enabled in persisted settings so a fresh install stays quiet until asked.
    monitoring_service = get_monitoring_service()
    if monitoring_service.settings.enabled:
        await monitoring_service.start(enable=False)
        logger.info(
            "System monitoring started (profile=%s, poll=%ss).",
            monitoring_service.settings.profile,
            monitoring_service.settings.poll_interval_seconds,
        )
    else:
        logger.info("System monitoring idle (disabled in settings).")

    # Voice service is constructed but only opens the microphone on explicit
    # user action, unless auto-start is deliberately enabled.
    voice_service = get_voice_service()
    voice_service.bind_loop(asyncio.get_running_loop())
    if voice_service.settings.auto_start:
        started = await voice_service.start()
        logger.info("Voice auto-start requested: %s", "started" if started else "failed")
    else:
        logger.info("Voice idle (microphone closed until the user enables it).")

    # Remote relay is outbound-only. It stays idle until a bot token, owner,
    # and the enabled flag are all configured.
    remote_service = get_remote_service()
    if remote_service.settings.enabled and remote_service.settings.effective_token:
        started = await remote_service.start(enable=False)
        logger.info("Remote relay start requested: %s", "connected" if started else "not connected")
    else:
        logger.info("Remote relay idle (disabled or not configured).")

    yield

    # Shutdown sequence
    await remote_service.stop(disable=False)
    await monitoring_service.stop(disable=False)
    await voice_service.stop()
    await bus.stop()
    logger.info("ECHO Core Daemon shutdown complete.")


def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title="ECHO Core Daemon",
        description="Personal AI Assistant Daemon API and WebSocket Gateway",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(memory.router)
    app.include_router(files.router)
    app.include_router(tasks.router)
    app.include_router(settings.router)
    app.include_router(tools.router)
    app.include_router(voice.router)
    app.include_router(monitoring.router)
    app.include_router(remote.router)
    app.include_router(ws_router)

    return app


app = create_app()
