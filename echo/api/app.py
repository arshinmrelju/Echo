from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from echo.api.routes import chat, health, memory, settings, tasks, tools
from echo.api.websocket import router as ws_router
from echo.core.config import get_settings
from echo.core.database import get_database
from echo.core.events import get_event_bus
from echo.core.logging import setup_logging
from echo.tools.bootstrap import initialize_all_tools


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

    yield

    # Shutdown sequence
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
    app.include_router(tasks.router)
    app.include_router(settings.router)
    app.include_router(tools.router)
    app.include_router(ws_router)

    return app


app = create_app()
