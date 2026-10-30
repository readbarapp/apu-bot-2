from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from bot.catalogs import CHECKOUT_STEP_TIMEOUT_MS, bag_url, checkout_url, product_url
from bot.inventory import StockMatch
from bot.logs import hub

PLACE_ORDER_PATTERN = re.compile(r"立即下單|下訂單|Place Your Order|Place Order", re.I)
ADD_BAG_PATTERN = re.compile(r"加入購物袋|Add to Bag|Add to Cart", re.I)
CHECKOUT_PATTERN = re.compile(r"^結帳$|^Check Out$|Checkout", re.I)
SKIP_PATTERN = re.compile(
    r"不使用折抵|不使用 iPhone 折抵|不，謝謝|暫時不加入|沒有 AppleCare|"
    r"No AppleCare|No trade-in|Skip|略過此步驟|現在不要|不加入",
    re.I,
)
CONTINUE_PATTERN = re.compile(r"^繼續$|^Continue$|繼續結帳", re.I)
PICKUP_PATTERN = re.compile(r"於 Apple Store 取貨|店內取貨|Pick up|取貨", re.I)


@dataclass
class CheckoutResult:
    ok: bool
    reason: str


async def _stopped(stop_event: asyncio.Event) -> bool:
    return stop_event.is_set()


async def _click_role(page, pattern: re.Pattern[str], timeout: int) -> bool:
    locator = page.get_by_role("button", name=pattern)
    try:
        await locator.first.wait_for(state="visible", timeout=timeout)
        await locator.first.click(timeout=timeout)
        return True
    except Exception:
        pass
    locator = page.get_by_text(pattern)
    try:
        await locator.first.wait_for(state="visible", timeout=min(timeout, 4000))
        await locator.first.click(timeout=3000)
        return True
    except Exception:
        return False


async def _maybe_click(page, pattern: re.Pattern[str], timeout: int = 2500) -> bool:
    return await _click_role(page, pattern, timeout)


async def _on_place_order_step(page) -> bool:
    if re.search(r"checkout.*(review|placeorder|namedPlaceOrder)", page.url, re.I):
        return True
    locator = page.get_by_role("button", name=PLACE_ORDER_PATTERN)
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def _select_pickup_store(page, match: StockMatch, timeout: int) -> None:
    await _maybe_click(page, PICKUP_PATTERN, timeout=timeout)
    store_pattern = re.compile(re.escape(match.store_name) + r"|" + re.escape(match.store_id), re.I)
    candidates = [
        page.get_by_text(store_pattern),
        page.locator(f'[data-store-id="{match.store_id}"]'),
        page.locator(f'input[value="{match.store_id}"]'),
    ]
    for locator in candidates:
        try:
            await locator.first.wait_for(state="visible", timeout=4000)
            await locator.first.click(timeout=3000)
            return
        except Exception:
            continue
    search = page.get_by_placeholder(re.compile(r"地區|城市|search|搜尋", re.I))
    try:
        await search.first.fill(match.store_name, timeout=3000)
        await page.keyboard.press("Enter")
        await page.get_by_text(store_pattern).first.click(timeout=5000)
    except Exception:
        hub.warn("checkout", f"未能自動點選門市 {match.store_name}，將繼續嘗試結帳步驟")


async def run_checkout(
    page,
    sku: str,
    match: StockMatch,
    test_mode: bool,
    worker_name: str,
    stop_event: asyncio.Event,
) -> CheckoutResult:
    if await _stopped(stop_event):
        return CheckoutResult(False, "stopped")

    hub.info(worker_name, f"開始搶購 {sku} @ {match.store_name}（{match.quote}）")
    await page.goto(product_url(sku), wait_until="domcontentloaded", timeout=45_000)
    if await _stopped(stop_event):
        return CheckoutResult(False, "stopped")

    deadline = asyncio.get_running_loop().time() + 45
    added = False
    while asyncio.get_running_loop().time() < deadline:
        if await _stopped(stop_event):
            return CheckoutResult(False, "stopped")
        if await _maybe_click(page, ADD_BAG_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS):
            added = True
            break
        await _maybe_click(page, SKIP_PATTERN, timeout=1800)
        if not await _on_place_order_step(page):
            await _maybe_click(page, CONTINUE_PATTERN, timeout=1500)
        await asyncio.sleep(0.4)

    if not added:
        return CheckoutResult(False, "add_to_bag_failed")

    hub.info(worker_name, "已加入購物袋，進入結帳")
    if not await _maybe_click(page, CHECKOUT_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS):
        await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)
        if not await _maybe_click(page, CHECKOUT_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS):
            await page.goto(checkout_url(), wait_until="domcontentloaded", timeout=30_000)

    step_deadline = asyncio.get_running_loop().time() + 90
    while asyncio.get_running_loop().time() < step_deadline:
        if await _stopped(stop_event):
            return CheckoutResult(False, "stopped")
        if await _on_place_order_step(page):
            break
        if re.search(r"checkout|fulfillment|pickup", page.url, re.I):
            await _select_pickup_store(page, match, timeout=4000)
        await _maybe_click(page, SKIP_PATTERN, timeout=1500)
        if not await _on_place_order_step(page):
            await _maybe_click(page, CONTINUE_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS)
        await asyncio.sleep(0.5)

    if not await _on_place_order_step(page):
        return CheckoutResult(False, "did_not_reach_place_order")

    if test_mode:
        hub.success(
            worker_name,
            f"測試模式：已停在最後確認步驟，不會送出訂單。目前頁面：{page.url}",
        )
        return CheckoutResult(True, "dry_run")

    hub.warn(worker_name, "真實下單模式：正在送出訂單")
    if not await _click_role(page, PLACE_ORDER_PATTERN, CHECKOUT_STEP_TIMEOUT_MS):
        return CheckoutResult(False, "place_order_click_failed")
    try:
        await page.wait_for_url(re.compile(r"checkout/(thankyou|status|complete)|order", re.I), timeout=20_000)
    except Exception:
        pass
    hub.success(worker_name, f"已送出訂單（或等待確認頁）。目前頁面：{page.url}")
    return CheckoutResult(True, "ordered")
