from __future__ import annotations

import asyncio
import re
from collections import deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")

_PAN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_CVV = re.compile(r"(?i)\b(?:cvv|cvc|安全碼)[:\s\-]*\d{3,4}\b")
_CARD_KEY = re.compile(r"(?i)(card_number|pan|信用卡號碼)\s*[:=]\s*\S+")


def redact_message(message: str) -> str:
    text = _PAN.sub("[已隱藏卡號]", message)
    text = _CVV.sub("[已隱藏安全碼]", text)
    return _CARD_KEY.sub(r"\1=[已隱藏]", text)


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
            "message": redact_message(message),
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
