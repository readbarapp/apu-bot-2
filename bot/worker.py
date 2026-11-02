from __future__ import annotations

import asyncio
import random
import re
import shutil
import time
from pathlib import Path
from typing import Any

from bot.account import detect_apple_id, has_apple_session, looks_like_signin
from bot.catalogs import (
    POLL_JITTER_SECONDS,
    POLL_SECONDS,
    account_url,
    product_url,
    shop_home_url,
    signin_url,
)
from bot.catalogs import STORE_BY_ID
from bot.checkout import INTERRUPT_MESSAGE, checkout_is_blocked, run_checkout
from bot.secrets import public_guest
from bot.inventory import (
    INVENTORY_BLOCK_PAUSE_AFTER,
    InventoryLimited,
    backoff_seconds,
    load_pickup_matches,
    next_poll_delay,
)
from bot.logs import hub
from bot.models import WorkerProfile
from bot.window import (
    bring_context_to_front,
    browser_launch_message,
    launch_stealth_context,
)

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = ROOT / "sessions"
WATCH_HEARTBEAT_POLLS = 8


def should_open_account_page(checkout_mode: str, *, sniping: bool) -> bool:
    """Guest checkout never needs /shop/account; probing it often 541/404s the IP."""
    return checkout_mode != "guest" and not sniping


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


def delete_session_dir(raw: str) -> None:
    if not str(raw or "").strip():
        return
    path = session_dir_path(raw)
    try:
        resolved = path.resolve()
        resolved.relative_to(SESSIONS_ROOT.resolve())
    except (ValueError, OSError):
        return
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)


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
            "checkout_mode": self.profile.checkout_mode,
            "fulfillment": self.profile.fulfillment,
            "delivery_max_days": self.profile.delivery_max_days,
            "guest": public_guest(self.profile.guest.model_dump()),
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
        self.context, browser_label = await launch_stealth_context(
            self._playwright, user_data_dir
        )
        hub.info(self.profile.name, browser_launch_message(browser_label))
        self._bind_close_watchers()
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await page.goto(shop_home_url(), wait_until="domcontentloaded", timeout=45_000)
        self.ready_event.set()
        if self.profile.checkout_mode == "guest":
            self._set("ready", "訪客模式：唔使登入 Apple ID。資料已備好，可以開始運作。")
            return
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
        if not email and not session and should_open_account_page(
            self.profile.checkout_mode, sniping=self.sniping
        ):
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
        if self.profile.checkout_mode == "guest":
            await self.bring_to_front()
            hub.info(self.profile.name, "訪客模式唔使登入 Apple ID。視窗已帶到最前。")
            return
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
        guest = self.profile.checkout_mode == "guest"
        if not guest:
            if not self.logged_in and not self.apple_id:
                if self.context is not None:
                    await self.refresh_account()
                if not self.logged_in and not self.apple_id:
                    raise RuntimeError("尚未登入 Apple ID，不能開始搶機")
        await self.ensure_browser()
        if not guest:
            await self.refresh_account()
            if not self.logged_in and not self.apple_id:
                raise RuntimeError("尚未登入 Apple ID，不能開始搶機")
        if self.sniping:
            return
        await self._open_product_watch_page()
        self.snipe_stop = asyncio.Event()
        self.sniping = True
        self._snipe_task = asyncio.create_task(self._snipe_loop(), name=f"snipe-{self.profile.name}")
        label = "訪客" if guest else (self.apple_id or "已登入")
        self._set(
            "watching",
            f"開始搶購（{label}）。而家喺產品頁用 fetch 查庫存，唔會整頁 refresh；有貨先加車。",
        )

    async def stop_sniping(self) -> None:
        self.snipe_stop.set()
        await self._cancel_snipe()
        if self.profile.checkout_mode == "guest":
            self._set("ready", "已暫停搶購。訪客資料仍在，撳「開始運作」即可再搶。")
        elif self.logged_in or self.apple_id:
            label = self.apple_id or "已登入"
            self._set("ready", f"已暫停搶購。Apple ID {label} 仍然登入，撳「開始運作」即可再搶。")
        else:
            self._set("needs_login", "已暫停搶購，尚未登入 Apple ID。")

    async def _open_product_watch_page(self) -> None:
        """Stay on the Duo/iPhone PDP so inventory fetch looks like the storefront XHR."""
        page = await self._page()
        current = getattr(page, "url", "") or ""
        on_pdp = bool(re.search(r"/shop/(buy-|goto/product|product/)", current, re.I))
        blocked = checkout_is_blocked(current) or bool(re.search(r"/shop/account", current, re.I))
        if on_pdp and not blocked:
            return
        await page.goto(product_url(self.profile.sku), wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_url(
                re.compile(r"/shop/(buy-[^/]+/[^/]+/.+|product/)", re.I),
                timeout=12_000,
            )
        except Exception:
            pass
        try:
            await page.wait_for_load_state("load", timeout=8_000)
        except Exception:
            pass
        if checkout_is_blocked(getattr(page, "url", "") or ""):
            raise InventoryLimited(541)

    async def _check_inventory(self) -> list:
        await self._open_product_watch_page()
        page = await self._page()
        if self.profile.fulfillment == "delivery":
            store_ids = list(STORE_BY_ID)
            pickup_window = "3d"
        else:
            store_ids = self.profile.stores
            pickup_window = self.profile.pickup_window
        return await load_pickup_matches(
            page,
            sku=self.profile.sku,
            store_ids=store_ids,
            pickup_window=pickup_window,
        )

    async def _auto_pause(self) -> None:
        self.sniping = False
        self.snipe_stop.set()
        try:
            await self.bring_to_front()
        except Exception:
            pass
        self._set("paused", INTERRUPT_MESSAGE, level="error")

    async def _snipe_loop(self) -> None:
        try:
            blocks = 0
            polls = 0
            watch_started = time.monotonic()
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
                    polls += 1
                except InventoryLimited as exc:
                    blocks += 1
                    if blocks >= INVENTORY_BLOCK_PAUSE_AFTER:
                        self.sniping = False
                        self.snipe_stop.set()
                        try:
                            await self.bring_to_front()
                        except Exception:
                            pass
                        self._set(
                            "paused",
                            (
                                f"庫存接口連續 {blocks} 次被擋（HTTP {exc.status}）。"
                                "呢個係 Apple 風控暫時限制查詢，唔一定永久封 IP。"
                                "已自動暫停，唔好再連打。等幾分鐘再用 1 個 Worker 試。"
                            ),
                            level="error",
                        )
                        return
                    wait_for = backoff_seconds(blocks)
                    self._set(
                        "watching",
                        (
                            f"庫存接口被限制（HTTP {exc.status}，Apple 風控），"
                            f"{wait_for:.0f}s 後重試（第 {blocks}/{INVENTORY_BLOCK_PAUSE_AFTER} 次）。"
                            "唔一定永久封 IP；連續撞會越擋越實。"
                        ),
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
                    if polls == 1 or polls % WATCH_HEARTBEAT_POLLS == 0:
                        elapsed = max(1, int(time.monotonic() - watch_started))
                        self._set(
                            "watching",
                            (
                                f"正在查貨：第 {polls} 次仍暫無供應（官網 JSON 200）。"
                                f"已運作 {elapsed}s。停留產品頁用 fetch 問庫存，唔會整頁 refresh。"
                            ),
                        )
                    await asyncio.sleep(next_poll_delay(POLL_SECONDS, POLL_JITTER_SECONDS, self._rng))
                    continue

                match = matches[0]
                self._set(
                    "checking_out",
                    f"偵測到貨：{match.store_name} / {match.quote}，開始自動結帳",
                    level="success",
                )
                try:
                    remaining = max(1, self.profile.max_qty - self.purchased)
                    result = await run_checkout(
                        await self._page(),
                        sku=self.profile.sku,
                        match=match,
                        test_mode=self.test_mode,
                        worker_name=self.profile.name,
                        stop_event=self.stop_event,
                        checkout_mode=self.profile.checkout_mode,
                        fulfillment=self.profile.fulfillment,
                        guest=self.profile.guest if self.profile.checkout_mode == "guest" else None,
                        delivery_max_days=self.profile.delivery_max_days,
                        quantity=remaining,
                    )
                except Exception as exc:
                    if is_browser_closed_error(exc):
                        await self._on_browser_closed()
                        return
                    await self._auto_pause()
                    return
                if result.pause:
                    message = INTERRUPT_MESSAGE
                    if result.total_seconds or result.timings:
                        message = f"{INTERRUPT_MESSAGE} {result.report()}"
                    self.sniping = False
                    self.snipe_stop.set()
                    try:
                        await self.bring_to_front()
                    except Exception:
                        pass
                    self._set("paused", message, level="error")
                    return
                if result.ok:
                    # One worker-wide counter for every selected store combined.
                    self.purchased += max(1, result.quantity)
                    if result.reason == "dry_run":
                        done = f"測試模式完成 {self.purchased}/{self.profile.max_qty}，已停在最後一步。"
                        if result.total_seconds or result.timings:
                            done = f"{done} {result.report()}"
                        self._set(
                            "dry_run_paused" if self.purchased >= self.profile.max_qty else "watching",
                            done,
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
                        cap = "已達購買數量上限，此 Worker 停止搶購"
                        if result.total_seconds or result.timings:
                            cap = f"{cap}。{result.report()}"
                        self._set(self.status, cap, level="success")
                        return
                else:
                    leftover = f"結帳未完成（{result.reason}），繼續監控"
                    if result.total_seconds or result.timings:
                        leftover = f"{leftover}。{result.report()}"
                    self._set("watching", leftover, level="warn")
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


class RateLimited(InventoryLimited):
    """Backward-compatible alias."""
