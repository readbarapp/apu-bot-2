from __future__ import annotations

import asyncio
from typing import Any

from bot.logs import hub
from bot.models import StartRequest, WorkerProfile
from bot.worker import Worker


class EngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class BotManager:
    worker_cls = Worker

    def __init__(self) -> None:
        self.running = False
        self.test_mode = True
        self.workers: dict[str, Worker] = {}
        self.tasks: list[asyncio.Task] = []
        self._playwright: Any = None
        self._lock = asyncio.Lock()
        self._started: StartRequest | None = None

    def status(self) -> dict:
        workers = [worker.snapshot() for worker in self.workers.values()]
        if not workers and self._started:
            workers = [
                {
                    "id": item.id,
                    "name": item.name,
                    "session_dir": item.session_dir,
                    "sku": item.sku,
                    "stores": item.stores,
                    "pickup_window": item.pickup_window,
                    "max_qty": item.max_qty,
                    "purchased": 0,
                    "status": "idle",
                    "last_message": "",
                }
                for item in self._started.workers
            ]
        return {
            "running": self.running,
            "test_mode": self.test_mode,
            "workers": workers,
        }

    async def start(self, request: StartRequest) -> dict:
        async with self._lock:
            if self.running:
                raise EngineError("系統已在運行中，請先緊急停止", 409)
            self.running = True
            self.test_mode = request.test_mode
            self._started = request
            self.workers = {}
            self.tasks = []

        hub.info("system", "前端已發出全域啟動指令")
        if request.test_mode:
            hub.info("system", "測試模式開啟：偵測到貨源時會停在最後一步，不會扣款下單")
        else:
            hub.warn("system", "真實下單模式：偵測到符合條件的貨源時將自動送出訂單並可能信用卡扣款")

        try:
            await self._boot(request.workers)
        except Exception as exc:
            await self.stop(reason=f"啟動失敗：{exc}")
            raise EngineError(f"啟動失敗：{exc}", 500) from exc

        await self.bring_all_to_front()
        hub.success("system", "所有 Worker 瀏覽器視窗已嘗試帶到最前方")
        return self.status()

    async def _ensure_playwright(self) -> None:
        if self._playwright is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

    async def _boot(self, profiles: list[WorkerProfile]) -> None:
        await self._ensure_playwright()
        for index, profile in enumerate(profiles):
            worker = self.worker_cls(
                profile,
                test_mode=self.test_mode,
                playwright=self._playwright,
                index=index,
            )
            self.workers[profile.id] = worker
            self.tasks.append(asyncio.create_task(worker.run(), name=f"worker-{profile.name}"))

        async def wait_ready(worker: Worker) -> None:
            try:
                await asyncio.wait_for(worker.ready_event.wait(), timeout=45)
            except TimeoutError as exc:
                raise RuntimeError(f"{worker.profile.name} 瀏覽器啟動逾時") from exc
            if worker.status == "error":
                raise RuntimeError(worker.last_message or f"{worker.profile.name} 啟動失敗")

        await asyncio.gather(*(wait_ready(worker) for worker in self.workers.values()))

    async def bring_all_to_front(self) -> None:
        for worker in self.workers.values():
            try:
                await worker.bring_to_front()
            except Exception as exc:
                hub.warn(worker.profile.name, f"無法將視窗帶到最前：{exc}")

    async def focus_worker(self, worker_id: str) -> dict:
        worker = self.workers.get(worker_id)
        if not worker:
            raise EngineError("找不到這個 Worker", 404)
        if worker.context is None:
            raise EngineError("此 Worker 目前沒有開啟的瀏覽器視窗", 409)
        await worker.bring_to_front()
        hub.info(worker.profile.name, "前端要求顯示此 Worker 視窗")
        return {"ok": True, "id": worker_id}

    async def stop(self, reason: str = "前端發出緊急停止") -> dict:
        async with self._lock:
            hub.warn("system", reason)
            workers = list(self.workers.values())
            tasks = list(self.tasks)
            playwright = self._playwright
            self.running = False
            self.tasks = []
            self._playwright = None

        for worker in workers:
            worker.stop_event.set()
        for worker in workers:
            try:
                await worker.shutdown()
            except Exception:
                pass
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
        for worker in workers:
            if worker.status not in {"completed", "dry_run_paused", "error"}:
                worker.status = "stopped"
        hub.success("system", "已強制終止所有 Worker，並關閉全部瀏覽器實例")
        return self.status()


manager = BotManager()
