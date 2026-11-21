"""Minimal outbound-only Telegram Bot API client.

ECHO never accepts inbound network connections for remote control. The daemon
long-polls the Telegram API, so the desktop is never exposed to the internet.
The bot token is never included in logs or exception text.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("echo.remote.telegram")

MAX_MESSAGE_CHARS = 3900


class TelegramError(Exception):
    def __init__(self, description: str, error_code: Optional[int] = None, retry_after: Optional[int] = None):
        super().__init__(description)
        self.description = description
        self.error_code = error_code
        self.retry_after = retry_after


@dataclass
class IncomingMessage:
    update_id: int
    message_id: int
    chat_id: int
    user_id: int
    username: Optional[str]
    display_name: str
    text: str
    is_private: bool


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.telegram.org",
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = 40.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)

    @property
    def token_configured(self) -> bool:
        return bool(self._token)

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass

    async def _call(
        self,
        method: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        if not self._token:
            raise TelegramError("Bot token is not configured.")
        url = f"{self._base_url}/bot{self._token}/{method}"
        try:
            response = await self._client.post(
                url,
                data=payload or None,
                files=files,
                timeout=timeout or self._timeout,
            )
        except httpx.HTTPError as exc:
            # Never echo the URL: it contains the token.
            raise TelegramError(f"Telegram transport failure: {type(exc).__name__}") from None

        try:
            body = response.json()
        except ValueError:
            raise TelegramError(f"Telegram returned HTTP {response.status_code}") from None

        if not body.get("ok"):
            description = str(body.get("description") or "Telegram request failed")
            parameters = body.get("parameters") or {}
            raise TelegramError(
                description,
                error_code=body.get("error_code"),
                retry_after=parameters.get("retry_after"),
            )
        return body.get("result")

    async def get_me(self) -> Dict[str, Any]:
        return await self._call("getMe") or {}

    async def get_updates(self, offset: int, timeout_seconds: int) -> List[IncomingMessage]:
        result = await self._call(
            "getUpdates",
            payload={
                "offset": offset,
                "timeout": timeout_seconds,
                "allowed_updates": '["message"]',
            },
            timeout=timeout_seconds + 15,
        )
        messages: List[IncomingMessage] = []
        for update in result or []:
            message = update.get("message")
            if not message:
                continue
            sender = message.get("from") or {}
            chat = message.get("chat") or {}
            text = message.get("text") or ""
            if not text:
                continue
            display = " ".join(
                part
                for part in [sender.get("first_name"), sender.get("last_name")]
                if part
            ) or sender.get("username") or f"user {sender.get('id')}"
            messages.append(
                IncomingMessage(
                    update_id=int(update.get("update_id") or 0),
                    message_id=int(message.get("message_id") or 0),
                    chat_id=int(chat.get("id") or sender.get("id") or 0),
                    user_id=int(sender.get("id") or 0),
                    username=sender.get("username"),
                    display_name=display,
                    text=text.strip(),
                    is_private=chat.get("type") == "private",
                )
            )
        return messages

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
    ) -> Dict[str, Any]:
        chunks = _split_text(text)
        last: Dict[str, Any] = {}
        for chunk in chunks:
            last = await self._call(
                "sendMessage",
                payload={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": "true" if disable_preview else "false",
                },
            ) or {}
        return last

    async def send_photo(self, chat_id: int, photo_path: Path, caption: Optional[str] = None) -> Dict[str, Any]:
        path = Path(photo_path)
        if not path.exists():
            raise TelegramError("Screenshot file is missing.")
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        with path.open("rb") as handle:
            files = {"photo": (path.name, handle, mime)}
            payload: Dict[str, Any] = {"chat_id": str(chat_id)}
            if caption:
                payload["caption"] = caption[:1000]
                payload["parse_mode"] = "HTML"
            return await self._call("sendPhoto", payload=payload, files=files, timeout=90.0) or {}


def _split_text(text: str) -> List[str]:
    if len(text) <= MAX_MESSAGE_CHARS:
        return [text]
    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= MAX_MESSAGE_CHARS:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, MAX_MESSAGE_CHARS)
        if split_at < MAX_MESSAGE_CHARS // 2:
            split_at = MAX_MESSAGE_CHARS
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)
