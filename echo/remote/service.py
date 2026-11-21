"""Remote relay service: pairing, authorization, commands, and lifecycle.

The daemon owns an outbound long-poll loop against the Telegram Bot API. No
inbound port is opened, and the only account allowed to run sensitive
commands is the explicitly paired owner.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import secrets
import string
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from pydantic import ValidationError

from echo.api.ws_hub import manager
from echo.core.chat_service import get_chat_turn_service
from echo.core.database import get_database
from echo.core.events import Event, get_event_bus
from echo.remote.config import RemoteSettings
from echo.remote.notifications import NotificationDelivery, NotificationRouter
from echo.remote.status import build_status, format_events, format_health, format_status, format_tasks
from echo.remote.store import RemoteStore, hash_pairing_code, now_iso
from echo.remote.telegram import IncomingMessage, TelegramClient, TelegramError, esc
from echo.tools.permissions import get_permission_manager
from echo.tools.registry import get_tool_registry

logger = logging.getLogger("echo.remote.service")

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CREDENTIAL_PATTERN = re.compile(
    r"\b(password|passwd|passphrase|credential|credentials|api[\s_-]?key|"
    r"private[\s_-]?key|secret|seed phrase|recovery code|2fa|otp)\b",
    re.IGNORECASE,
)

OWNER_COMMANDS = [
    ("/status", "PC, ECHO, task, health, and heartbeat"),
    ("/health", "CPU, RAM, disks, battery, and alerts"),
    ("/events [n]", "Recent monitored events (max 10)"),
    ("/tasks", "Task progress"),
    ("/task <goal>", "Run a remote task, e.g. screenshot or storage"),
    ("/ask <question>", "Ask ECHO a question"),
    ("/open <app>", "Open an approved app (requires approval)"),
    ("/screenshot", "Capture this desktop"),
    ("/pending", "Pending dangerous actions"),
    ("/approve <id>", "Approve a dangerous action"),
    ("/deny <id>", "Deny a dangerous action"),
    ("/pause [reason]", "Pause remote command execution"),
    ("/resume", "Resume remote command execution"),
]

ALLOWED_COMMANDS = [
    ("/status", "PC, ECHO, task, health, and heartbeat"),
    ("/health", "CPU, RAM, disks, battery, and alerts"),
    ("/events [n]", "Recent monitored events (max 10)"),
    ("/tasks", "Task progress"),
]


@dataclass
class CommandResponse:
    text: str = ""
    photo_path: Optional[Path] = None
    caption: Optional[str] = None


class RemoteService:
    def __init__(
        self,
        store: Optional[RemoteStore] = None,
        *,
        client_factory: Optional[Callable[[str], TelegramClient]] = None,
    ) -> None:
        self.store = store or RemoteStore()
        self.settings = self._load_settings()
        self._client_factory = client_factory or (lambda token: TelegramClient(token))
        self._client: Optional[TelegramClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._notify_task: Optional[asyncio.Task] = None
        self._start_lock = asyncio.Lock()
        self._connected = False
        self._polling = False
        self._last_error: Optional[str] = None
        self._reconnect_attempts = 0
        self._started_at: Optional[str] = None
        self._pair_attempts: Dict[int, Deque[float]] = defaultdict(deque)
        self._subscribed = False
        self._bus_handler = self._on_bus_event
        self._approval_listener = self._on_approval_resolved
        self.notifications = NotificationRouter(self.store, lambda: self.settings)
        self.delivery = NotificationDelivery(self.store, self.notifications, lambda: self.settings)
        self._ensure_owner_row()

    def _ensure_owner_row(self) -> None:
        owner_id = self.settings.effective_owner_id
        if not owner_id:
            return
        existing = self.store.get_user(owner_id)
        if existing and existing.get("role") == "owner":
            return
        try:
            self.store.upsert_user(
                owner_id,
                username=self.settings.owner_username or (existing or {}).get("username"),
                display_name=self.settings.owner_display_name or "Owner",
                role="owner",
                added_by="settings",
            )
        except Exception as exc:
            logger.debug("Could not register owner row: %s", exc)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load_settings(self) -> RemoteSettings:
        raw = self.store.load_settings() or {}
        try:
            settings = RemoteSettings(**raw)
        except ValidationError as exc:
            logger.warning("Stored remote settings are invalid: %s", exc)
            settings = RemoteSettings()

        if not settings.bot_token:
            env_token = RemoteSettings().effective_token
            if env_token:
                settings = settings.model_copy(update={"bot_token": env_token})
        if not settings.owner_user_id:
            env_owner = RemoteSettings().effective_owner_id
            if env_owner:
                settings = settings.model_copy(update={"owner_user_id": env_owner})
        return settings

    def _save_settings(self) -> None:
        try:
            self.store.save_settings(self.settings.model_dump())
        except Exception as exc:
            logger.error("Could not persist remote settings: %s", exc)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @property
    def running(self) -> bool:
        return self._poll_task is not None and not self._poll_task.done()

    async def start(self, enable: bool = True) -> bool:
        async with self._start_lock:
            if enable and not self.settings.enabled:
                self.settings = self.settings.model_copy(update={"enabled": True})
                self._save_settings()

            if not self.settings.enabled:
                await self._broadcast_status()
                return False

            token = self.settings.effective_token
            if not token:
                self._last_error = "Bot token is not configured."
                await self._broadcast_status()
                return False

            if self.running and self._client is not None:
                return True

            client = self._client_factory(token)
            try:
                me = await client.get_me()
            except TelegramError as exc:
                self._last_error = f"Telegram authentication failed: {exc.description}"
                await client.close()
                await self._broadcast_status()
                return False

            username = me.get("username") if isinstance(me, dict) else None
            if username and username != self.settings.bot_username:
                self.settings = self.settings.model_copy(update={"bot_username": username})
                self._save_settings()

            self._client = client
            self.delivery.prepare_reconnect()
            self.store.reset_sending_notifications()
            self._subscribe()
            self._started_at = self._started_at or now_iso()
            self._last_error = None
            self._poll_task = asyncio.create_task(self._poll_loop(), name="echo-remote-poll")
            self._notify_task = asyncio.create_task(self._notification_loop(), name="echo-remote-delivery")
            self.store.set_state("relay_connected", "false")
            await self._broadcast_status()
            return True

    async def stop(self, disable: bool = True) -> None:
        async with self._start_lock:
            if disable and self.settings.enabled:
                self.settings = self.settings.model_copy(update={"enabled": False})
                self._save_settings()
            await self._cancel_task(self._poll_task)
            await self._cancel_task(self._notify_task)
            self._poll_task = None
            self._notify_task = None
            if self._client is not None:
                await self._client.close()
                self._client = None
            self._connected = False
            self._polling = False
            self.store.set_state("relay_connected", "false")
            self._unsubscribe()
        await self._broadcast_status()

    async def _cancel_task(self, task: Optional[asyncio.Task]) -> None:
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    # ------------------------------------------------------------------ #
    # Settings and users
    # ------------------------------------------------------------------ #

    async def update_settings(self, updates: Dict[str, Any]) -> RemoteSettings:
        current = self.settings.model_dump()
        structural = False

        for key, value in updates.items():
            if key == "bot_token":
                token = str(value or "").strip()
                structural = True
                current["bot_token"] = token
                current["bot_username"] = None if not token else current.get("bot_username")
                continue
            if key == "owner_user_id":
                try:
                    owner = int(value) if value not in (None, "", 0) else None
                except (TypeError, ValueError):
                    raise ValueError("owner_user_id must be a numeric Telegram user id")
                current["owner_user_id"] = owner
                continue
            if key == "allowed_user_ids":
                current["allowed_user_ids"] = value or []
                continue
            if key in RemoteSettings.model_fields:
                current[key] = value

        if "enabled" in updates:
            structural = True

        try:
            new_settings = RemoteSettings(**current)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        old_owner = self.settings.owner_user_id
        identity_changed = new_settings.owner_user_id != old_owner
        self.settings = new_settings
        self._save_settings()
        self._sync_users()

        if identity_changed:
            if old_owner and old_owner != new_settings.owner_user_id:
                self.store.remove_user(old_owner)
            if new_settings.owner_user_id:
                self.store.upsert_user(
                    new_settings.owner_user_id,
                    username=new_settings.owner_username,
                    display_name=new_settings.owner_display_name or "Owner",
                    role="owner",
                    added_by="settings",
                )

        if structural and self.running:
            await self.stop(disable=False)
            await self.start(enable=False)
        elif new_settings.enabled and not self.running:
            await self.start(enable=False)

        await self._broadcast_status()
        return self.settings

    def _sync_users(self) -> None:
        """Mirror the allowed-user list into rows for display/audit."""
        users = {int(u["telegram_id"]): u for u in self.store.list_users()}
        owner_id = self.settings.effective_owner_id
        wanted = set(self.settings.allowed_user_ids)
        if owner_id:
            wanted.discard(owner_id)
        for telegram_id in wanted:
            if telegram_id not in users or users[telegram_id]["role"] != "allowed":
                self.store.upsert_user(
                    telegram_id,
                    username=users.get(telegram_id, {}).get("username"),
                    display_name=users.get(telegram_id, {}).get("display_name") or f"Allowed {telegram_id}",
                    role="allowed",
                    added_by="settings",
                )
        for telegram_id, user in users.items():
            if telegram_id == owner_id:
                continue
            if user["role"] == "allowed" and telegram_id not in wanted:
                self.store.remove_user(telegram_id)

    async def add_allowed_user(self, telegram_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        if telegram_id <= 0:
            raise ValueError("Telegram user id must be positive")
        if telegram_id == self.settings.effective_owner_id:
            raise ValueError("The owner is already authorized")
        allowed = list(self.settings.allowed_user_ids)
        if telegram_id not in allowed:
            allowed.append(telegram_id)
        self.settings = self.settings.model_copy(update={"allowed_user_ids": allowed})
        self._save_settings()
        user = self.store.upsert_user(
            telegram_id,
            username=username,
            display_name=username or f"Allowed {telegram_id}",
            role="allowed",
            added_by="desktop",
        )
        await self._broadcast_status()
        return user

    async def remove_user(self, telegram_id: int) -> bool:
        if telegram_id == self.settings.effective_owner_id:
            self.settings = self.settings.model_copy(
                update={
                    "owner_user_id": None,
                    "owner_username": None,
                    "owner_display_name": None,
                    "allowed_user_ids": [u for u in self.settings.allowed_user_ids if u != telegram_id],
                }
            )
            self._save_settings()
        else:
            allowed = [u for u in self.settings.allowed_user_ids if u != telegram_id]
            self.settings = self.settings.model_copy(update={"allowed_user_ids": allowed})
            self._save_settings()
        removed = self.store.remove_user(telegram_id)
        await self._broadcast_status()
        return removed

    # ------------------------------------------------------------------ #
    # Pairing
    # ------------------------------------------------------------------ #

    async def start_pairing(self) -> Dict[str, Any]:
        ttl = self.settings.pairing_ttl_seconds
        code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
        self.store.cancel_pairing()
        expires = self.store.create_pairing(hash_pairing_code(code), ttl)
        self.store.set_state("pairing_expires_at", expires)
        await self._broadcast_status()
        return {
            "code": code,
            "expires_at": expires,
            "ttl_seconds": ttl,
            "bot_username": self.settings.bot_username,
            "instructions": (
                f"Send /pair {code} to @{self.settings.bot_username}"
                if self.settings.bot_username
                else f"Send /pair {code} to your ECHO bot"
            ),
        }

    async def cancel_pairing(self) -> None:
        self.store.cancel_pairing()
        self.store.set_state("pairing_expires_at", "")
        await self._broadcast_status()

    async def _pair_attempt_allowed(self, telegram_id: int) -> bool:
        window = self.settings.pairing_attempt_window_seconds
        cutoff = datetime.now(timezone.utc).timestamp() - window
        attempts = self._pair_attempts[telegram_id]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) < self.settings.pairing_attempt_limit

    def _record_pair_failure(self, telegram_id: int) -> None:
        self._pair_attempts[telegram_id].append(datetime.now(timezone.utc).timestamp())

    def _clear_pair_attempts(self, telegram_id: int) -> None:
        self._pair_attempts.pop(telegram_id, None)

    async def _cmd_pair(self, message: IncomingMessage, code: str) -> CommandResponse:
        if not await self._pair_attempt_allowed(message.user_id):
            return CommandResponse("Too many pairing attempts. Try again later.")
        cleaned = code.strip().upper()
        if not cleaned:
            return CommandResponse("Usage: /pair <code> (generate the code in ECHO → Remote Relay)")
        code_hash = hash_pairing_code(cleaned)
        record = self.store.get_pairing(code_hash)
        if record is None or record.get("used_at"):
            self._record_pair_failure(message.user_id)
            return CommandResponse("Pairing code is invalid or has already been used.")

        if not self.store.consume_pairing(code_hash, message.user_id):
            self._record_pair_failure(message.user_id)
            return CommandResponse("Pairing code is invalid or expired.")

        old_owner = self.settings.owner_user_id
        allowed = [u for u in self.settings.allowed_user_ids if u != message.user_id]
        self.settings = self.settings.model_copy(
            update={
                "owner_user_id": message.user_id,
                "owner_username": message.username,
                "owner_display_name": message.display_name,
                "allowed_user_ids": allowed,
            }
        )
        self._save_settings()
        if old_owner and old_owner != message.user_id:
            self.store.remove_user(old_owner)
        self.store.upsert_user(
            message.user_id,
            username=message.username,
            display_name=message.display_name,
            role="owner",
            added_by="pairing",
        )
        self._clear_pair_attempts(message.user_id)
        self.store.set_state("pairing_expires_at", "")
        await self._broadcast_status()
        logger.info("Telegram owner paired: %d", message.user_id)
        return CommandResponse(
            "<b>PAIRING COMPLETE</b>\n"
            "This Telegram account is now the ECHO owner.\n"
            "Try /status. Dangerous actions still require explicit approval."
        )

    # ------------------------------------------------------------------ #
    # Status and payloads
    # ------------------------------------------------------------------ #

    def _relay_state(self) -> Dict[str, Any]:
        return {
            "connected": self._connected,
            "running": self.running,
            "polling": self._polling,
            "last_error": self._last_error,
            "reconnect_attempts": self._reconnect_attempts,
        }

    def status(self) -> Dict[str, Any]:
        remote_status = build_status(self.settings, self.store, self._relay_state())
        pairing_expires = self.store.get_state("pairing_expires_at") or ""
        active_pairing = bool(pairing_expires) and pairing_expires > now_iso()
        return {
            "enabled": self.settings.enabled,
            "running": self.running,
            "connected": self._connected,
            "polling": self._polling,
            "paused": self.settings.paused,
            "pause_reason": self.settings.pause_reason,
            "bot_username": self.settings.bot_username,
            "token_configured": bool(self.settings.effective_token),
            "started_at": self._started_at,
            "last_error": self._last_error,
            "reconnect_attempts": self._reconnect_attempts,
            "last_heartbeat_at": remote_status.get("last_heartbeat_at"),
            "heartbeat_age_seconds": remote_status.get("last_heartbeat_age_seconds"),
            "active_pairing": active_pairing,
            "pairing_expires_at": pairing_expires if active_pairing else None,
            "settings": self.settings.public_dict(),
            "relay": remote_status.get("relay"),
            "remote_status": remote_status,
            "queue": self.store.notification_stats(),
            "users": self.store.list_users(),
            "pending_actions": self.store.list_pending_actions("pending"),
            "listener": {
                "transport": "telegram_long_poll",
                "inbound_ports": 0,
                "screenshots_owner_only": True,
            },
        }

    def settings_payload(self) -> Dict[str, Any]:
        return {
            "settings": self.settings.public_dict(),
            "defaults": RemoteSettings().public_dict(),
            "status": self.status(),
        }

    async def status_event(self) -> Dict[str, Any]:
        return {"type": "remote_status", **self.status()}

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        try:
            await manager.broadcast(payload)
        except Exception as exc:  # pragma: no cover - transport failure
            logger.debug("Remote broadcast failed: %s", exc)

    async def _broadcast_status(self) -> None:
        await self._broadcast(await self.status_event())

    async def handle_ws_command(self, msg_type: str, data: Dict[str, Any]) -> None:
        if msg_type == "remote_status_request":
            await self._broadcast_status()
        elif msg_type == "remote_start":
            await self.start()
        elif msg_type == "remote_stop":
            await self.stop()
        elif msg_type == "remote_pause":
            await self.pause(data.get("reason"))
        elif msg_type == "remote_resume":
            await self.resume()
        else:
            logger.debug("Unhandled remote websocket command: %s", msg_type)

    # ------------------------------------------------------------------ #
    # Event bus
    # ------------------------------------------------------------------ #

    def _subscribe(self) -> None:
        if self._subscribed:
            return
        bus = get_event_bus()
        for topic in ("monitor_alert", "monitor_recovered", "monitor_event", "approval_request", "task_updated"):
            bus.subscribe(topic, self._bus_handler)
        get_permission_manager().add_resolution_listener(self._approval_listener)
        self._subscribed = True

    def _unsubscribe(self) -> None:
        if not self._subscribed:
            return
        bus = get_event_bus()
        for topic in ("monitor_alert", "monitor_recovered", "monitor_event", "approval_request", "task_updated"):
            bus.unsubscribe(topic, self._bus_handler)
        get_permission_manager().remove_resolution_listener(self._approval_listener)
        self._subscribed = False

    def _on_approval_resolved(self, request) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._execute_local_resolution(request))

    async def _execute_local_resolution(self, request) -> None:
        """Execute a remote-originated action approved from the desktop UI."""
        pending = self.store.get_pending_action(request.id)
        if not pending or pending.get("status") != "pending":
            return
        owner_id = self.settings.effective_owner_id
        if not owner_id or int(pending["telegram_id"]) != int(owner_id):
            self.store.set_pending_action_status(request.id, "denied", "owner mismatch")
            return

        if request.status == "denied":
            self.store.set_pending_action_status(request.id, "denied", "denied in desktop")
            if pending.get("task_id"):
                self.store.update_remote_task(pending["task_id"], status="cancelled", result="Denied by owner")
                self._update_local_task(pending["task_id"], "cancelled")
                await self._publish_task(pending["task_id"], "cancelled")
            self.notifications.enqueue(
                category="system",
                severity="warning",
                title="REMOTE ACTION DENIED",
                message=f"{pending['tool_name']} was denied in the desktop UI.",
                dedupe_key=f"approval-result:{request.id}",
            )
            await self._broadcast_status()
            return

        if request.status != "approved":
            return

        self.store.set_pending_action_status(request.id, "approved")
        try:
            arguments = json.loads(pending["arguments"] or "{}")
            result = await get_tool_registry().execute(
                pending["tool_name"], arguments, approval_id=request.id
            )
        except Exception as exc:
            result = None
            error = str(exc)
        else:
            error = result.error if result else "unknown error"

        if result is not None and result.success:
            self.store.set_pending_action_status(request.id, "executed", "success")
            if pending.get("task_id"):
                self.store.update_remote_task(pending["task_id"], status="completed", result="Action executed")
                self._update_local_task(pending["task_id"], "completed")
                await self._publish_task(pending["task_id"], "completed")
            self.notifications.enqueue(
                category="system",
                severity="info",
                title="REMOTE ACTION EXECUTED",
                message=f"{pending['tool_name']} was approved and executed from the desktop.",
                dedupe_key=f"approval-result:{request.id}",
            )
        else:
            self.store.set_pending_action_status(request.id, "executed", error or "failed")
            if pending.get("task_id"):
                self.store.update_remote_task(pending["task_id"], status="failed", error=error)
                self._update_local_task(pending["task_id"], "failed")
                await self._publish_task(pending["task_id"], "failed")
            self.notifications.enqueue(
                category="system",
                severity="warning",
                title="REMOTE ACTION FAILED",
                message=f"{pending['tool_name']} was approved but failed: {error}",
                dedupe_key=f"approval-result:{request.id}",
            )
        await self._broadcast_status()

    async def _on_bus_event(self, event: Event) -> None:
        if not self.settings.enabled or not self.settings.effective_owner_id:
            return
        before = self.store.notification_stats().get("queued", 0)
        await self.notifications.handle_bus_event(event.topic, event.payload)
        after = self.store.notification_stats().get("queued", 0)
        if after > before:
            await self._broadcast(
                {
                    "type": "remote_notification_queued",
                    "topic": event.topic,
                    "queue_size": after,
                }
            )

    # ------------------------------------------------------------------ #
    # Long polling and delivery
    # ------------------------------------------------------------------ #

    async def _poll_loop(self) -> None:
        client = self._client
        if client is None:
            return
        offset = int(self.store.get_state("update_offset", "0") or 0)
        backoff = 2
        offline_since: Optional[datetime] = None

        while True:
            try:
                updates = await client.get_updates(offset, self.settings.poll_timeout_seconds)
            except asyncio.CancelledError:
                raise
            except TelegramError as exc:
                self._polling = False
                self._connected = False
                self.store.set_state("relay_connected", "false")
                self._last_error = exc.description
                self._reconnect_attempts += 1
                if offline_since is None:
                    offline_since = datetime.now(timezone.utc)
                    self.store.set_state("offline_since", offline_since.isoformat())
                    await self._broadcast_status()
                await asyncio.sleep(backoff)
                backoff = min(self.settings.reconnect_max_seconds, backoff * 2)
                continue
            except Exception as exc:
                self._polling = False
                self._connected = False
                self._last_error = f"Relay loop error: {type(exc).__name__}"
                self._reconnect_attempts += 1
                if offline_since is None:
                    offline_since = datetime.now(timezone.utc)
                    self.store.set_state("offline_since", offline_since.isoformat())
                    await self._broadcast_status()
                await asyncio.sleep(backoff)
                backoff = min(self.settings.reconnect_max_seconds, backoff * 2)
                continue

            was_offline = offline_since is not None
            if not self._connected:
                self._connected = True
                self.store.set_state("relay_connected", "true")
                if was_offline:
                    downtime = int((datetime.now(timezone.utc) - offline_since).total_seconds())
                    suppressed = self.delivery.prepare_reconnect()
                    self.notifications.enqueue_connectivity(
                        back_online=True, downtime_seconds=downtime, suppressed=suppressed
                    )
                    await self._broadcast_status()
            offline_since = None
            self._polling = True
            self._reconnect_attempts = 0
            self._last_error = None
            backoff = 2

            stamp = now_iso()
            self.store.set_state("last_poll_at", stamp)
            self.store.set_state("last_heartbeat_at", stamp)
            self.store.set_state("update_offset", str(offset))
            self.store.expire_pending_actions()

            for update in updates:
                offset = max(offset, update.update_id + 1)
                self.store.set_state("update_offset", str(offset))
                try:
                    await self.handle_message(update, client)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Remote message handling failed: %s", exc)

            if not updates:
                await asyncio.sleep(0.2)

    async def _notification_loop(self) -> None:
        while True:
            try:
                owner_id = self.settings.effective_owner_id
                client = self._client
                if self._connected and owner_id and client is not None:
                    before = self.store.notification_stats().get("queued", 0)
                    sent, failed = await self.delivery.flush_once(client, owner_id)
                    if sent or failed:
                        await self._broadcast(
                            {
                                "type": "remote_delivery",
                                "sent": sent,
                                "failed": failed,
                                "queue_size": max(0, before - sent),
                            }
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = f"Delivery loop error: {type(exc).__name__}"
                logger.error("Remote notification loop error: %s", exc)
            await asyncio.sleep(3)

    # ------------------------------------------------------------------ #
    # Authorization
    # ------------------------------------------------------------------ #

    def role_for(self, telegram_id: int) -> Optional[str]:
        if telegram_id <= 0:
            return None
        owner_id = self.settings.effective_owner_id
        if owner_id and telegram_id == owner_id:
            return "owner"
        user = self.store.get_user(telegram_id)
        if user and user.get("role") == "owner":
            return "owner"
        if telegram_id in self.settings.allowed_user_ids:
            return "allowed"
        if user and user.get("role") == "allowed":
            return "allowed"
        return None

    # ------------------------------------------------------------------ #
    # Message handling
    # ------------------------------------------------------------------ #

    async def handle_message(self, message: IncomingMessage, client: Optional[TelegramClient] = None) -> None:
        client = client or self._client
        if client is None:
            return
        if not message.is_private:
            await self._safe_send(client, message.chat_id, "ECHO only accepts private Telegram messages.")
            return

        text = message.text.strip()
        if not text:
            return
        command, args = self._parse(text)

        if not await self._rate_allowed(message.user_id, command):
            audit_id = self.store.start_command(
                telegram_id=message.user_id,
                username=message.username,
                command=command,
                args={"text": args[:200]},
            )
            self.store.finish_command(
                audit_id, status="rate_limited", error="command rate limit exceeded"
            )
            await self._safe_send(
                client, message.chat_id, "Rate limit exceeded. Wait a minute and try again."
            )
            await self._broadcast(
                {
                    "type": "remote_command",
                    "command": {
                        "id": audit_id,
                        "telegram_id": message.user_id,
                        "command": command,
                        "status": "rate_limited",
                        "created_at": now_iso(),
                    },
                }
            )
            return

        role = self.role_for(message.user_id)
        if command == "/pair":
            audit_id = self.store.start_command(
                telegram_id=message.user_id,
                username=message.username,
                command=command,
                args={"text": args[:200]},
            )
            response = await self._cmd_pair(message, args)
            status = "ok" if "COMPLETE" in response.text else "pair_failed"
            await self._send_response(
                client, message, response, role or "unpaired", command, audit_id, status=status
            )
            return

        if command in ("/start", "/help") and role is None:
            response = CommandResponse(self._pairing_help())
            await self._send_response(client, message, response, "unpaired", command)
            return

        if role is None:
            audit_id = self.store.start_command(
                telegram_id=message.user_id,
                username=message.username,
                command=command,
                args={"text": args[:500]},
            )
            self.store.finish_command(audit_id, status="rejected", error="unauthorized")
            await self._safe_send(
                client,
                message.chat_id,
                "This Telegram account is not authorized for ECHO. "
                "Generate a pairing code in ECHO → Remote Relay, then send /pair CODE.",
            )
            await self._broadcast(
                {
                    "type": "remote_command",
                    "command": {
                        "telegram_id": message.user_id,
                        "command": command,
                        "status": "rejected",
                        "created_at": now_iso(),
                    },
                }
            )
            return

        audit_id = self.store.start_command(
            telegram_id=message.user_id,
            username=message.username,
            command=command,
            args={"text": args[:2000], "role": role},
        )
        try:
            self.store.touch_user(message.user_id)
            if self.settings.paused and command not in ("/status", "/health", "/resume", "/help", "/start"):
                response = CommandResponse(
                    "ECHO is paused for remote commands. Send /resume to re-enable."
                )
            elif command in ("/start", "/help"):
                response = CommandResponse(self._help_text(role))
            else:
                response = await self._dispatch(command, args, message, role, client)
            await self._send_response(client, message, response, role, command, audit_id)
        except Exception as exc:
            logger.error("Remote command %s failed: %s", command, exc)
            self.store.finish_command(audit_id, status="failed", error=str(exc))
            await self._safe_send(client, message.chat_id, "Command failed. The error was recorded in the audit log.")
            await self._broadcast(
                {
                    "type": "remote_command",
                    "command": {
                        "id": audit_id,
                        "telegram_id": message.user_id,
                        "command": command,
                        "status": "failed",
                        "error": str(exc),
                        "created_at": now_iso(),
                    },
                }
            )

    async def _rate_allowed(self, telegram_id: int, command: str) -> bool:
        if command in ("/start", "/help", "/resume"):
            return True
        recent = self.store.count_recent_commands(telegram_id, 60)
        return recent < self.settings.command_rate_limit

    async def _dispatch(
        self,
        command: str,
        args: str,
        message: IncomingMessage,
        role: str,
        client: TelegramClient,
    ) -> CommandResponse:
        if command == "/status":
            return CommandResponse(format_status(build_status(self.settings, self.store, self._relay_state())))
        if command == "/health":
            return CommandResponse(format_health(build_status(self.settings, self.store, self._relay_state())))
        if command == "/events":
            return self._cmd_events(args)
        if command == "/tasks":
            return self._cmd_tasks()
        if command == "/pause":
            return await self._cmd_pause(role, args)
        if command == "/resume":
            return await self._cmd_resume(role)
        if command == "/task":
            return await self._cmd_task(args, message, role)
        if command == "/ask":
            return await self._cmd_ask(args, message, role)
        if command == "/open":
            return await self._cmd_open(args, role, message.user_id)
        if command == "/text":
            return await self._cmd_free_text(args, message, role)
        if command == "/screenshot":
            return await self._cmd_screenshot(role)
        if command == "/pending":
            return self._cmd_pending(role)
        if command == "/approve":
            return await self._cmd_resolve(args, role, approve=True)
        if command == "/deny":
            return await self._cmd_resolve(args, role, approve=False)
        return CommandResponse(self._help_text(role))

    def _cmd_events(self, args: str) -> CommandResponse:
        try:
            limit = max(1, min(10, int(args.split()[0]))) if args.split() else 5
        except (TypeError, ValueError):
            limit = 5
        events = self._list_events(limit)
        return CommandResponse(format_events(events, limit))

    def _cmd_tasks(self) -> CommandResponse:
        tasks: List[Dict[str, Any]] = []
        try:
            with self.store.database.get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, goal, status, updated_at FROM tasks ORDER BY updated_at DESC LIMIT 10;"
                ).fetchall()
            tasks.extend(dict(row) for row in rows)
        except Exception:
            pass
        for task in self.store.list_remote_tasks(limit=10):
            tasks.append(
                {
                    "id": task["id"],
                    "goal": f"REMOTE · {task['goal']}",
                    "status": task["status"],
                    "updated_at": task["updated_at"],
                }
            )
        tasks.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return CommandResponse(format_tasks(tasks[:15]))

    async def pause(self, reason: Optional[str] = None) -> RemoteSettings:
        pause_reason = (reason or "Paused from Telegram").strip()[:200]
        self.settings = self.settings.model_copy(update={"paused": True, "pause_reason": pause_reason})
        self._save_settings()
        await self._broadcast_status()
        return self.settings

    async def resume(self) -> RemoteSettings:
        self.settings = self.settings.model_copy(update={"paused": False, "pause_reason": None})
        self._save_settings()
        await self._broadcast_status()
        return self.settings

    async def _cmd_pause(self, role: str, args: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        settings = await self.pause(args.strip() or "Paused from Telegram")
        return CommandResponse(
            f"<b>ECHO PAUSED</b>\n{esc(settings.pause_reason)}\nSend /resume to re-enable commands."
        )

    async def _cmd_resume(self, role: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        await self.resume()
        return CommandResponse("<b>ECHO RESUMED</b>\nRemote commands are enabled.")

    async def _cmd_ask(self, args: str, message: IncomingMessage, role: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Read-only account: /status, /health, /events, /tasks.")
        question = args.strip()
        if not question:
            return CommandResponse("Usage: /ask <question>")
        if CREDENTIAL_PATTERN.search(question):
            return CommandResponse("Credential and secret requests are blocked for remote access.")
        return CommandResponse(esc(await self._ask(question, message.user_id)))

    async def _cmd_free_text(self, text: str, message: IncomingMessage, role: str) -> CommandResponse:
        if CREDENTIAL_PATTERN.search(text):
            return CommandResponse("Credential and secret requests are blocked for remote access.")
        intent, value = self._detect_intent(text)
        if role == "owner":
            if intent in ("status", "storage", "screenshot", "open"):
                return await self._run_remote_task(text, message.user_id, role, explicit=False)
            return CommandResponse(esc(await self._ask(text, message.user_id)))

        if intent == "status":
            return CommandResponse(format_status(build_status(self.settings, self.store, self._relay_state())))
        if intent == "storage":
            return CommandResponse(format_health(build_status(self.settings, self.store, self._relay_state())))
        return CommandResponse(
            "Read-only account: /status, /health, /events, /tasks. "
            "Screenshots, app launching, and questions are owner-only."
        )

    async def _cmd_open(
        self,
        args: str,
        role: str,
        telegram_id: int,
        task_id: Optional[str] = None,
    ) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        app = args.strip()
        if not app:
            return CommandResponse("Usage: /open <approved app> (notepad, calculator, paint, explorer, taskmgr, cmd)")
        return await self._request_launch_approval(app, telegram_id, task_id)

    async def _request_launch_approval(self, app: str, telegram_id: int, task_id: Optional[str]) -> CommandResponse:
        manager_ = get_permission_manager()
        arguments = {"app_name_or_path": app}
        request = manager_.request_approval(
            tool_name="application.launch",
            args=arguments,
            category="application",
            description=f"Remote request to open '{app}'",
        )
        self.store.create_pending_action(
            approval_id=request.id,
            telegram_id=telegram_id,
            command="/open",
            tool_name=request.tool_name,
            arguments=arguments,
            ttl_seconds=900,
            task_id=task_id,
        )
        await self.notifications.handle_bus_event(
            "approval_request",
            {"approval": {"id": request.id, "tool_name": request.tool_name, "description": request.description}},
        )
        await self._broadcast(
            {
                "type": "remote_approval_requested",
                "approval_id": request.id,
                "tool_name": request.tool_name,
                "arguments": arguments,
            }
        )
        return CommandResponse(
            "<b>APPROVAL REQUIRED</b>\n"
            f"Tool: <b>{esc(request.tool_name)}</b>\n"
            f"Target: <b>{esc(app)}</b>\n\n"
            f"Approve in ECHO desktop, or reply <code>/approve {request.id}</code>.\n"
            f"Deny with <code>/deny {request.id}</code>. Expires in 15 minutes."
        )

    async def _cmd_screenshot(self, role: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        if not self.settings.screenshot_enabled:
            return CommandResponse("Screenshot capture is disabled in Remote Relay settings.")
        registry = get_tool_registry()
        result = await registry.execute("screen.capture_desktop", {})
        if not result.success:
            return CommandResponse(f"Screenshot failed: {esc(result.error or 'unknown error')}")
        data = result.data or {}
        raw_path = data.get("file_path")
        if not raw_path:
            return CommandResponse("Screenshot failed: capture returned no file.")
        path = self._prepare_photo(Path(raw_path))
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        size = data.get("width"), data.get("height")
        caption = f"<b>ECHO · SCREENSHOT</b>\n{stamp} · {size[0]}×{size[1]}"
        return CommandResponse(caption=caption, photo_path=path)

    def _cmd_pending(self, role: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        pending = self.store.list_pending_actions("pending")
        requests = {r.id: r for r in get_permission_manager().list_pending()}
        if not pending:
            return CommandResponse("No dangerous actions are waiting for approval.")
        lines = ["<b>ECHO · PENDING APPROVALS</b>", ""]
        for item in pending:
            alive = item["approval_id"] in requests
            lines.append(
                f"<b>{esc(item['tool_name'])}</b> · {esc(item['arguments'])}\n"
                f"<code>/approve {item['approval_id']}</code>"
                + ("" if alive else " · <i>expired</i>")
            )
        return CommandResponse("\n\n".join(lines))

    async def _cmd_resolve(self, args: str, role: str, *, approve: bool) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Owner-only command.")
        approval_id = args.strip().split()[0] if args.strip() else ""
        if not approval_id:
            return CommandResponse(f"Usage: /{'approve' if approve else 'deny'} <approval id>")
        pending = self.store.get_pending_action(approval_id)
        if pending is None or int(pending["telegram_id"]) != int(self.settings.effective_owner_id or 0):
            return CommandResponse("Approval request not found.")
        if pending["expires_at"] <= now_iso():
            self.store.set_pending_action_status(approval_id, "expired")
            return CommandResponse("Approval request has expired. Re-run the command.")
        if pending["status"] != "pending":
            return CommandResponse(f"This action is already {pending['status']}.")

        permission = get_permission_manager()
        request = permission.get_request(approval_id)
        if request is None:
            self.store.set_pending_action_status(approval_id, "expired")
            return CommandResponse("Approval request is no longer active. Re-run the command.")

        # Mark the remote action first so the desktop resolution listener does
        # not execute it a second time.
        self.store.set_pending_action_status(approval_id, "approved" if approve else "denied")
        permission.resolve_request(approval_id, approve)
        if not approve:
            if pending.get("task_id"):
                self.store.update_remote_task(pending["task_id"], status="cancelled", result="Denied by owner")
                self._update_local_task(pending["task_id"], "cancelled")
                await self._publish_task(pending["task_id"], "cancelled")
            await self._broadcast_status()
            return CommandResponse("Action denied. Nothing was executed.")

        arguments = json.loads(pending["arguments"] or "{}")
        result = await get_tool_registry().execute(
            pending["tool_name"], arguments, approval_id=approval_id
        )
        if result.success:
            self.store.set_pending_action_status(approval_id, "executed", "success")
            if pending.get("task_id"):
                self.store.update_remote_task(pending["task_id"], status="completed", result="Action executed")
                self._update_local_task(pending["task_id"], "completed")
                await self._publish_task(pending["task_id"], "completed")
            await self._broadcast_status()
            return CommandResponse(
                f"<b>APPROVED &amp; EXECUTED</b>\nTool: {esc(pending['tool_name'])}\n"
                f"Result: {esc(result.data)}"
            )

        self.store.set_pending_action_status(approval_id, "executed", result.error or "failed")
        if pending.get("task_id"):
            self.store.update_remote_task(pending["task_id"], status="failed", error=result.error)
            self._update_local_task(pending["task_id"], "failed")
            await self._publish_task(pending["task_id"], "failed")
        await self._broadcast_status()
        return CommandResponse(f"Approved, but execution failed: {esc(result.error or 'unknown error')}")

    async def _cmd_task(self, args: str, message: IncomingMessage, role: str) -> CommandResponse:
        if role != "owner":
            return CommandResponse("Read-only account. Remote tasks are owner-only.")
        goal = args.strip()
        if not goal:
            return CommandResponse(
                "Usage: /task <goal>\n"
                "Examples: /task take a screenshot · /task tell me my available storage · "
                "/task check whether my computer is online"
            )
        return await self._run_remote_task(goal, message.user_id, role, explicit=True)

    async def _run_remote_task(
        self,
        goal: str,
        telegram_id: int,
        role: str,
        *,
        explicit: bool,
    ) -> CommandResponse:
        if CREDENTIAL_PATTERN.search(goal):
            return CommandResponse("Credential and secret requests are blocked for remote access.")
        task_id = self.store.create_remote_task(telegram_id, "/task" if explicit else "text", goal)
        self._create_local_task(task_id, goal)
        await self._publish_task(task_id, "in_progress")
        self.store.update_remote_task(task_id, status="in_progress")

        intent, value = self._detect_intent(goal)
        if intent == "status":
            status = build_status(self.settings, self.store, self._relay_state())
            text = format_status(status)
            await self._complete_task(task_id, text)
            return CommandResponse(text)
        if intent == "storage":
            text = format_health(build_status(self.settings, self.store, self._relay_state()))
            await self._complete_task(task_id, text)
            return CommandResponse(text)
        if intent == "screenshot":
            response = await self._cmd_screenshot(role)
            if response.photo_path:
                self.store.update_remote_task(
                    task_id, status="completed", result=f"Screenshot sent: {response.photo_path.name}"
                )
                self._update_local_task(task_id, "completed")
                await self._publish_task(task_id, "completed")
            else:
                await self._fail_task(task_id, response.text)
            return response
        if intent == "open":
            response = await self._cmd_open(value, role, telegram_id, task_id=task_id)
            self.store.update_remote_task(
                task_id, status="in_progress", result="Waiting for approval"
            )
            return response

        answer = await self._ask(goal, telegram_id)
        if answer.startswith("ECHO could not complete"):
            await self._fail_task(task_id, answer)
            return CommandResponse(answer)
        await self._complete_task(task_id, answer)
        return CommandResponse(f"<b>TASK COMPLETE</b>\n\n{esc(answer)}")

    async def _complete_task(self, task_id: str, result: str) -> None:
        self.store.update_remote_task(task_id, status="completed", result=result[:4000])
        self._update_local_task(task_id, "completed")
        await self._publish_task(task_id, "completed")

    async def _fail_task(self, task_id: str, error: str) -> None:
        self.store.update_remote_task(task_id, status="failed", error=error[:2000])
        self._update_local_task(task_id, "failed")
        await self._publish_task(task_id, "failed")

    def _create_local_task(self, task_id: str, goal: str) -> None:
        stamp = now_iso()
        try:
            with self.store.database.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (id, conversation_id, goal, status, created_at, updated_at)
                    VALUES (?, NULL, ?, 'in_progress', ?, ?);
                    """,
                    (task_id, f"REMOTE · {goal}"[:200], stamp, stamp),
                )
        except Exception as exc:
            logger.debug("Could not mirror remote task into local tasks: %s", exc)

    def _update_local_task(self, task_id: str, status: str) -> None:
        try:
            with self.store.database.transaction() as conn:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?;",
                    (status, now_iso(), task_id),
                )
        except Exception:
            pass

    async def _publish_task(self, task_id: str, status: str) -> None:
        task = self.store.get_remote_task(task_id) or {"id": task_id, "goal": "", "status": status}
        payload = {
            "id": task_id,
            "goal": task.get("goal") or "",
            "status": status,
            "error": task.get("error"),
            "origin": "remote",
        }
        await self._broadcast({"type": "task_updated", "task": payload})
        asyncio.create_task(
            get_event_bus().publish(Event(topic="task_updated", payload={"task": payload}))
        )

    async def _ask(self, question: str, telegram_id: int) -> str:
        async def noop(_payload: Dict[str, Any]) -> None:
            return None

        try:
            result = await get_chat_turn_service().run_turn(
                conversation_id=f"remote:{telegram_id}",
                content=question,
                emit=noop,
                source="remote",
                task_key=f"remote:{telegram_id}",
            )
        except Exception as exc:
            logger.error("Remote ask failed: %s", exc)
            return f"ECHO could not complete the request: {type(exc).__name__}."
        if result.error:
            return f"ECHO could not complete the request: {result.error}"
        return result.content.strip() or "ECHO returned an empty response."

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _parse(self, text: str) -> tuple[str, str]:
        if not text.startswith("/"):
            return "/text", text
        head, _, rest = text.partition(" ")
        command = head.split("@", 1)[0].lower()
        return command, rest.strip()

    def _help_text(self, role: str) -> str:
        commands = OWNER_COMMANDS if role == "owner" else ALLOWED_COMMANDS
        lines = [
            "<b>ECHO · REMOTE COMMANDS</b>",
            "",
            *[f"{cmd} — {desc}" for cmd, desc in commands],
            "",
            "You can also send natural language, e.g. <i>check whether my computer is online</i>.",
        ]
        if role == "owner":
            lines.append("Dangerous actions require approval before execution.")
        else:
            lines.append("This account is read-only.")
        lines.append("Credential and secret requests are always blocked.")
        return "\n".join(lines)

    def _pairing_help(self) -> str:
        bot = f"@{self.settings.bot_username}" if self.settings.bot_username else "the ECHO bot"
        return (
            "<b>ECHO · REMOTE RELAY</b>\n\n"
            f"This account is not paired with {esc(bot)}.\n"
            "Open ECHO desktop → Remote Relay → Generate pairing code, "
            "then send <code>/pair YOURCODE</code> from this chat."
        )

    def _detect_intent(self, text: str) -> tuple[str, str]:
        lower = text.lower().strip()
        if any(word in lower for word in ("screenshot", "screen shot", "screen capture", "capture screen")):
            return "screenshot", ""
        if any(word in lower for word in ("storage", "disk space", "free space", "drive space", "available space")):
            return "storage", ""
        if any(word in lower for word in ("online", "status", "alive", "up and running", "reachable")):
            return "status", ""
        match = re.search(r"\bopen\s+(.+)$", lower)
        if match:
            return "open", match.group(1).strip()
        return "ask", text

    def _list_events(self, limit: int) -> List[Dict[str, Any]]:
        try:
            from echo.monitoring.service import get_monitoring_service

            return get_monitoring_service().list_events(limit=limit)
        except Exception:
            return []

    def _prepare_photo(self, path: Path) -> Path:
        limit = self.settings.max_screenshot_mb * 1024 * 1024
        try:
            if path.stat().st_size <= limit:
                return path
        except OSError:
            return path
        try:
            from PIL import Image

            image = Image.open(path)
            for scale, quality in ((1920, 82), (1280, 74), (960, 65)):
                copy = image.copy()
                copy.thumbnail((scale, scale))
                out = path.with_name(f"{path.stem}_{scale}.jpg")
                copy.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
                if out.stat().st_size <= limit:
                    return out
            return out
        except Exception as exc:
            logger.warning("Could not compress screenshot: %s", exc)
            return path

    async def _send_response(
        self,
        client: TelegramClient,
        message: IncomingMessage,
        response: CommandResponse,
        role: str,
        command: str,
        audit_id: Optional[str] = None,
        status: str = "ok",
    ) -> None:
        error: Optional[str] = None
        try:
            if response.photo_path is not None:
                # Screenshots are only ever delivered to the verified owner.
                owner_id = self.settings.effective_owner_id
                if not owner_id or int(message.user_id) != int(owner_id):
                    raise TelegramError("Screenshot delivery is owner-only.")
                await client.send_photo(owner_id, response.photo_path, response.caption)
            if response.text:
                await client.send_message(message.chat_id, response.text)
        except TelegramError as exc:
            status = "failed"
            error = exc.description
            logger.warning("Could not deliver remote reply: %s", exc.description)
        except Exception as exc:
            status = "failed"
            error = str(exc)
            logger.warning("Could not deliver remote reply: %s", exc)

        if audit_id:
            self.store.finish_command(
                audit_id,
                status=status,
                response=response.text or response.caption or ("screenshot" if response.photo_path else ""),
                error=error,
            )
        await self._broadcast(
            {
                "type": "remote_command",
                "command": {
                    "id": audit_id,
                    "telegram_id": message.user_id,
                    "command": command,
                    "status": status,
                    "created_at": now_iso(),
                },
            }
        )

    async def _safe_send(self, client: TelegramClient, chat_id: int, text: str) -> None:
        try:
            await client.send_message(chat_id, text)
        except Exception as exc:
            logger.debug("Could not deliver remote notice: %s", exc)

    # ------------------------------------------------------------------ #
    # Desktop actions
    # ------------------------------------------------------------------ #

    async def send_test_notification(self) -> bool:
        owner_id = self.settings.effective_owner_id
        if not owner_id:
            return False
        notification_id = self.notifications.enqueue(
            category="system",
            severity="info",
            title="ECHO TEST NOTIFICATION",
            message="Remote relay is configured correctly. This message was queued from the desktop UI.",
        )
        if notification_id is None:
            return False
        if self._connected and self._client is not None:
            await self.delivery.flush_once(self._client, owner_id)
        return True

    def list_commands(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.list_commands(limit)

    def list_notifications(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.list_notifications(status=status, limit=limit)

    async def retry_notification(self, notification_id: str) -> bool:
        return self.store.retry_notification(notification_id)


_service: Optional[RemoteService] = None


def get_remote_service() -> RemoteService:
    global _service
    if _service is None:
        _service = RemoteService()
    return _service


def set_remote_service(service: Optional[RemoteService]) -> None:
    """Test seam."""
    global _service
    _service = service
