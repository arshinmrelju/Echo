from pathlib import Path
import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_data_dir() -> Path:
    """Return default data directory: %LOCALAPPDATA%\\Echo\\data or ./data fallback."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "Echo" / "data"
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base
        except OSError:
            # Sandbox or permission restriction: fallback to workspace data directory
            pass

    base = Path.cwd() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Settings(BaseSettings):
    # Server configuration
    host: str = Field(default="127.0.0.1", alias="ECHO_HOST")
    port: int = Field(default=8000, alias="ECHO_PORT")
    debug: bool = Field(default=False, alias="ECHO_DEBUG")
    token: Optional[str] = Field(default=None, alias="ECHO_TOKEN")

    # Storage paths
    data_dir: Path = Field(default_factory=get_default_data_dir, alias="ECHO_DATA_DIR")
    db_name: str = "echo.db"

    # AI Provider defaults
    ai_provider: str = Field(default="mock", alias="ECHO_AI_PROVIDER")
    ai_model: str = Field(default="echo-fast-v1", alias="ECHO_AI_MODEL")
    ai_api_key: Optional[str] = Field(default=None, alias="ECHO_AI_API_KEY")
    ai_api_base: Optional[str] = Field(default=None, alias="ECHO_AI_API_BASE")
    ai_temperature: float = Field(default=0.7, alias="ECHO_AI_TEMPERATURE")
    ai_max_tokens: int = Field(default=2048, alias="ECHO_AI_MAX_TOKENS")

    # Security
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        alias="ECHO_ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
