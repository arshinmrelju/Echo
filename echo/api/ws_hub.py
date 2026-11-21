"""WebSocket connection hub shared by the gateway and voice subsystem."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import WebSocket

logger = logging.getLogger("echo.ws_hub")


class ConnectionManager:
    """Tracks live UI connections and broadcasts server events to all of them."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._send_locks: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        self._send_locks[websocket] = asyncio.Lock()
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self._send_locks.pop(websocket, None)
        logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def send_json(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Send one JSON frame, serialised per connection to avoid interleaving."""
        lock = self._send_locks.get(websocket)
        if lock is None:
            return
        async with lock:
            try:
                await websocket.send_text(json.dumps(data))
            except Exception:
                self.disconnect(websocket)

    async def broadcast(self, data: Dict[str, Any]) -> None:
        """Fan out a frame to every connected client; closed clients are dropped."""
        for websocket in list(self.active_connections):
            await self.send_json(websocket, data)


manager = ConnectionManager()
