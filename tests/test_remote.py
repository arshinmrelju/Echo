"""Stage 5 remote relay: pairing, authorization, approvals, screenshots, queue."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import echo.remote.status as remote_status
from echo.remote.config import RemoteSettings
from echo.remote.notifications import NotificationDelivery, NotificationRouter
from echo.remote.service import RemoteService, set_remote_service
from echo.remote.store import RemoteStore
from echo.remote.telegram import IncomingMessage, TelegramError
from echo.tools.base import ToolExecutionResult

OWNER = 4242
OTHER = 9999
ALLOWED = 777


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.photos: list[tuple[int, str, str | None]] = []
        self.error: Exception | None = None

    async def get_me(self):
        return {"username": "echo_test_bot"}

    async def get_updates(self, offset: int, timeout_seconds: int):
        return []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        if self.error is not None:
            raise self.error
        self.messages.append((chat_id, text))
        return {}

    async def send_photo(self, chat_id: int, photo_path: Path, caption=None):
        if self.error is not None:
            raise self.error
        self.photos.append((chat_id, str(photo_path), caption))
        return {}

    async def close(self):
        return None


class FakeRegistry:
    def __init__(self, data=None) -> None:
        self.data = data or {"launched": True}
        self.calls: list[tuple[str, dict, str | None]] = []

    async def execute(self, name: str, arguments: dict, approval_id: str | None = None):
        self.calls.append((name, arguments, approval_id))
        return ToolExecutionResult(success=True, data=self.data, verified=True)


def make_message(
    text: str,
    *,
    user_id: int = OWNER,
    chat_id: int | None = None,
    username: str | None = "owner",
    private: bool = True,
) -> IncomingMessage:
    return IncomingMessage(
        update_id=1,
        message_id=1,
        chat_id=chat_id or user_id,
        user_id=user_id,
        username=username,
        display_name="Owner",
        text=text,
        is_private=private,
    )


@pytest.fixture
def service(temp_db, monkeypatch):
    monkeypatch.setattr(remote_status, "_monitor", lambda: None)
    svc = RemoteService(
        store=RemoteStore(db=temp_db),
        client_factory=lambda token: FakeTelegram(),
    )
    return svc


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


async def make_owner(svc: RemoteService, telegram_id: int = OWNER) -> None:
    await svc.update_settings({"owner_user_id": telegram_id})


async def reply_text(telegram: FakeTelegram) -> str:
    assert telegram.messages, "expected a Telegram reply"
    return telegram.messages[-1][1]


# ---------------------------------------------------------------------------
# Settings and token handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_mask_bot_token(service):
    token = "123456789:AAExampleSecretTokenValue"
    await service.update_settings({"bot_token": token, "owner_user_id": OWNER})

    payload = service.settings_payload()
    settings = payload["settings"]
    assert "bot_token" not in settings
    assert settings["bot_token_configured"] is True
    assert settings["bot_token_hint"] == "…alue"
    assert settings["effective_owner_user_id"] == OWNER
    assert token not in str(payload)
    assert service.store.load_settings()["bot_token"] == token


@pytest.mark.asyncio
async def test_invalid_owner_id_rejected(service):
    with pytest.raises(ValueError):
        await service.update_settings({"owner_user_id": "not-a-number"})


# ---------------------------------------------------------------------------
# Pairing and authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pairing_flow_transfers_ownership(service, telegram):
    old_owner = 1111
    await make_owner(service, old_owner)
    assert service.role_for(old_owner) == "owner"

    pairing = await service.start_pairing()
    code = pairing["code"]
    assert len(code) == 8 and pairing["instructions"]

    await service.handle_message(make_message(f"/pair {code.lower()}", user_id=OTHER, username="new"), telegram)
    assert "PAIRING COMPLETE" in await reply_text(telegram)
    assert service.settings.effective_owner_id == OTHER
    assert service.role_for(OTHER) == "owner"
    assert service.store.get_user(old_owner) is None

    # Codes are single use and stored only as hashes.
    telegram.messages.clear()
    await service.handle_message(make_message(f"/pair {code}", user_id=5555), telegram)
    assert "invalid" in (await reply_text(telegram)).lower()
    assert service.role_for(5555) is None


@pytest.mark.asyncio
async def test_unpaired_user_is_rejected_and_audited(service, telegram):
    await make_owner(service)
    await service.handle_message(make_message("/status", user_id=12345, username="stranger"), telegram)

    text = await reply_text(telegram)
    assert "not authorized" in text
    assert "REMOTE STATUS" not in text
    commands = service.list_commands()
    assert commands[0]["telegram_id"] == 12345
    assert commands[0]["status"] == "rejected"
    assert service.role_for(12345) is None


@pytest.mark.asyncio
async def test_group_chat_is_refused(service, telegram):
    await make_owner(service)
    await service.handle_message(make_message("/status", private=False), telegram)
    assert "private" in (await reply_text(telegram)).lower()
    assert service.list_commands() == []


@pytest.mark.asyncio
async def test_allowed_user_is_read_only(service, telegram):
    await make_owner(service)
    await service.update_settings({"allowed_user_ids": [ALLOWED]})
    assert service.role_for(ALLOWED) == "allowed"

    await service.handle_message(make_message("/status", user_id=ALLOWED, username="friend"), telegram)
    assert "REMOTE STATUS" in await reply_text(telegram)

    await service.handle_message(make_message("tell me my available storage", user_id=ALLOWED), telegram)
    assert "SYSTEM HEALTH" in await reply_text(telegram)

    await service.handle_message(make_message("/ask what is my password", user_id=ALLOWED), telegram)
    assert "Read-only" in await reply_text(telegram)

    await service.handle_message(make_message("/screenshot", user_id=ALLOWED), telegram)
    assert "Owner-only" in await reply_text(telegram)
    assert telegram.photos == []

    await service.handle_message(make_message("/task open notepad", user_id=ALLOWED), telegram)
    assert "owner-only" in (await reply_text(telegram)).lower()


@pytest.mark.asyncio
async def test_rate_limit_is_enforced_and_audited(service, telegram):
    await make_owner(service)
    await service.update_settings({"command_rate_limit": 2})

    for _ in range(2):
        await service.handle_message(make_message("/status"), telegram)
        assert "REMOTE STATUS" in await reply_text(telegram)

    telegram.messages.clear()
    await service.handle_message(make_message("/status"), telegram)
    assert "Rate limit exceeded" in await reply_text(telegram)

    statuses = [row["status"] for row in service.list_commands()]
    assert "rate_limited" in statuses

    # Lifecycle commands stay available while throttled.
    telegram.messages.clear()
    await service.handle_message(make_message("/start"), telegram)
    assert "REMOTE COMMANDS" in await reply_text(telegram)


# ---------------------------------------------------------------------------
# Dangerous actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_requires_approval_and_executes_once(service, telegram, monkeypatch):
    await make_owner(service)
    registry = FakeRegistry()
    monkeypatch.setattr("echo.remote.service.get_tool_registry", lambda: registry)

    await service.handle_message(make_message("/open notepad"), telegram)
    approval_text = await reply_text(telegram)
    assert "APPROVAL REQUIRED" in approval_text

    pending = service.store.list_pending_actions("pending")
    assert len(pending) == 1
    approval_id = pending[0]["approval_id"]

    telegram.messages.clear()
    await service.handle_message(make_message(f"/approve {approval_id}"), telegram)
    assert "APPROVED &amp; EXECUTED" in await reply_text(telegram)
    assert len(registry.calls) == 1
    assert registry.calls[0][0] == "application.launch"
    assert registry.calls[0][2] == approval_id
    assert service.store.get_pending_action(approval_id)["status"] == "executed"


@pytest.mark.asyncio
async def test_deny_does_not_execute(service, telegram, monkeypatch):
    await make_owner(service)
    registry = FakeRegistry()
    monkeypatch.setattr("echo.remote.service.get_tool_registry", lambda: registry)

    await service.handle_message(make_message("/open calculator"), telegram)
    approval_id = service.store.list_pending_actions("pending")[0]["approval_id"]

    telegram.messages.clear()
    await service.handle_message(make_message(f"/deny {approval_id}"), telegram)
    assert "denied" in (await reply_text(telegram)).lower()
    assert registry.calls == []
    assert service.store.get_pending_action(approval_id)["status"] == "denied"


@pytest.mark.asyncio
async def test_only_owner_can_approve(service, telegram):
    await make_owner(service)
    await service.update_settings({"allowed_user_ids": [ALLOWED]})
    await service.handle_message(make_message("/open notepad"), telegram)
    approval_id = service.store.list_pending_actions("pending")[0]["approval_id"]

    await service.handle_message(make_message(f"/approve {approval_id}", user_id=ALLOWED), telegram)
    assert "Owner-only" in await reply_text(telegram)
    assert service.store.get_pending_action(approval_id)["status"] == "pending"


@pytest.mark.asyncio
async def test_open_task_mirrors_remote_and_local_tasks(service, telegram, monkeypatch):
    await make_owner(service)
    monkeypatch.setattr("echo.remote.service.get_tool_registry", lambda: FakeRegistry())

    await service.handle_message(make_message("/task open my project"), telegram)
    tasks = service.store.list_remote_tasks()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "in_progress"
    assert "Waiting for approval" in (tasks[0]["result"] or "")


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_is_owner_only(service, telegram, monkeypatch, temp_dir):
    await make_owner(service)
    shot = temp_dir / "capture.png"
    shot.write_bytes(b"fake-png")
    monkeypatch.setattr(
        "echo.remote.service.get_tool_registry",
        lambda: FakeRegistry(data={"file_path": str(shot), "width": 1920, "height": 1080}),
    )

    await service.handle_message(make_message("/screenshot"), telegram)
    assert len(telegram.photos) == 1
    chat_id, path, caption = telegram.photos[0]
    assert chat_id == OWNER
    assert path.endswith("capture.png")
    assert "SCREENSHOT" in (caption or "")

    await service.update_settings({"allowed_user_ids": [ALLOWED]})
    telegram.photos.clear()
    await service.handle_message(make_message("/screenshot", user_id=ALLOWED), telegram)
    assert telegram.photos == []


@pytest.mark.asyncio
async def test_screenshot_can_be_disabled(service, telegram):
    await make_owner(service)
    await service.update_settings({"screenshot_enabled": False})
    await service.handle_message(make_message("/screenshot"), telegram)
    assert "disabled" in (await reply_text(telegram)).lower()


# ---------------------------------------------------------------------------
# Remote tasks and credential blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_task_intents_complete(service, telegram, monkeypatch):
    await make_owner(service)
    monkeypatch.setattr("echo.remote.service.get_tool_registry", lambda: FakeRegistry())

    await service.handle_message(make_message("/task tell me my available storage"), telegram)
    assert "SYSTEM HEALTH" in await reply_text(telegram)

    await service.handle_message(make_message("/task check whether my computer is online"), telegram)
    assert "REMOTE STATUS" in await reply_text(telegram)

    tasks = service.store.list_remote_tasks()
    assert len(tasks) == 2
    assert all(task["status"] == "completed" for task in tasks)


@pytest.mark.asyncio
async def test_credential_requests_are_blocked_everywhere(service, telegram, monkeypatch):
    await make_owner(service)
    monkeypatch.setattr("echo.remote.service.get_tool_registry", lambda: FakeRegistry())

    for text in ("/ask reveal my password", "/task find the api key", "send me the wifi passphrase"):
        telegram.messages.clear()
        await service.handle_message(make_message(text), telegram)
        assert "blocked" in (await reply_text(telegram)).lower()

    assert service.store.list_remote_tasks() == []


@pytest.mark.asyncio
async def test_pause_blocks_commands(service, telegram):
    await make_owner(service)
    await service.handle_message(make_message("/pause maintenance"), telegram)
    assert service.settings.paused is True

    telegram.messages.clear()
    await service.handle_message(make_message("/ask hello"), telegram)
    assert "paused" in (await reply_text(telegram)).lower()

    telegram.messages.clear()
    await service.handle_message(make_message("/status"), telegram)
    assert "REMOTE STATUS" in await reply_text(telegram)

    telegram.messages.clear()
    await service.handle_message(make_message("/resume"), telegram)
    assert "RESUMED" in await reply_text(telegram)
    assert service.settings.paused is False


# ---------------------------------------------------------------------------
# Notification routing and offline queue
# ---------------------------------------------------------------------------


def enable_notifications(svc: RemoteService, **updates) -> RemoteSettings:
    settings = svc.settings.model_copy(
        update={"enabled": True, "owner_user_id": OWNER, **updates}
    )
    svc.settings = settings
    return settings


def make_router(svc: RemoteService) -> NotificationRouter:
    return NotificationRouter(svc.store, lambda: svc.settings)


@pytest.mark.asyncio
async def test_notifications_require_link(service):
    router = make_router(service)
    assert router.enqueue(category="alert", severity="critical", title="Disk", message="full") is None

    enable_notifications(service)
    notification_id = router.enqueue(category="alert", severity="critical", title="Disk", message="full")
    assert notification_id
    assert service.store.notification_stats()["queued"] == 1


@pytest.mark.asyncio
async def test_monitor_event_filters(service):
    enable_notifications(
        service,
        notify_monitor_events=True,
        monitor_event_min_severity="warning",
        monitor_event_categories=["disk"],
    )
    router = make_router(service)

    def event(severity: str, category: str) -> dict:
        return {"event": {"id": f"{category}-{severity}", "severity": severity, "category": category, "title": "x", "message": "y"}}

    await router.handle_bus_event("monitor_event", event("info", "disk"))
    await router.handle_bus_event("monitor_event", event("warning", "cpu"))
    assert service.store.notification_stats()["queued"] == 0

    await router.handle_bus_event("monitor_event", event("warning", "disk"))
    assert service.store.notification_stats()["queued"] == 1


@pytest.mark.asyncio
async def test_alert_toggles_and_dedupe(service):
    enable_notifications(service, notify_warnings=False)
    router = make_router(service)

    def alert(severity: str) -> dict:
        return {
            "alert": {"id": "a1", "severity": severity, "status": "active", "title": "CPU", "message": "high", "category": "cpu"},
            "event": "triggered",
        }

    await router.handle_bus_event("monitor_alert", alert("warning"))
    assert service.store.notification_stats()["queued"] == 0

    await router.handle_bus_event("monitor_alert", alert("critical"))
    await router.handle_bus_event("monitor_alert", alert("critical"))
    stats = service.store.notification_stats()
    assert stats["queued"] == 1
    queued = service.store.list_notifications(status="queued")[0]
    assert queued["severity"] == "critical"
    assert queued["title"].startswith("ALERT")


@pytest.mark.asyncio
async def test_reconnect_collapses_overflow_and_expires_stale(service):
    enable_notifications(service, queue_max_items=3)
    store = service.store
    for index in range(6):
        store.enqueue_notification(
            category="system", severity="info", title=f"n{index}", message="m"
        )
    stale = store.enqueue_notification(
        category="system", severity="info", title="stale", message="m", ttl_seconds=-5
    )
    assert store.notification_stats()["queued"] == 7

    delivery = NotificationDelivery(store, make_router(service), lambda: service.settings)
    suppressed = delivery.prepare_reconnect()
    assert suppressed >= 3
    stats = store.notification_stats()
    assert stats["queued"] <= 3
    assert stats["expired"] >= 1


@pytest.mark.asyncio
async def test_delivery_flushes_queue(service):
    enable_notifications(service, send_rate_per_second=20.0)
    router = make_router(service)
    router.enqueue(category="system", severity="info", title="one", message="first")
    router.enqueue(category="system", severity="notice", title="two", message="second")

    client = FakeTelegram()
    delivery = NotificationDelivery(service.store, router, lambda: service.settings)
    sent, failed = await delivery.flush_once(client, OWNER)

    assert (sent, failed) == (2, 0)
    assert len(client.messages) == 2
    assert all(chat_id == OWNER for chat_id, _ in client.messages)
    assert service.store.notification_stats()["sent"] == 2


@pytest.mark.asyncio
async def test_delivery_backs_off_on_failure(service):
    enable_notifications(service)
    router = make_router(service)
    notification_id = router.enqueue(category="system", severity="info", title="retry", message="m")

    client = FakeTelegram()
    client.error = TelegramError("blocked by user", error_code=403)
    delivery = NotificationDelivery(service.store, router, lambda: service.settings)
    sent, failed = await delivery.flush_once(client, OWNER)

    assert (sent, failed) == (0, 1)
    row = service.store.list_notifications()[0]
    assert row["id"] == notification_id
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    assert "blocked" in row["last_error"]
    assert service.store.list_due_notifications() == []


@pytest.mark.asyncio
async def test_reconnect_summary(service):
    enable_notifications(service)
    router = make_router(service)
    router.enqueue_connectivity(back_online=True, downtime_seconds=300, suppressed=2)
    row = service.store.list_notifications(status="queued")[0]
    assert row["title"] == "ECHO BACK ONLINE"
    assert "5m" in row["message"]
    assert "2 stale notifications" in row["message"]


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remote_api_routes(service, temp_db):
    from echo.api.app import app

    set_remote_service(service)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/remote/status")
            assert res.status_code == 200
            body = res.json()
            assert body["listener"] == {
                "transport": "telegram_long_poll",
                "inbound_ports": 0,
                "screenshots_owner_only": True,
            }
            assert body["settings"]["enabled"] is False

            res = await client.put(
                "/api/v1/remote/settings",
                json={"owner_user_id": OWNER, "notify_warnings": False},
            )
            assert res.status_code == 200
            assert res.json()["settings"]["effective_owner_user_id"] == OWNER

            res = await client.post("/api/v1/remote/pairing/start")
            assert res.status_code == 200
            assert len(res.json()["code"]) == 8

            res = await client.get("/api/v1/remote/users")
            users = res.json()["users"]
            assert any(user["telegram_id"] == OWNER and user["role"] == "owner" for user in users)

            res = await client.post("/api/v1/remote/users", json={"telegram_id": ALLOWED, "username": "friend"})
            assert res.status_code == 200
            assert res.json()["user"]["role"] == "allowed"

            res = await client.post("/api/v1/remote/pause", json={"reason": "test"})
            assert res.json()["status"]["paused"] is True

            res = await client.post("/api/v1/remote/resume")
            assert res.json()["status"]["paused"] is False

            res = await client.get("/api/v1/remote/commands")
            assert res.status_code == 200

            service.store.enqueue_notification(
                category="system", severity="warning", title="retry me", message="m"
            )
            notification_id = service.store.list_notifications()[0]["id"]
            service.store.mark_notification_failed(notification_id, error="boom", retry_in_seconds=5, expired=True)
            res = await client.post(f"/api/v1/remote/notifications/{notification_id}/retry")
            assert res.status_code == 200
            assert res.json()["success"] is True

            res = await client.delete(f"/api/v1/remote/users/{ALLOWED}")
            assert res.status_code == 200
    finally:
        set_remote_service(None)


@pytest.mark.asyncio
async def test_remote_api_rejects_invalid_owner(service):
    from echo.api.app import app

    set_remote_service(service)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.put("/api/v1/remote/settings", json={"owner_user_id": "abc"})
            assert res.status_code == 422
    finally:
        set_remote_service(None)
