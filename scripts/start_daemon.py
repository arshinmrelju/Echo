import uvicorn
from echo.core.config import get_settings


def main():
    cfg = get_settings()
    uvicorn.run(
        "echo.api.app:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
        log_level="debug" if cfg.debug else "info",
    )


if __name__ == "__main__":
    main()

