from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from bot.account import detect_apple_id, looks_like_signin
from bot.catalogs import (
    INVENTORY_TIMEOUT_MS,
    POLL_JITTER_SECONDS,
    POLL_SECONDS,
    account_url,
    shop_home_url,
    signin_url,
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
        self.status = "needs_login"
        self.purchased = 0
        self.last_message = ""
        self.apple_id: str | None = None
        self.sniping = False
        self.context: Any = None
        self.ready_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.snipe_stop = asyncio.Event()
        self._snipe_task: asyncio.Task | None = None
        self._login_task: asyncio.Task | None = None
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
            "apple_id": self.apple_id,
            "logged_in": bool(self.apple_id),
            "sniping": self.sniping,
            "browser_open": self.context is not None,
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
        self.snipe_stop.set()
        await self._cancel_snipe()
        await self._close_browser()
        if self.status not in {"completed", "dry_run_paused", "error"}:
            self.status = "stopped"

    async def _cancel_snipe(self) -> None:
        task = self._snipe_task
        self._snipe_task = None
        self.sniping = False
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _close_browser(self) -> None:
        context = self.context
        self.context = None
        if context is None:
            return
        try:
            await context.close()
        except Exception:
            pass

    async def _page(self):
        assert self.context is not None
        if self.context.pages:
            return self.context.pages[-1]
        return await self.context.new_page()

    async def ensure_browser(self) -> None:
        if self.context is not None:
            return
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
        email = await self.refresh_account()
        if email:
            self._set("ready", f"已登入 Apple ID：{email}。待命中，等你開始運作。")
        else:
            self._set("needs_login", "瀏覽器已開，尚未登入 Apple ID。請撳「登入 Apple ID」。")

    async def refresh_account(self) -> str | None:
        if self.context is None:
            return self.apple_id
        page = await self._page()
        email = await detect_apple_id(page)
        if not email and not self.sniping:
            try:
                await page.goto(account_url(), wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
            email = await detect_apple_id(page)
        self.apple_id = email
        if email and self.status in {"needs_login", "logging_in", "idle", "launching"} and not self.sniping:
            self._set("ready", f"已登入 Apple ID：{email}。待命中，等你開始運作。")
        return email

    async def open_login(self) -> None:
        await self.ensure_browser()
        page = await self._page()
        email = await self.refresh_account()
        await self.bring_to_front()
        if email:
            hub.info(self.profile.name, f"已登入 {email}，視窗已帶到最前")
            return
        self._set("logging_in", "已打開 Apple ID 登入頁，請在瀏覽器完成登入（含 2FA）")
        try:
            await page.goto(signin_url(), wait_until="domcontentloaded", timeout=45_000)
        except Exception as exc:
            self._set("needs_login", f"無法打開登入頁：{exc}", level="warn")
            return
        await self.bring_to_front()
        if self._login_task is None or self._login_task.done():
            self._login_task = asyncio.create_task(self._watch_login(), name=f"login-{self.profile.name}")

    async def _watch_login(self) -> None:
        for _ in range(180):
            if self.stop_event.is_set() or self.sniping:
                return
            await asyncio.sleep(2)
            try:
                page = await self._page()
                if looks_like_signin(page.url):
                    continue
                email = await self.refresh_account()
            except Exception:
                continue
            if email:
                if not self.sniping:
                    self._set("ready", f"登入成功：{email}。而家係真正待命，可以開始運作或全域啟動。")
                return
        if not self.apple_id:
            self._set("needs_login", "仍未偵測到登入。可再撳「登入 Apple ID」。", level="warn")

    async def start_sniping(self) -> None:
        if not self.apple_id and self.context is not None:
            await self.refresh_account()
        if not self.apple_id:
            raise RuntimeError("尚未登入 Apple ID，不能開始搶機")
        await self.ensure_browser()
        if self.sniping:
            return
        self.snipe_stop = asyncio.Event()
        self.sniping = True
        self._snipe_task = asyncio.create_task(self._snipe_loop(), name=f"snipe-{self.profile.name}")
        self._set("watching", f"開始搶購（{self.apple_id}）")

    async def stop_sniping(self) -> None:
        self.snipe_stop.set()
        await self._cancel_snipe()
        if self.apple_id:
            self._set("ready", f"已停止運作。Apple ID {self.apple_id} 仍然登入，可隨時再開。")
        else:
            self._set("needs_login", "已停止運作，尚未登入 Apple ID。")

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

    async def _snipe_loop(self) -> None:
        try:
            blocks = 0
            while (
                not self.stop_event.is_set()
                and not self.snipe_stop.is_set()
                and self.purchased < self.profile.max_qty
            ):
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
                        self.sniping = False
                        self.status = "completed" if result.reason != "dry_run" else "dry_run_paused"
                        self._set(self.status, "已達購買數量上限，此 Worker 停止搶購", level="success")
                        return
                else:
                    self._set("watching", f"結帳未完成（{result.reason}），繼續監控", level="warn")
                await asyncio.sleep(next_poll_delay(1.2, (0.2, 0.6), self._rng))
        except asyncio.CancelledError:
            self.sniping = False
            raise
        except Exception as exc:
            self.sniping = False
            self._set("error", f"Worker 異常結束：{exc}", level="error")
        finally:
            self.sniping = False
            self.ready_event.set()

    async def run(self) -> None:
        await self.ensure_browser()
        if self.apple_id:
            await self.start_sniping()
            if self._snipe_task:
                await self._snipe_task


class RateLimited(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status
