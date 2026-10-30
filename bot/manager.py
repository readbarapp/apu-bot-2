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

    def _refresh_running(self) -> None:
        self.running = any(worker.sniping for worker in self.workers.values())

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
                    "status": "needs_login",
                    "last_message": "",
                    "apple_id": None,
                    "logged_in": False,
                    "sniping": False,
                    "browser_open": False,
                }
                for item in self._started.workers
            ]
        return {
            "running": self.running,
            "test_mode": self.test_mode,
            "workers": workers,
        }

    async def _ensure_playwright(self) -> None:
        if self._playwright is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

    async def _upsert(self, profile: WorkerProfile, test_mode: bool) -> Worker:
        await self._ensure_playwright()
        existing = self.workers.get(profile.id)
        if existing:
            if not existing.sniping:
                existing.profile = profile
            existing.test_mode = test_mode
            existing._playwright = self._playwright
            return existing
        worker = self.worker_cls(
            profile,
            test_mode=test_mode,
            playwright=self._playwright,
            index=len(self.workers),
        )
        self.workers[profile.id] = worker
        return worker

    def _get(self, worker_id: str) -> Worker:
        worker = self.workers.get(worker_id)
        if not worker:
            raise EngineError("找不到這個 Worker。請先儲存設定，再登入或啟動。", 404)
        return worker

    async def login_worker(self, profile: WorkerProfile, test_mode: bool) -> dict:
        self.test_mode = test_mode
        worker = await self._upsert(profile, test_mode)
        await worker.open_login()
        return self.status()

    async def run_worker(self, profile: WorkerProfile, test_mode: bool) -> dict:
        self.test_mode = test_mode
        worker = await self._upsert(profile, test_mode)
        try:
            await worker.start_sniping()
        except RuntimeError as exc:
            raise EngineError(str(exc), 409) from exc
        self._refresh_running()
        return self.status()

    async def pause_worker(self, worker_id: str) -> dict:
        worker = self._get(worker_id)
        await worker.stop_sniping()
        self._refresh_running()
        return self.status()

    async def start(self, request: StartRequest) -> dict:
        self.test_mode = request.test_mode
        self._started = request
        hub.info("system", "前端已發出全域啟動指令")
        if request.test_mode:
            hub.info("system", "測試模式開啟：偵測到貨源時會停在最後一步，不會扣款下單")
        else:
            hub.warn("system", "真實下單模式：偵測到符合條件的貨源時將自動送出訂單並可能信用卡扣款")

        ready: list[Worker] = []
        for profile in request.workers:
            worker = await self._upsert(profile, request.test_mode)
            if not worker.apple_id and worker.context is not None:
                try:
                    await worker.refresh_account()
                except Exception as exc:
                    hub.warn(worker.profile.name, f"檢查登入狀態失敗：{exc}")
            if worker.apple_id:
                ready.append(worker)
            else:
                hub.warn(worker.profile.name, "尚未登入 Apple ID，全域啟動會跳過此 Worker")

        if not ready:
            raise EngineError("尚未有 Worker 完成 Apple ID 登入。請先撳「登入 Apple ID」，登入成功變成待命後再全域啟動。", 409)

        for worker in ready:
            try:
                await worker.start_sniping()
            except RuntimeError as exc:
                hub.warn(worker.profile.name, str(exc))

        self._refresh_running()
        await self.bring_all_to_front()
        hub.success("system", f"已開始 {sum(1 for worker in ready if worker.sniping)} 個已登入 Worker 搶購")
        return self.status()

    async def bring_all_to_front(self) -> None:
        for worker in self.workers.values():
            if worker.context is None:
                continue
            try:
                await worker.bring_to_front()
            except Exception as exc:
                hub.warn(worker.profile.name, f"無法將視窗帶到最前：{exc}")

    async def focus_worker(self, worker_id: str) -> dict:
        worker = self._get(worker_id)
        if worker.context is None:
            raise EngineError("此 Worker 目前沒有開啟的瀏覽器視窗。請先撳「登入 Apple ID」。", 409)
        await worker.bring_to_front()
        hub.info(worker.profile.name, "前端要求顯示此 Worker 視窗")
        return {"ok": True, "id": worker_id}

    async def stop(self, reason: str = "前端發出緊急停止") -> dict:
        async with self._lock:
            hub.warn("system", reason)
            workers = list(self.workers.values())
            tasks = [worker._snipe_task for worker in workers if worker._snipe_task]
            login_tasks = [worker._login_task for worker in workers if worker._login_task]
            playwright = self._playwright
            self.running = False
            self.tasks = []
            self._playwright = None

        for worker in workers:
            worker.stop_event.set()
            worker.snipe_stop.set()
        for worker in workers:
            try:
                await worker.shutdown()
            except Exception:
                pass
        pending = [task for task in tasks + login_tasks if task and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
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
