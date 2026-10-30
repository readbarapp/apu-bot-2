from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from bot.account import detect_apple_id, has_apple_session, looks_like_signin
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


CLOSED_ERROR_MARKERS = (
    "target closed",
    "has been closed",
    "browser has been closed",
    "context or browser has been closed",
    "connection closed",
)


def session_dir_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = SESSIONS_ROOT / path
    return path


def resolve_session_dir(raw: str) -> Path:
    path = session_dir_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_browser_closed_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in CLOSED_ERROR_MARKERS)


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
        self.logged_in = False
        self.sniping = False
        self.context: Any = None
        self.ready_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.snipe_stop = asyncio.Event()
        self._snipe_task: asyncio.Task | None = None
        self._login_task: asyncio.Task | None = None
        self._closed_task: asyncio.Task | None = None
        self._closing = False
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
            "logged_in": bool(self.logged_in or self.apple_id),
            "sniping": self.sniping,
            "browser_open": self.context is not None,
            "session_path": str(session_dir_path(self.profile.session_dir)),
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
        self._closing = True
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
        self._closing = True
        context = self.context
        self.context = None
        if context is None:
            self._closing = False
            return
        try:
            await context.close()
        except Exception:
            pass
        self._closing = False

    def _schedule_browser_closed(self) -> None:
        if self._closing:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._closed_task and not self._closed_task.done():
            return
        self._closed_task = loop.create_task(self._on_browser_closed())

    async def _on_browser_closed(self) -> None:
        if self._closing:
            return
        if self.context is None and self.status == "browser_closed":
            return
        self.context = None
        was_sniping = self.sniping
        await self._cancel_snipe()
        if was_sniping:
            message = (
                "你手動關閉咗呢個 Worker 嘅瀏覽器，已自動停止搶購。"
                "登入資料仍保存在 session 資料夾。要再搶請撳「開始運作」，系統會重新打開瀏覽器。"
            )
        else:
            message = (
                "你手動關閉咗呢個 Worker 嘅瀏覽器。"
                "登入資料仍保存在 session 資料夾。要再操作請撳「登入 Apple ID」重新打開視窗。"
            )
        self._set("browser_closed", message, level="warn")

    def _bind_close_watchers(self) -> None:
        context = self.context
        if context is None:
            return

        def on_context_close() -> None:
            self._schedule_browser_closed()

        def attach_page(page) -> None:
            def on_page_close() -> None:
                if self._closing:
                    return
                try:
                    pages = [item for item in context.pages if not item.is_closed()]
                except Exception:
                    pages = []
                if not pages:
                    self._schedule_browser_closed()

            page.on("close", on_page_close)

        context.on("close", on_context_close)
        context.on("page", attach_page)
        for page in list(getattr(context, "pages", []) or []):
            attach_page(page)

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
        self._bind_close_watchers()
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await page.goto(shop_home_url(), wait_until="domcontentloaded", timeout=45_000)
        self.ready_event.set()
        await self.refresh_account()
        if self.logged_in:
            label = self.apple_id or "已登入"
            self._set("ready", f"已登入 Apple ID：{label}。待命中，撳「全部開始搶機」或「開始運作」。")
        else:
            self._set("needs_login", "瀏覽器已開，尚未登入 Apple ID。請撳「登入 Apple ID」。")

    async def refresh_account(self) -> str | None:
        if self.context is None:
            return self.apple_id
        page = await self._page()
        email = await detect_apple_id(page)
        session = await has_apple_session(self.context)
        if not email and not session and not self.sniping:
            try:
                await page.goto(account_url(), wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
            email = await detect_apple_id(page)
            session = await has_apple_session(self.context)
        if email:
            self.apple_id = email
        if email or session:
            self.logged_in = True
        else:
            self.apple_id = None
            self.logged_in = False
        if self.logged_in and self.status in {"needs_login", "logging_in", "idle", "launching"} and not self.sniping:
            label = self.apple_id or "已登入"
            self._set("ready", f"已登入 Apple ID：{label}。待命中，撳「全部開始搶機」或「開始運作」。")
        return self.apple_id

    async def open_login(self) -> None:
        await self.ensure_browser()
        page = await self._page()
        email = await self.refresh_account()
        await self.bring_to_front()
        if self.logged_in:
            hub.info(self.profile.name, f"已登入 {email or 'Apple ID'}，視窗已帶到最前")
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
            if self.stop_event.is_set() or self.sniping or self.status == "browser_closed":
                return
            await asyncio.sleep(2)
            try:
                if self.context is None:
                    return
                page = await self._page()
                if looks_like_signin(page.url) and not await has_apple_session(self.context):
                    continue
                email = await self.refresh_account()
            except Exception as exc:
                if is_browser_closed_error(exc):
                    self._schedule_browser_closed()
                    return
                continue
            if self.logged_in:
                if not self.sniping:
                    label = email or self.apple_id or "已登入"
                    self._set("ready", f"登入成功：{label}。而家係真正待命，可以全部開始搶機。")
                return
        if not self.logged_in:
            self._set("needs_login", "仍未偵測到登入。可再撳「登入 Apple ID」。", level="warn")

    async def start_sniping(self) -> None:
        if not self.logged_in and not self.apple_id:
            if self.context is not None:
                await self.refresh_account()
            if not self.logged_in and not self.apple_id:
                raise RuntimeError("尚未登入 Apple ID，不能開始搶機")
        await self.ensure_browser()
        await self.refresh_account()
        if not self.logged_in and not self.apple_id:
            raise RuntimeError("尚未登入 Apple ID，不能開始搶機")
        if self.sniping:
            return
        self.snipe_stop = asyncio.Event()
        self.sniping = True
        self._snipe_task = asyncio.create_task(self._snipe_loop(), name=f"snipe-{self.profile.name}")
        label = self.apple_id or "已登入"
        self._set("watching", f"開始搶購（{label}）")

    async def stop_sniping(self) -> None:
        self.snipe_stop.set()
        await self._cancel_snipe()
        if self.logged_in or self.apple_id:
            label = self.apple_id or "已登入"
            self._set("ready", f"已暫停搶購。Apple ID {label} 仍然登入，撳「開始運作」即可再搶。")
        else:
            self._set("needs_login", "已暫停搶購，尚未登入 Apple ID。")

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
                if self.context is None:
                    await self._on_browser_closed()
                    return
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
                    if is_browser_closed_error(exc):
                        await self._on_browser_closed()
                        return
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
