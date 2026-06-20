from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import threading
import uuid
from typing import Any, Callable, Optional


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class LogEvent:
    id: str
    timestamp: str
    level: LogLevel
    source: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        level: LogLevel,
        source: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> LogEvent:
        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            source=source,
            message=message,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d


class EventBus:
    """In-memory event log with pub/sub for WebSocket streaming."""

    def __init__(self, max_events: int = 10_000) -> None:
        self._events: deque[LogEvent] = deque(maxlen=max_events)
        self._subscribers: list[Callable[[LogEvent], None]] = []
        self._lock = threading.Lock()

    def emit(
        self,
        level: LogLevel | str,
        source: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> LogEvent:
        if isinstance(level, str):
            level = LogLevel(level.upper())
        event = LogEvent.create(level, source, message, metadata)
        with self._lock:
            self._events.append(event)
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                pass
        return event

    def info(self, source: str, message: str, **metadata) -> LogEvent:
        return self.emit(LogLevel.INFO, source, message, metadata or None)

    def warn(self, source: str, message: str, **metadata) -> LogEvent:
        return self.emit(LogLevel.WARN, source, message, metadata or None)

    def error(self, source: str, message: str, **metadata) -> LogEvent:
        return self.emit(LogLevel.ERROR, source, message, metadata or None)

    def subscribe(self, callback: Callable[[LogEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[LogEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def get_logs(
        self,
        limit: int = 200,
        level: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        with self._lock:
            events = list(self._events)
        if level:
            events = [e for e in events if e.level.value == level.upper()]
        if source:
            events = [e for e in events if source.lower() in e.source.lower()]
        if search:
            q = search.lower()
            events = [e for e in events if q in e.message.lower()]
        return [e.to_dict() for e in events[-limit:]]

    def count(self) -> int:
        with self._lock:
            return len(self._events)


# Global bus — wired at app startup
event_bus = EventBus()
