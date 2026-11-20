from datetime import datetime, timezone
from fastapi import APIRouter
from echo.api.schemas import SettingsResponse, SettingsUpdateRequest
from echo.core.config import get_settings
from echo.core.database import get_database

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
async def get_app_settings():
    settings = get_settings()
    db = get_database()

    with db.get_connection() as conn:
        cur = conn.execute("SELECT key, value FROM app_settings;")
        db_settings = dict(cur.fetchall())

    ai_provider = db_settings.get("ai_provider", settings.ai_provider)
    ai_model = db_settings.get("ai_model", settings.ai_model)
    ai_api_key = db_settings.get("ai_api_key", settings.ai_api_key or "")
    ai_api_base = db_settings.get("ai_api_base", settings.ai_api_base or "")
    ai_temperature = float(db_settings.get("ai_temperature", settings.ai_temperature))
    ai_max_tokens = int(db_settings.get("ai_max_tokens", settings.ai_max_tokens))
    theme = db_settings.get("theme", "dark")
    startup_behavior = db_settings.get("startup_behavior", "tray")

    return SettingsResponse(
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_api_key_configured=bool(ai_api_key.strip()) if ai_api_key else False,
        ai_api_base=ai_api_base if ai_api_base else None,
        ai_temperature=ai_temperature,
        ai_max_tokens=ai_max_tokens,
        theme=theme,
        startup_behavior=startup_behavior,
        data_dir=str(settings.data_dir),
    )


@router.put("", response_model=SettingsResponse)
async def update_app_settings(req: SettingsUpdateRequest):
    db = get_database()
    now_str = datetime.now(timezone.utc).isoformat()

    updates = {}
    if req.ai_provider is not None:
        updates["ai_provider"] = req.ai_provider
    if req.ai_model is not None:
        updates["ai_model"] = req.ai_model
    if req.ai_api_key is not None:
        updates["ai_api_key"] = req.ai_api_key
    if req.ai_api_base is not None:
        updates["ai_api_base"] = req.ai_api_base
    if req.ai_temperature is not None:
        updates["ai_temperature"] = str(req.ai_temperature)
    if req.ai_max_tokens is not None:
        updates["ai_max_tokens"] = str(req.ai_max_tokens)
    if req.theme is not None:
        updates["theme"] = req.theme
    if req.startup_behavior is not None:
        updates["startup_behavior"] = req.startup_behavior

    with db.transaction() as conn:
        for k, v in updates.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (k, v, now_str),
            )

    return await get_app_settings()

