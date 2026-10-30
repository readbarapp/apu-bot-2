from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from bot.catalogs import (
    INVENTORY_TIMEOUT_MS,
    LAUNCH_STAGGER_SECONDS,
    POLL_JITTER_SECONDS,
    POLL_SECONDS,
    shop_home_url,
)
from bot.checkout import run_checkout
from bot.inventory import (
    backoff_seconds,
    is_rate_limited,
    next_poll_delay,
    parse_pickup_payload,
    pickup_url,
)
from bot.logs import hub
from bot.models import WorkerProfile
from bot.window import bring_context_to_front

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = ROOT / "sessions"


def resolve_session_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = SESSIONS_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


class Worker:
    def __init__(
        self,
        profile: WorkerProfile,
        test_mode: bool,
        playwright: Any,
        index: int = 0,
    ) -> None:
        self.profile = profile
        self.test_mode = test_mode
        self._playwright = playwright
        self.index = index
        self.status = "idle"
        self.purchased = 0
        self.last_message = ""
        self.context: Any = None
        self.ready_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self._rng = random.Random(profile.id)

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

    def _set(self, status: str, message: str, *, level: str = "info") -> None:
        self.status = status
        self.last_message = message
        getattr(hub, level if level in {"info", "warn", "error", "success"} else "info")(
            self.profile.name, message
        )

    async def bring_to_front(self) -> None:
        await bring_context_to_front(self.context)

    async def shutdown(self) -> None:
        self.stop_event.set()
        await self._close_browser()
        if self.status not in {"completed", "dry_run_paused", "error"}:
            self.status = "stopped"

    async def _close_browser(self) -> None:
        context = self.context
        self.context = None
        if context is None:
            return
        try:
            await context.close()
        except Exception:
            pass

    async def _launch(self) -> None:
        self._set("launching", "正在啟動持久化瀏覽器會話")
        user_data_dir = str(resolve_session_dir(self.profile.session_dir))
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-HK",
            timezone_id="Asia/Hong_Kong",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await page.goto(shop_home_url(), wait_until="domcontentloaded", timeout=45_000)
        self.ready_event.set()
        self._set(
            "watching",
            "瀏覽器已啟動。若尚未登入，請在此視窗登入 Apple ID，會話會保存在 session 資料夾。",
        )

    async def _check_inventory(self) -> list:
        assert self.context is not None
        url = pickup_url(self.profile.sku)
        response = await self.context.request.get(url, timeout=INVENTORY_TIMEOUT_MS)
        status = response.status
        if is_rate_limited(status):
            raise RateLimited(status)
        if status >= 400:
            raise RuntimeError(f"庫存查詢失敗 HTTP {status}")
        payload = await response.json()
        return parse_pickup_payload(
            payload,
            sku=self.profile.sku,
            store_ids=self.profile.stores,
            pickup_window=self.profile.pickup_window,
        )

    async def _page(self):
        assert self.context is not None
        if self.context.pages:
            return self.context.pages[-1]
        return await self.context.new_page()

    async def run(self) -> None:
        try:
            await asyncio.sleep(self.index * LAUNCH_STAGGER_SECONDS)
            if self.stop_event.is_set():
                self.status = "stopped"
                return
            await self._launch()
            blocks = 0
            while not self.stop_event.is_set() and self.purchased < self.profile.max_qty:
                try:
                    matches = await self._check_inventory()
                    blocks = 0
                except RateLimited as exc:
                    blocks += 1
                    wait_for = backoff_seconds(blocks)
                    self._set(
                        "watching",
                        f"庫存接口被限制（HTTP {exc.status}），{wait_for:.0f}s 後重試",
                        level="warn",
                    )
                    await asyncio.sleep(wait_for)
                    continue
                except Exception as exc:
                    self._set("watching", f"庫存查詢異常：{exc}", level="warn")
                    await asyncio.sleep(next_poll_delay(POLL_SECONDS, POLL_JITTER_SECONDS, self._rng))
                    continue

                if not matches:
                    if self.status != "watching":
                        self._set("watching", "輪詢中：尚未找到符合條件的貨源")
                    await asyncio.sleep(next_poll_delay(POLL_SECONDS, POLL_JITTER_SECONDS, self._rng))
                    continue

                match = matches[0]
                self._set(
                    "checking_out",
                    f"偵測到貨：{match.store_name} / {match.quote}，開始自動結帳",
                    level="success",
                )
                result = await run_checkout(
                    await self._page(),
                    sku=self.profile.sku,
                    match=match,
                    test_mode=self.test_mode,
                    worker_name=self.profile.name,
                    stop_event=self.stop_event,
                )
                if result.ok:
                    self.purchased += 1
                    if result.reason == "dry_run":
                        self._set(
                            "dry_run_paused" if self.purchased >= self.profile.max_qty else "watching",
                            f"測試模式完成 {self.purchased}/{self.profile.max_qty}，已停在最後一步",
                            level="success",
                        )
                    else:
                        self._set(
                            "watching",
                            f"下單成功 {self.purchased}/{self.profile.max_qty}",
                            level="success",
                        )
                    if self.purchased >= self.profile.max_qty:
                        self.status = "completed" if result.reason != "dry_run" else "dry_run_paused"
                        self._set(self.status, "已達購買數量上限，此 Worker 停止搶購", level="success")
                        return
                else:
                    self._set("watching", f"結帳未完成（{result.reason}），繼續監控", level="warn")
                await asyncio.sleep(next_poll_delay(1.2, (0.2, 0.6), self._rng))
        except asyncio.CancelledError:
            self.status = "stopped"
            raise
        except Exception as exc:
            self._set("error", f"Worker 異常結束：{exc}", level="error")
        finally:
            self.ready_event.set()
            if self.stop_event.is_set() and self.status not in {"completed", "dry_run_paused", "error"}:
                self.status = "stopped"
                await self._close_browser()


class RateLimited(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status
