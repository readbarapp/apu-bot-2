from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from bot.catalogs import CHECKOUT_STEP_TIMEOUT_MS, bag_url, checkout_url, product_url
from bot.inventory import StockMatch, days_from_quote
from bot.logs import hub
from bot.models import GuestProfile

PLACE_ORDER_PATTERN = re.compile(r"立即下單|下訂單|Place Your Order|Place Order", re.I)
ADD_BAG_PATTERN = re.compile(r"加入購物袋|Add to Bag|Add to Cart", re.I)
NO_TRADEIN_PATTERN = re.compile(
    r"^不換購$|不使用折抵|不使用 iPhone 折抵|No trade-?in",
    re.I,
)
NO_APPLECARE_PATTERN = re.compile(
    r"無 AppleCare|沒有 AppleCare|No AppleCare|Without AppleCare",
    re.I,
)
CHECKOUT_PATTERN = re.compile(r"^結帳$|^Check Out$|Checkout", re.I)
SKIP_PATTERN = re.compile(
    r"不換購|不使用折抵|不使用 iPhone 折抵|不，謝謝|暫時不加入|"
    r"無 AppleCare|沒有 AppleCare|No AppleCare|Without AppleCare|"
    r"No trade-in|Skip|略過此步驟|現在不要|不加入",
    re.I,
)
CONTINUE_PATTERN = re.compile(r"^繼續$|^Continue$|繼續結帳", re.I)
PICKUP_PATTERN = re.compile(r"於 Apple Store 取貨|店內取貨|門市取貨|Pick up|取貨", re.I)
DELIVERY_PATTERN = re.compile(r"送貨上門|運送|送貨|Delivery|Ship|Home Delivery", re.I)
GUEST_PATTERN = re.compile(r"訪客結帳|以訪客身份|Guest Checkout|Continue as Guest", re.I)
INTERRUPT_MESSAGE = "⚠️ 偵測到頁面異常或手動干預，已自動暫停該 Worker，請手動處理後再按恢復"

FIELD_CANDIDATES = {
    "last_name": [r"姓", r"Last Name", r"lastName", r"familyName"],
    "first_name": [r"名(?!稱)", r"First Name", r"firstName", r"givenName"],
    "email": [r"電郵", r"電子郵件", r"Email"],
    "phone": [r"電話", r"手機", r"Phone", r"Mobile"],
    "address": [r"地址", r"街道", r"Address", r"Street"],
    "card_number": [r"卡號", r"信用卡", r"Card Number", r"cardNumber"],
    "card_month": [r"月", r"Month", r"expMonth"],
    "card_year": [r"年", r"Year", r"expYear"],
    "cvv": [r"安全碼", r"CVV", r"CVC", r"Security Code"],
}


class CheckoutInterrupted(Exception):
    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or INTERRUPT_MESSAGE)
        self.detail = detail or INTERRUPT_MESSAGE


@dataclass
class CheckoutResult:
    ok: bool
    reason: str
    pause: bool = False
    timings: dict[str, float] = field(default_factory=dict)
    total_seconds: float = 0.0

    def report(self) -> str:
        labels = {
            "add_bag": "Step 1 加車",
            "enter_checkout": "Step 2 進入結帳",
            "fulfillment": "Step 3 處理取貨/送貨",
            "payment": "Step 4 到達付款前最後一步",
        }
        parts = [
            f"{labels.get(name, name)} {seconds:.2f} 秒"
            for name, seconds in self.timings.items()
        ]
        joined = " → ".join(parts) if parts else "未完成計時"
        return f"效能實測報告：{joined}。總耗時 {self.total_seconds:.2f} 秒"


class StepTimer:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.last = self.started
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.marks[name] = round(now - self.last, 3)
        self.last = now

    def result(self, ok: bool, reason: str, pause: bool = False) -> CheckoutResult:
        return CheckoutResult(
            ok=ok,
            reason=reason,
            pause=pause,
            timings=dict(self.marks),
            total_seconds=round(time.perf_counter() - self.started, 3),
        )


async def _stopped(stop_event: asyncio.Event) -> bool:
    return stop_event.is_set()


def _looks_unexpected(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "timeout",
        "strict mode",
        "intercepts pointer",
        "not visible",
        "not attached",
        "target closed",
        "execution context",
        "unexpected",
    )
    return any(marker in text for marker in markers)


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


async def _click_choice(page, pattern: re.Pattern[str], timeout: int = 2500) -> bool:
    """Click a radio/label option such as 不換購 or 無 AppleCare+."""
    slice_timeout = max(700, min(timeout, 1600))
    locators = [
        page.get_by_label(pattern),
        page.get_by_role("radio", name=pattern),
        page.locator("label").filter(has_text=pattern),
        page.get_by_role("button", name=pattern),
        page.get_by_text(pattern),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=slice_timeout)
            await handle.click(timeout=slice_timeout)
            return True
        except Exception:
            continue
    return False


async def _maybe_click(page, pattern: re.Pattern[str], timeout: int = 2500) -> bool:
    return await _click_role(page, pattern, timeout)


async def _decline_tradein_and_applecare(page) -> None:
    """Apple HK iPhone PDPs keep Add to Bag disabled until both options are chosen."""
    await _click_choice(page, NO_TRADEIN_PATTERN, timeout=3500)
    await _click_choice(page, NO_APPLECARE_PATTERN, timeout=3500)


async def _click_add_to_bag(page, timeout: int = 4000) -> bool:
    locators = [
        page.get_by_role("button", name=ADD_BAG_PATTERN),
        page.locator('button[data-autom="add-to-cart"]:not(.rf-pdp-applepay-button)'),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=min(timeout, 2000))
            if not await handle.is_enabled():
                continue
            await handle.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


async def _on_place_order_step(page) -> bool:
    if re.search(r"checkout.*(review|placeorder|namedPlaceOrder)", page.url, re.I):
        return True
    locator = page.get_by_role("button", name=PLACE_ORDER_PATTERN)
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def _fill_labeled(page, patterns: list[str], value: str) -> bool:
    if not value:
        return False
    joined = re.compile("|".join(patterns), re.I)
    locators = [
        page.get_by_label(joined),
        page.get_by_placeholder(joined),
        page.locator(f"input[name*='{patterns[-1]}' i], select[name*='{patterns[-1]}' i]"),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=1800)
            tag = await handle.evaluate("el => (el.tagName || '').toLowerCase()")
            if tag == "select":
                try:
                    await handle.select_option(value=value, timeout=1500)
                except Exception:
                    await handle.select_option(label=value, timeout=1500)
            else:
                await handle.fill(value, timeout=2000)
            return True
        except Exception:
            continue
    return False


async def _fill_guest(page, guest: GuestProfile | None) -> None:
    if guest is None:
        return
    await _maybe_click(page, GUEST_PATTERN, timeout=2500)
    mapping = {
        "last_name": guest.last_name,
        "first_name": guest.first_name,
        "email": guest.email,
        "phone": guest.phone,
        "address": guest.address,
        "card_number": guest.card_number,
        "card_month": guest.card_month,
        "card_year": guest.card_year,
        "cvv": guest.cvv,
    }
    for key, value in mapping.items():
        await _fill_labeled(page, FIELD_CANDIDATES[key], value)


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


async def _click_earliest_slot(page) -> None:
    locators = [
        page.locator("input[type='radio']:visible"),
        page.get_by_role("radio"),
        page.locator("[data-timeslot], .timeslot, .time-slot, [name*='timeSlot' i]"),
        page.get_by_role("button", name=re.compile(r"上午|下午|\d{1,2}:\d{2}|AM|PM")),
    ]
    for locator in locators:
        try:
            await locator.first.wait_for(state="visible", timeout=2500)
            await locator.first.click(timeout=2000)
            return
        except Exception:
            continue


async def _delivery_days_from_page(page) -> int | None:
    try:
        text = await page.inner_text("body", timeout=3000)
    except Exception:
        return None
    return days_from_quote(text)


async def _handle_fulfillment(
    page,
    match: StockMatch,
    fulfillment: str,
    checkout_mode: str,
    guest: GuestProfile | None,
    delivery_max_days: int,
) -> str | None:
    if fulfillment == "delivery":
        await _maybe_click(page, DELIVERY_PATTERN, timeout=4000)
        if checkout_mode == "guest":
            await _fill_guest(page, guest)
        days = await _delivery_days_from_page(page)
        if days is not None and days > delivery_max_days:
            hub.warn("checkout", f"預計送達需 {days} 日，超出設定的 {delivery_max_days} 日內，放棄今次機會")
            try:
                await page.goto(product_url(match.sku), wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
            return "delivery_too_slow"
        return None

    await _select_pickup_store(page, match, timeout=4000)
    await _click_earliest_slot(page)
    if checkout_mode == "guest":
        await _fill_guest(page, guest)
    return None


async def run_checkout(
    page,
    sku: str,
    match: StockMatch,
    test_mode: bool,
    worker_name: str,
    stop_event: asyncio.Event,
    checkout_mode: str = "apple_id",
    fulfillment: str = "pickup",
    guest: GuestProfile | None = None,
    delivery_max_days: int = 7,
) -> CheckoutResult:
    timer = StepTimer()
    if await _stopped(stop_event):
        return timer.result(False, "stopped")

    try:
        where = match.store_name if fulfillment == "pickup" else f"送貨 {delivery_max_days} 日內"
        hub.info(worker_name, f"開始搶購 {sku}（{where}）")
        await page.goto(product_url(sku), wait_until="domcontentloaded", timeout=45_000)
        if await _stopped(stop_event):
            return timer.result(False, "stopped")

        hub.info(worker_name, "產品頁已開，先揀不換購同無 AppleCare+，再開加車")
        await _decline_tradein_and_applecare(page)

        deadline = asyncio.get_running_loop().time() + 45
        added = False
        while asyncio.get_running_loop().time() < deadline:
            if await _stopped(stop_event):
                return timer.result(False, "stopped")
            if await _click_add_to_bag(page, timeout=4000):
                added = True
                break
            await _decline_tradein_and_applecare(page)
            await _click_choice(page, SKIP_PATTERN, timeout=1500)
            if not await _on_place_order_step(page):
                await _maybe_click(page, CONTINUE_PATTERN, timeout=1500)
            await asyncio.sleep(0.3)

        if not added:
            return timer.result(False, "add_to_bag_failed")
        timer.mark("add_bag")

        hub.info(worker_name, "已加入購物袋，進入結帳")
        if not await _maybe_click(page, CHECKOUT_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS):
            await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)
            if not await _maybe_click(page, CHECKOUT_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS):
                await page.goto(checkout_url(), wait_until="domcontentloaded", timeout=30_000)
        timer.mark("enter_checkout")

        step_deadline = asyncio.get_running_loop().time() + 90
        fulfillment_done = False
        while asyncio.get_running_loop().time() < step_deadline:
            if await _stopped(stop_event):
                return timer.result(False, "stopped")
            if await _on_place_order_step(page):
                break
            if re.search(r"checkout|fulfillment|pickup|shipping|guest", page.url, re.I) or True:
                if not fulfillment_done:
                    skipped = await _handle_fulfillment(
                        page,
                        match,
                        fulfillment,
                        checkout_mode,
                        guest,
                        delivery_max_days,
                    )
                    fulfillment_done = True
                    timer.mark("fulfillment")
                    if skipped:
                        return timer.result(False, skipped)
            await _click_choice(page, SKIP_PATTERN, timeout=1500)
            if checkout_mode == "guest":
                await _fill_guest(page, guest)
            if not await _on_place_order_step(page):
                await _maybe_click(page, CONTINUE_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS)
            await asyncio.sleep(0.5)

        if not await _on_place_order_step(page):
            raise CheckoutInterrupted("找不到付款前最後一步，可能被新頁面或手動操作打斷")
        timer.mark("payment")

        if test_mode:
            result = timer.result(True, "dry_run")
            hub.success(worker_name, f"測試模式：已停在最後確認步驟，不會送出訂單。目前頁面：{page.url}")
            hub.success(worker_name, result.report())
            print(result.report(), flush=True)
            return result

        hub.warn(worker_name, "真實下單模式：正在送出訂單")
        if not await _click_role(page, PLACE_ORDER_PATTERN, CHECKOUT_STEP_TIMEOUT_MS):
            raise CheckoutInterrupted("未能點擊送出訂單")
        try:
            await page.wait_for_url(re.compile(r"checkout/(thankyou|status|complete)|order", re.I), timeout=20_000)
        except Exception:
            pass
        result = timer.result(True, "ordered")
        hub.success(worker_name, f"已送出訂單（或等待確認頁）。目前頁面：{page.url}")
        hub.success(worker_name, result.report())
        return result
    except asyncio.CancelledError:
        raise
    except CheckoutInterrupted as exc:
        result = timer.result(False, "interrupted", pause=True)
        hub.error(worker_name, INTERRUPT_MESSAGE)
        if exc.detail and exc.detail != INTERRUPT_MESSAGE:
            hub.error(worker_name, "請喺已帶到最前嘅視窗手動處理，完成後撳「開始運作」再繼續。")
        return result
    except Exception as exc:
        if _looks_unexpected(exc):
            result = timer.result(False, "interrupted", pause=True)
            hub.error(worker_name, INTERRUPT_MESSAGE)
            return result
        return timer.result(False, "checkout_error")
