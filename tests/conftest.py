from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.manager import manager  # noqa: E402


class DummyWorker:
    def __init__(self, profile, test_mode, playwright, index=0) -> None:
        self.profile = profile
        self.test_mode = test_mode
        self.index = index
        self.status = "idle"
        self.purchased = 0
        self.last_message = ""
        self.context = None
        self.ready_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.focused = 0

    def snapshot(self) -> dict:
        return {
            "id": self.profile.id,
            "name": self.profile.name,
            "session_dir": self.profile.session_dir,
            "sku": self.profile.sku,
            "stores": self.profile.stores,
            "pickup_window": self.profile.pickup_window,
            "max_qty": self.profile.max_qty,
            "purchased": self.purchased,
            "status": self.status,
            "last_message": self.last_message,
        }

    async def run(self) -> None:
        self.context = object()
        self.status = "watching"
        self.last_message = "dummy watching"
        self.ready_event.set()
        try:
            await self.stop_event.wait()
        except asyncio.CancelledError:
            self.status = "stopped"
            raise
        self.status = "stopped"

    async def bring_to_front(self) -> None:
        self.focused += 1

    async def shutdown(self) -> None:
        self.stop_event.set()
        self.context = None
        if self.status != "stopped":
            self.status = "stopped"


@pytest.fixture
def client(monkeypatch):
    async def fake_playwright(self) -> None:
        self._playwright = object()

    monkeypatch.setattr(type(manager), "worker_cls", DummyWorker)
    monkeypatch.setattr(type(manager), "_ensure_playwright", fake_playwright)

    from app import app

    with TestClient(app) as test_client:
        yield test_client
        if manager.running:
            test_client.post("/api/stop")
        manager.workers.clear()
        manager.tasks.clear()
        manager._started = None
        manager._playwright = None
        manager.running = False
        manager.test_mode = True
