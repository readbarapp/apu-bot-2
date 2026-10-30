from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")


def _now() -> str:
    return datetime.now(HK).isoformat(timespec="seconds")


class LogHub:
    def __init__(self, history_size: int = 500) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def emit(self, worker: str | None, level: str, message: str) -> dict[str, Any]:
        item = {
            "ts": _now(),
            "worker": worker or "system",
            "level": level,
            "message": message,
        }
        self._history.append(item)
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in self._subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(item)
            except Exception:
                dead.append(queue)
        for queue in dead:
            self._subscribers.discard(queue)
        return item

    def info(self, worker: str | None, message: str) -> None:
        self.emit(worker, "info", message)

    def warn(self, worker: str | None, message: str) -> None:
        self.emit(worker, "warn", message)

    def error(self, worker: str | None, message: str) -> None:
        self.emit(worker, "error", message)

    def success(self, worker: str | None, message: str) -> None:
        self.emit(worker, "success", message)


hub = LogHub()
