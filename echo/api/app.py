from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from echo.api.routes import chat, health, memory, settings, tasks
from echo.api.websocket import router as ws_router
from echo.core.config import get_settings
from echo.core.database import get_database
from echo.core.events import get_event_bus
from echo.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("DEBUG LIFESPAN: entering", flush=True)
    cfg = get_settings()
    print("DEBUG LIFESPAN: got settings", flush=True)
    logger = setup_logging(debug=cfg.debug)
    print("DEBUG LIFESPAN: setup logging", flush=True)

    # Initialize SQLite database & migrations
    db = get_database()
    print("DEBUG LIFESPAN: got db", flush=True)

    # Start Event Bus
    bus = get_event_bus()
    bus.start()
    print("DEBUG LIFESPAN: bus started, yielding", flush=True)

    yield

    print("DEBUG LIFESPAN: post-yield, stopping bus", flush=True)
    await bus.stop()
    print("DEBUG LIFESPAN: bus stopped", flush=True)


def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title="ECHO Core Daemon",
        description="Personal AI Assistant Daemon API and WebSocket Gateway",
        version="0.1.0",
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
    app.include_router(ws_router)

    return app


app = create_app()
