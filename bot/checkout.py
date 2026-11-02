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
PICKUP_PATTERN = re.compile(r"我會前來取貨|於 Apple Store 取貨|店內取貨|門市取貨|Pick up|取貨", re.I)
DELIVERY_PATTERN = re.compile(r"我希望送貨|送貨上門|運送|送貨|Delivery|Ship|Home Delivery", re.I)
GUEST_PATTERN = re.compile(
    r"以訪客身份繼續|訪客結帳|以訪客身份|Guest Checkout|Continue as Guest",
    re.I,
)
BLOCKED_URL_MARKERS = (
    "/shop/404",
    "/shop/go/404",
    "/shop/541",
    "/shop/sorry",
    "message_generic",
)
INTERRUPT_MESSAGE = "⚠️ 偵測到頁面異常或手動干預，已自動暫停該 Worker，請手動處理後再按恢復"

FIELD_CANDIDATES = {
    "last_name": [r"姓氏", r"姓", r"Last Name", r"lastName", r"familyName"],
    "first_name": [r"名字", r"名(?!稱)", r"First Name", r"firstName", r"givenName"],
    "email": [r"電郵地址", r"電郵", r"電子郵件", r"Email", r"emailAddress"],
    "phone": [r"電話號碼", r"電話", r"手機", r"Phone", r"Mobile", r"fullDaytimePhone"],
    "address": [r"街道地址", r"地址", r"街道", r"Address", r"Street"],
    "card_number": [r"卡號", r"信用卡", r"Card Number", r"cardNumber"],
    "card_month": [r"月", r"Month", r"expMonth", r"expireMonth"],
    "card_year": [r"年", r"Year", r"expYear", r"expireYear"],
    "cvv": [r"安全碼", r"CVV", r"CVC", r"Security Code"],
}
COMBINED_EXPIRY_PATTERNS = [
    r"MM\s*/\s*YY",
    r"月\s*[／/]\s*年",
    r"到期日",
    r"有效期限",
    r"Expiry Date",
    r"Expiration Date",
    r"expirationDate",
]


def card_year_yy(year: str) -> str:
    digits = re.sub(r"\D", "", year or "")
    if len(digits) >= 2:
        return digits[-2:]
    return digits


def card_year_yyyy(year: str) -> str:
    digits = re.sub(r"\D", "", year or "")
    if len(digits) == 2:
        return f"20{digits}"
    if len(digits) >= 4:
        return digits[-4:]
    return digits


def card_year_options(year: str) -> list[str]:
    """Apple HK expiry is MM/YY. Try 2-digit YY first, then 4-digit as a select fallback."""
    yy = card_year_yy(year)
    yyyy = card_year_yyyy(year)
    options: list[str] = []
    if yy:
        options.append(yy)
    if yyyy and yyyy not in options:
        options.append(yyyy)
    return options


def card_month_options(month: str) -> list[str]:
    digits = re.sub(r"\D", "", month or "")
    if not digits:
        return []
    number = int(digits)
    if number < 1 or number > 12:
        return [digits]
    padded = f"{number:02d}"
    plain = str(number)
    return [padded] if padded == plain else [padded, plain]


def mm_yy(month: str, year: str) -> str:
    months = card_month_options(month)
    yy = card_year_yy(year)
    if not months or not yy:
        return ""
    return f"{months[0]}/{yy}"


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


def checkout_is_blocked(url: str) -> bool:
    text = (url or "").lower()
    return any(marker in text for marker in BLOCKED_URL_MARKERS)


def block_report(step: str, url: str, title: str = "", extra: str = "") -> str:
    """One Live Log line the operator can paste back without reading code."""
    parts = [
        "【請複製呢段到對話】",
        f"步驟={step}",
        f"網址={url or '（無）'}",
        f"標題={title or '（無）'}",
        f"被擋頁={'是' if checkout_is_blocked(url) else '否'}",
    ]
    if extra:
        parts.append(extra)
    return "；".join(parts)


async def page_title(page) -> str:
    try:
        return str(await page.title() or "")
    except Exception:
        return ""


async def wait_if_checkout_blocked(page, timeout: int = 8000) -> bool:
    """True when add-to-bag or checkout navigated to Apple's 541/404 page."""
    try:
        await page.wait_for_url(
            re.compile(r"/shop/bag|/shop/404|/shop/go/404|/shop/541|sorry", re.I),
            timeout=timeout,
        )
    except Exception:
        pass
    return checkout_is_blocked(getattr(page, "url", "") or "")


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
    slice_timeout = max(500, min(timeout, 900))
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


async def _add_bag_enabled(page) -> bool:
    locator = page.get_by_role("button", name=ADD_BAG_PATTERN)
    try:
        if await locator.count() == 0:
            return False
        return bool(await locator.first.is_enabled())
    except Exception:
        return False


async def _decline_tradein_and_applecare(page) -> None:
    """Apple HK iPhone PDPs keep Add to Bag disabled until both options are chosen."""
    if await _add_bag_enabled(page):
        return
    await _click_choice(page, NO_TRADEIN_PATTERN, timeout=2500)
    await _click_choice(page, NO_APPLECARE_PATTERN, timeout=2500)


async def _click_visible_checkout(page, timeout: int = 8000) -> bool:
    groups = [
        page.locator('[data-autom="checkout"]'),
        page.get_by_role("button", name=CHECKOUT_PATTERN),
    ]
    for group in groups:
        try:
            count = await group.count()
        except Exception:
            continue
        for index in range(count):
            handle = group.nth(index)
            try:
                if not await handle.is_visible():
                    continue
                await handle.click(timeout=timeout)
                return True
            except Exception:
                continue
    return False


async def _continue_as_guest(page, timeout: int = 8000) -> str | None:
    """Click Apple's guest checkout button. None means continue; a string is a stop reason."""
    if checkout_is_blocked(page.url):
        return "guest_blocked"
    if not re.search(r"signIn", page.url, re.I):
        return None
    locators = [
        page.locator('[data-autom="guest-checkout-btn"]'),
        page.get_by_role("button", name=GUEST_PATTERN),
        page.get_by_role("link", name=GUEST_PATTERN),
    ]
    clicked = False
    saw_block = False

    def on_response(response) -> None:
        nonlocal saw_block
        url = response.url
        if response.status == 541 or "/shop/541" in url or "signInx" in url and response.status >= 400:
            saw_block = True

    try:
        page.on("response", on_response)
    except Exception:
        on_response = None  # type: ignore[assignment]
    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.first.click(timeout=timeout)
            clicked = True
            break
        except Exception:
            continue
    if clicked:
        try:
            await page.wait_for_url(
                re.compile(r"checkout|fulfillment|shipping|pickup|404|sorry|541", re.I),
                timeout=8_000,
            )
        except Exception:
            await asyncio.sleep(1.2)
    if on_response is not None:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    if saw_block or checkout_is_blocked(page.url) or re.search(r"signIn", page.url, re.I):
        return "guest_blocked"
    return None


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


def _fill_values(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in value if item]


async def _choose_input_value(handle, values: list[str]) -> str:
    chosen = values[0]
    try:
        maxlength = str(await handle.get_attribute("maxlength") or "")
    except Exception:
        maxlength = ""
    if maxlength == "4":
        four = next((item for item in values if len(re.sub(r"\D", "", item)) == 4), None)
        if four:
            return four
    slash = next((item for item in values if "/" in item), None)
    if slash and maxlength in {"5", "7"}:
        return slash
    return chosen


async def _apply_fill(handle, values: list[str]) -> bool:
    tag = await handle.evaluate("el => (el.tagName || '').toLowerCase()")
    if tag == "select":
        for candidate in values:
            try:
                await handle.select_option(value=candidate, timeout=1500)
                return True
            except Exception:
                try:
                    await handle.select_option(label=candidate, timeout=1500)
                    return True
                except Exception:
                    continue
        return False
    await handle.fill(await _choose_input_value(handle, values), timeout=2000)
    return True


async def _fill_labeled(page, patterns: list[str], value: str | list[str]) -> bool:
    values = _fill_values(value)
    if not values:
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
            if await _apply_fill(handle, values):
                return True
        except Exception:
            continue
    return False


async def _fill_combined_expiry(page, combined: str) -> bool:
    locators = [
        page.locator("input[autocomplete='cc-exp']"),
        page.locator("input[placeholder*='MM' i][placeholder*='YY' i]"),
        page.locator(
            "input[name*='expiration' i]:not([name*='month' i]):not([name*='year' i])"
        ),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=1200)
            await handle.fill(combined, timeout=2000)
            return True
        except Exception:
            continue
    return await _fill_labeled(page, COMBINED_EXPIRY_PATTERNS, combined)


async def _fill_card_expiry(page, month: str, year: str) -> None:
    combined = mm_yy(month, year)
    if combined and await _fill_combined_expiry(page, combined):
        return
    await _fill_labeled(page, FIELD_CANDIDATES["card_month"], card_month_options(month))
    await _fill_labeled(page, FIELD_CANDIDATES["card_year"], card_year_options(year))


async def _fill_guest(page, guest: GuestProfile | None) -> None:
    if guest is None:
        return
    mapping = {
        "last_name": guest.last_name,
        "first_name": guest.first_name,
        "email": guest.email,
        "phone": guest.phone,
        "address": guest.address,
        "card_number": guest.card_number,
        "cvv": guest.cvv,
    }
    for key, value in mapping.items():
        await _fill_labeled(page, FIELD_CANDIDATES[key], value)
    await _fill_card_expiry(page, guest.card_month, guest.card_year)


async def _select_pickup_store(page, match: StockMatch, timeout: int) -> None:
    await _click_choice(page, PICKUP_PATTERN, timeout=timeout)
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
        await _click_choice(page, DELIVERY_PATTERN, timeout=4000)
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
                if await wait_if_checkout_blocked(page):
                    hub.error(
                        worker_name,
                        block_report(
                            "加車",
                            page.url,
                            await page_title(page),
                            "加車掣已撳但跳咗 404/541，未入到購物袋。唔好連撳。可改用平時 Chrome 人手試同一款。",
                        ),
                    )
                    return timer.result(False, "add_to_bag_blocked", pause=True)
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
        if not await _click_visible_checkout(page, timeout=CHECKOUT_STEP_TIMEOUT_MS):
            await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)
            if not await _click_visible_checkout(page, timeout=CHECKOUT_STEP_TIMEOUT_MS):
                await page.goto(checkout_url(), wait_until="domcontentloaded", timeout=30_000)
        if checkout_is_blocked(page.url):
            hub.error(
                worker_name,
                block_report(
                    "進入結帳",
                    page.url,
                    await page_title(page),
                    "撳結帳之後跳咗 404/541。",
                ),
            )
            return timer.result(False, "checkout_blocked", pause=True)
        timer.mark("enter_checkout")

        if checkout_mode == "guest":
            blocked = await _continue_as_guest(page)
            if blocked:
                hub.error(
                    worker_name,
                    block_report(
                        "訪客結帳",
                        page.url,
                        await page_title(page),
                        "撳咗以訪客身份繼續之後被擋。可改用 Apple ID 模式；唔好連撳訪客。",
                    ),
                )
                return timer.result(False, blocked, pause=True)

        step_deadline = asyncio.get_running_loop().time() + 90
        fulfillment_done = False
        while asyncio.get_running_loop().time() < step_deadline:
            if await _stopped(stop_event):
                return timer.result(False, "stopped")
            if checkout_is_blocked(page.url):
                hub.error(
                    worker_name,
                    block_report("結帳途中", page.url, await page_title(page)),
                )
                return timer.result(False, "guest_blocked", pause=True)
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
