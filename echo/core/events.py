import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Callable, Coroutine, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """In-process asynchronous event bus with topic subscriptions."""

    def __init__(self):
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._wildcard_subscribers: List[EventHandler] = []
        self._running: bool = False

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        if topic == "*":
            self._wildcard_subscribers.append(handler)
        else:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        if topic == "*" and handler in self._wildcard_subscribers:
            self._wildcard_subscribers.remove(handler)
        elif topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    async def publish(self, event: Event) -> None:
        handlers = list(self._subscribers.get(event.topic, [])) + list(
            self._wildcard_subscribers
        )
        for handler in handlers:
            try:
                res = handler(event)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False


_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus
