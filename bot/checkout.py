from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from bot.catalogs import (
    APPLE_LOCALE,
    CHECKOUT_STEP_TIMEOUT_MS,
    PICKUP_LOCATION,
    STORE_BY_ID,
    bag_url,
    checkout_url,
    product_url,
)
from bot.inventory import StockMatch, days_from_quote
from bot.logs import hub
from bot.models import GuestProfile

PLACE_ORDER_PATTERN = re.compile(r"立即下單|下訂單|Place Your Order|Place Order", re.I)
ADD_BAG_PATTERN = re.compile(r"加入購物袋|Add to Bag|Add to Cart", re.I)
VIEW_BAG_PATTERN = re.compile(r"查看購物袋|View Bag|Review Bag", re.I)
REMOVE_BAG_PATTERN = re.compile(
    r"^移除$|^刪除$|^Remove$|從購物袋移除|Remove from Bag|Remove Item",
    re.I,
)
NO_TRADEIN_PATTERN = re.compile(
    r"^不換購$|不使用折抵|不使用 iPhone 折抵|No trade-?in",
    re.I,
)
NO_APPLECARE_PATTERN = re.compile(
    r"無 AppleCare|沒有 AppleCare|No AppleCare|Without AppleCare",
    re.I,
)
CHECKOUT_PATTERN = re.compile(r"^(結帳|Check Out|Checkout)$", re.I)
APPLE_PAY_PATTERN = re.compile(r"Apple\s*Pay", re.I)
SKIP_PATTERN = re.compile(
    r"不換購|不使用折抵|不使用 iPhone 折抵|不，謝謝|暫時不加入|"
    r"無 AppleCare|沒有 AppleCare|No AppleCare|Without AppleCare|"
    r"No trade-in|Skip|略過此步驟|現在不要|不加入",
    re.I,
)
CONTINUE_PATTERN = re.compile(
    r"繼續前往取貨詳情|繼續前往送貨詳情|繼續前往付款|繼續結帳|^繼續$|"
    r"^Continue$|Continue to Pickup|Continue to Delivery|Continue to Payment",
    re.I,
)
TIMESLOT_PATTERN = re.compile(
    r"上午|下午|\d{1,2}:\d{2}|AM|PM|時段|time\s*slot|timeslot",
    re.I,
)
REVIEW_ORDER_PATTERN = re.compile(r"檢查你的訂單|Review Your Order|Review Order", re.I)
CREDIT_CARD_PATTERN = re.compile(r"信用卡或扣帳卡|Credit or Debit Card|Credit Card", re.I)
PICKUP_PATTERN = re.compile(
    r"我會前來取貨|於 Apple Store 取貨|店內取貨|I['’]?ll pick up|Pick up at",
    re.I,
)
DELIVERY_PATTERN = re.compile(
    r"我希望送貨|I want it delivered|I['’]?d like delivery|Ship to me",
    re.I,
)
APPLY_PATTERN = re.compile(r"^套用$|^Apply$", re.I)
PICKUP_LOCATION_PATTERN = re.compile(
    r"地區|中環|城市|搜尋|search|retail|零售店|附近",
    re.I,
)
PICKUP_LOCATION_UI_PATTERN = re.compile(
    r"了解你可在哪裡取貨|地區（例如|地區\(例如|輸入地區以查看|正在顯示以下地點附近",
    re.I,
)
PICKUP_LOCATION_ERROR_PATTERN = re.compile(r"請輸入地區")
PICKUP_APPLIED_PATTERN = re.compile(r"正在顯示以下地點附近的零售店")
PICKUP_DETAILS_CONTINUE_PATTERN = re.compile(
    r"繼續前往取貨詳情|Continue to Pickup Details",
    re.I,
)
PICKUP_STORE_LIST_PATTERN = re.compile(
    r"Apple Store|ifc mall|Hysan Place|Canton Road|Festival Walk|"
    r"New Town Plaza|apm Hong Kong|取貨地點",
    re.I,
)
PICKUP_LOCATION_INPUT_SELECTORS = (
    'input[data-autom*="storelocator" i], input[data-autom*="store-locator" i], '
    'input[data-autom*="storeLocator" i]',
    'input[data-autom*="searchInput" i], input[data-autom*="search-input" i], '
    'input[data-autom*="store-search" i]',
    'input[id*="storeLocator" i], input[id*="searchInput" i], '
    'input[name*="storeLocator" i], input[name*="searchInput" i]',
    'input[placeholder*="地區"], input[placeholder*="中環"], '
    'input[aria-label*="地區" i], input[aria-label*="中環" i]',
    'input[data-autom*="location" i], input[data-autom*="city" i], '
    'input[name*="location" i], input[id*="location" i]',
    'input[data-autom*="pickup" i]',
)
PICKUP_APPLY_SELECTOR = (
    'button[data-autom*="storelocator" i], button[data-autom*="store-locator" i], '
    'button[data-autom*="search-button" i], button[data-autom*="searchButton" i], '
    '[data-autom*="storeLocator-search" i], [data-autom*="storelocator-search-button" i]'
)
GUEST_NAV_TIMEOUT_MS = 18_000
RETRY_FULFILLMENT = "retry_fulfillment"
GUEST_PATTERN = re.compile(
    r"以訪客身份繼續|訪客結帳|以訪客身份|Guest Checkout|Continue as Guest",
    re.I,
)
GUEST_BUTTON_PATTERN = re.compile(r"^以訪客身份繼續$|^Continue as Guest$", re.I)
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
    "phone": [
        r"手提電話號碼",
        r"^手提電話$",
        r"聯絡電話",
        r"Mobile Number",
        r"Phone Number",
        r"fullDaytimePhone",
    ],
    "address_street": [
        r"街道名稱及號碼",
        r"街道地址",
        r"Address Line 1",
        r"street",
        r"address1",
    ],
    "address_building": [
        r"屋苑或大廈",
        r"座數",
        r"樓層",
        r"單位",
        r"Address Line 2",
        r"address2",
    ],
    "country": [r"國家或地區", r"國家／地區", r"Country", r"countryCode"],
    "card_number": [r"卡號", r"信用卡號碼", r"Card Number", r"cardNumber"],
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


def hk_phone_number(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("852") and len(digits) >= 11:
        digits = digits[3:]
    if len(digits) > 8:
        digits = digits[-8:]
    return digits


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
    quantity: int = 1

    def report(self) -> str:
        labels = {
            "add_bag": "Step 1 加車",
            "enter_checkout": "Step 2 進入結帳",
            "fulfillment": "Step 3 處理取貨/送貨",
            "billing": "到達信用卡頁",
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

    def result(
        self,
        ok: bool,
        reason: str,
        pause: bool = False,
        quantity: int = 1,
    ) -> CheckoutResult:
        return CheckoutResult(
            ok=ok,
            reason=reason,
            pause=pause,
            timings=dict(self.marks),
            total_seconds=round(time.perf_counter() - self.started, 3),
            quantity=max(1, int(quantity or 1)),
        )

    def announce(
        self,
        worker_name: str,
        ok: bool,
        reason: str,
        pause: bool = False,
        quantity: int = 1,
        *,
        level: str = "info",
    ) -> CheckoutResult:
        """Always emit the second-count report, even if the card form cannot continue."""
        result = self.result(ok, reason, pause=pause, quantity=quantity)
        if result.timings or result.total_seconds >= 0.05:
            emit = getattr(hub, level if level in {"info", "warn", "error", "success"} else "info")
            emit(worker_name, result.report())
            print(result.report(), flush=True)
        return result


async def _stopped(stop_event: asyncio.Event) -> bool:
    return stop_event.is_set()


def checkout_is_blocked(url: str) -> bool:
    text = (url or "").lower()
    return any(marker in text for marker in BLOCKED_URL_MARKERS)


def checkout_stage(url: str) -> str:
    text = url or ""
    if re.search(r"PickupContact", text, re.I):
        return "contact"
    if re.search(r"Shipping-init|ShippingContact", text, re.I):
        return "shipping"
    if re.search(r"Billing", text, re.I):
        return "billing"
    if re.search(r"Fulfillment", text, re.I):
        return "fulfillment"
    if re.search(r"Review|placeorder|namedPlaceOrder", text, re.I):
        return "review"
    if re.search(r"signIn", text, re.I):
        return "signin"
    if re.search(r"/shop/bag", text, re.I):
        return "bag"
    if re.search(r"step=attach|/attach", text, re.I):
        return "attach"
    return "other"


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
            re.compile(
                r"/shop/bag|step=attach|/shop/404|/shop/go/404|/shop/541|sorry",
                re.I,
            ),
            timeout=timeout,
        )
    except Exception:
        pass
    return checkout_is_blocked(getattr(page, "url", "") or "")


def _response_looks_blocked(response) -> bool:
    url = getattr(response, "url", "") or ""
    status = int(getattr(response, "status", 0) or 0)
    if re.search(r"fulfillment-messages|pickup-message", url, re.I):
        return False
    if checkout_is_blocked(url):
        return True
    if status == 541 or (status >= 400 and re.search(r"add-to-cart|signInx|/shop/541", url, re.I)):
        return True
    return False


async def _open_bag(page) -> None:
    url = getattr(page, "url", "") or ""
    if checkout_stage(url) == "bag" and f"/{APPLE_LOCALE}/shop/bag" in url:
        return
    if re.search(r"/shop/bag", url, re.I) and f"/{APPLE_LOCALE}/" not in url:
        await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)
        return
    locators = [
        page.get_by_role("button", name=VIEW_BAG_PATTERN),
        page.get_by_role("link", name=VIEW_BAG_PATTERN),
        page.get_by_text(VIEW_BAG_PATTERN),
    ]
    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.first.click(timeout=4000)
            try:
                await page.wait_for_url(re.compile(r"/shop/bag", re.I), timeout=8000)
            except Exception:
                pass
            break
        except Exception:
            continue
    current = getattr(page, "url", "") or ""
    if checkout_stage(current) != "bag" or f"/{APPLE_LOCALE}/" not in current:
        await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)


def _remove_bag_locators(page):
    return [
        page.get_by_role("button", name=REMOVE_BAG_PATTERN),
        page.get_by_role("link", name=REMOVE_BAG_PATTERN),
        page.locator('[data-autom*="remove" i][data-autom*="bag" i]'),
        page.locator('[data-autom*="removeitem" i], [data-autom*="remove-item" i]'),
        page.locator('button[aria-label*="移除" i], button[aria-label*="Remove" i]'),
    ]


async def _first_remove_control(page):
    """Find a remove control without waiting; empty bag must return immediately."""
    for locator in _remove_bag_locators(page):
        try:
            if await locator.count() == 0:
                continue
            handle = locator.first
            try:
                if not await handle.is_visible():
                    continue
            except Exception:
                pass
            return handle
        except Exception:
            continue
    return None


async def _empty_bag(page) -> int:
    """Drop leftover test items so checkout does not buy 17e + Duo together."""
    try:
        await _open_bag(page)
    except Exception:
        return 0
    removed = 0
    for _ in range(12):
        handle = await _first_remove_control(page)
        if handle is None:
            break
        try:
            await handle.click(timeout=2000)
            removed += 1
            await asyncio.sleep(0.45)
        except Exception:
            break
    if removed:
        hub.info("checkout", f"已清走購物袋入面 {removed} 件舊貨，避免連測試型號一齊結帳")
    return removed


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


async def _wait_for_configured_pdp(page) -> None:
    """goto/product/SKU can briefly land on the family page before the colour/capacity URL."""
    try:
        await page.wait_for_url(
            re.compile(r"/shop/(buy-[^/]+/[^/]+/.+|product/)", re.I),
            timeout=12_000,
        )
    except Exception:
        pass
    try:
        await page.get_by_role("button", name=ADD_BAG_PATTERN).first.wait_for(
            state="visible",
            timeout=8_000,
        )
    except Exception:
        pass


async def _decline_tradein_and_applecare(page) -> None:
    """Apple HK iPhone PDPs keep Add to Bag disabled until both options are chosen."""
    if await _add_bag_enabled(page):
        return
    await _click_choice(page, NO_TRADEIN_PATTERN, timeout=2500)
    await _click_choice(page, NO_APPLECARE_PATTERN, timeout=2500)


async def _is_apple_pay_control(handle) -> bool:
    try:
        text = " ".join(
            [
                str(await handle.inner_text() or ""),
                str(await handle.get_attribute("aria-label") or ""),
                str(await handle.get_attribute("data-autom") or ""),
                str(await handle.get_attribute("class") or ""),
            ]
        )
    except Exception:
        return False
    return bool(APPLE_PAY_PATTERN.search(text))


async def _click_visible_checkout(page, timeout: int = 8000) -> bool:
    groups = [
        page.locator('[data-autom="checkout"]:not([class*="applepay" i])'),
        page.get_by_role("button", name=CHECKOUT_PATTERN),
        page.get_by_role("link", name=CHECKOUT_PATTERN),
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
                if await _is_apple_pay_control(handle):
                    continue
                await handle.click(timeout=timeout)
                return True
            except Exception:
                continue
    return False


def _guest_click_targets(root) -> list:
    """Prefer the visible blue「以訪客身份繼續」label; data-autom is optional on current Apple HK."""
    return [
        root.locator('[data-autom="guest-checkout-btn"], [data-autom="guest-checkout"], [data-autom="guestCheckout"]'),
        root.locator(
            '[id="signIn.guestLogin"], [id*="guestLogin" i], [name*="guestLogin" i], '
            '[id*="guest-checkout" i], [id*="guestCheckout" i]'
        ),
        root.get_by_role("button", name=GUEST_BUTTON_PATTERN),
        root.get_by_role("link", name=GUEST_BUTTON_PATTERN),
        root.get_by_text(GUEST_BUTTON_PATTERN),
        root.locator(
            "button:has-text('以訪客身份繼續'), a:has-text('以訪客身份繼續'), "
            "input[type='submit'][value='以訪客身份繼續'], input[type='button'][value='以訪客身份繼續']"
        ),
    ]


def _guest_page_roots(page) -> list:
    roots = [page]
    try:
        roots.extend(frame for frame in list(page.frames or []) if frame is not page)
    except Exception:
        pass
    return roots


async def _locator_is_visible(handle) -> bool:
    try:
        return bool(await handle.is_visible())
    except Exception:
        return False


async def _click_guest_button(handle, timeout: int = 2500) -> None:
    try:
        await handle.scroll_into_view_if_needed(timeout=min(timeout, 2000))
    except Exception:
        pass
    try:
        await handle.click(timeout=timeout)
        return
    except Exception:
        await handle.click(timeout=timeout, force=True)


def guest_block_extra(reason: str) -> str:
    if reason == "guest_button_missed":
        return "畫面停喺登入牆，搵唔到「以訪客身份繼續」。"
    if reason == "guest_nav_timeout":
        return "撳咗以訪客身份繼續之後頁面未跳去結帳。唔好連撳訪客。"
    return "撳咗以訪客身份繼續之後被擋。唔好連撳訪客。"


def _still_on_signin(url: str) -> bool:
    return bool(re.search(r"/shop/signIn(?:[/?#]|$)", url or "", re.I))


def _guest_nav_done(url: str) -> bool:
    text = url or ""
    if checkout_is_blocked(text):
        return True
    if _still_on_signin(text):
        return False
    return bool(re.search(r"/shop/checkout|/shop/bag|/shop/buy", text, re.I))


async def _continue_as_guest(page, timeout: int = 12000) -> str | None:
    """Click Apple's guest checkout button.

    None: left the sign-in wall. guest_clicked: clicked once, still waiting.
    Other strings are stop reasons (blocked / button missed).
    """
    if checkout_is_blocked(page.url):
        return "guest_blocked"
    if not re.search(r"signIn", page.url, re.I):
        return None
    clicked = False
    saw_block = False

    def on_response(response) -> None:
        nonlocal saw_block
        url = response.url
        if response.status == 541 or "/shop/541" in url or ("signInx" in url and response.status >= 400):
            saw_block = True

    try:
        page.on("response", on_response)
    except Exception:
        on_response = None  # type: ignore[assignment]
    deadline = asyncio.get_running_loop().time() + max(timeout / 1000, 0.05)
    while not clicked and asyncio.get_running_loop().time() < deadline:
        for root in _guest_page_roots(page):
            for locator in _guest_click_targets(root):
                try:
                    handle = locator.first
                    if not await _locator_is_visible(handle):
                        continue
                    await _click_guest_button(handle)
                    clicked = True
                    break
                except Exception:
                    continue
            if clicked:
                break
        if not clicked:
            await asyncio.sleep(0.25)
    if on_response is not None:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    if clicked:
        hub.info("checkout", "已撳「以訪客身份繼續」")
        try:
            await page.wait_for_url(_guest_nav_done, timeout=GUEST_NAV_TIMEOUT_MS)
        except Exception:
            await asyncio.sleep(1.2)
        if saw_block or checkout_is_blocked(page.url):
            return "guest_blocked"
        if _still_on_signin(page.url):
            hub.info("checkout", "已撳訪客，頁面仍喺登入牆，會繼續等跳去結帳，唔會再撳。")
            return "guest_clicked"
        return None
    if checkout_is_blocked(page.url):
        return "guest_blocked"
    hub.error("checkout", "搵唔到「以訪客身份繼續」")
    return "guest_button_missed"


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


async def _complete_add_to_bag(page, timeout: int = 4000) -> str:
    """Click add-to-bag and confirm Apple actually moved to attach/bag. blocked/ok/missed."""
    saw_block = False

    def on_response(response) -> None:
        nonlocal saw_block
        if _response_looks_blocked(response):
            saw_block = True

    listener = on_response
    try:
        page.on("response", on_response)
    except Exception:
        listener = None
    clicked = await _click_add_to_bag(page, timeout=timeout)
    if clicked:
        try:
            await page.wait_for_url(
                re.compile(r"step=attach|/shop/bag|/shop/404|/shop/541|sorry", re.I),
                timeout=10_000,
            )
        except Exception:
            await asyncio.sleep(1.0)
    if listener is not None:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    url = getattr(page, "url", "") or ""
    if checkout_stage(url) in {"attach", "bag"}:
        return "ok"
    title = await page_title(page)
    if (
        saw_block
        or checkout_is_blocked(url)
        or re.search(r"page not found|找不到|很抱歉", title, re.I)
    ):
        return "blocked"
    return "missed"


async def _on_place_order_step(page) -> bool:
    if checkout_stage(page.url) == "review":
        return True
    if re.search(r"checkout.*(review|placeorder|namedPlaceOrder)", page.url, re.I):
        return True
    locator = page.get_by_role("button", name=PLACE_ORDER_PATTERN)
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def _set_bag_quantity(page, quantity: int) -> int:
    wanted = max(1, int(quantity or 1))
    if wanted <= 1:
        return 1
    locators = [
        page.locator('select[data-autom*="quantity" i]'),
        page.get_by_label(re.compile(r"^數量$|^Quantity$", re.I)),
        page.locator('select[name*="quantity" i]'),
        page.locator("select.rs-quantity-dropdown, .quantity select"),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=2000)
            for qty in range(wanted, 0, -1):
                candidate = str(qty)
                try:
                    await handle.select_option(value=candidate, timeout=1200)
                    return qty
                except Exception:
                    try:
                        await handle.select_option(label=candidate, timeout=1200)
                        return qty
                    except Exception:
                        continue
        except Exception:
            continue
    return 1


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
    try:
        input_type = str(await handle.get_attribute("type") or "").lower()
        if input_type in {"checkbox", "radio"}:
            return False
    except Exception:
        pass
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
    try:
        await handle.click(timeout=800)
    except Exception:
        pass
    await handle.fill(await _choose_input_value(handle, values), timeout=2000)
    return True


async def _fill_phone(page, phone: str) -> bool:
    value = hk_phone_number(phone)
    if not value:
        return False
    locators = [
        page.locator('input[type="tel"]'),
        page.locator(
            'input[autocomplete="tel" i], input[data-autom*="phone" i], '
            'input[id*="phone" i], input[name*="phone" i], '
            'input[name*="fullDaytimePhone" i]'
        ),
        page.get_by_role("textbox", name=re.compile(r"手提電話號碼|^手提電話$")),
        page.get_by_label(re.compile(r"手提電話號碼|^手提電話$")),
        page.get_by_placeholder(re.compile(r"手提電話號碼|^手提電話$")),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=1800)
            if await _apply_fill(handle, [value]):
                return True
        except Exception:
            continue
    hub.warn("checkout", "未能填入手提電話")
    return False


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


async def _fill_contact(page, guest: GuestProfile | None) -> None:
    if guest is None:
        return
    mapping = {
        "last_name": guest.last_name,
        "first_name": guest.first_name,
        "email": guest.email,
        "phone": guest.phone,
    }
    for key, value in mapping.items():
        if key == "phone":
            await _fill_phone(page, value)
        else:
            await _fill_labeled(page, FIELD_CANDIDATES[key], value)


async def _fill_shipping(page, guest: GuestProfile | None) -> None:
    """Shipping-init: name, two-line address, region HK, then email and phone."""
    if guest is None:
        return
    await _fill_labeled(page, FIELD_CANDIDATES["last_name"], guest.last_name)
    await _fill_labeled(page, FIELD_CANDIDATES["first_name"], guest.first_name)
    await _select_hong_kong(page)
    await _fill_address(page, guest)
    await _fill_labeled(page, FIELD_CANDIDATES["email"], guest.email)
    await _fill_phone(page, guest.phone)


async def _select_hong_kong(page) -> None:
    await _fill_labeled(
        page,
        FIELD_CANDIDATES["country"],
        ["香港", "Hong Kong", "HK", "HKG"],
    )


async def _fill_address(page, guest: GuestProfile | None) -> None:
    if guest is None:
        return
    street = guest.address_street or guest.address
    await _fill_labeled(page, FIELD_CANDIDATES["address_street"], street)
    await _fill_labeled(page, FIELD_CANDIDATES["address_building"], guest.address_building)


async def _choose_credit_card(page) -> None:
    locators = [
        page.get_by_role("button", name=CREDIT_CARD_PATTERN),
        page.get_by_role("radio", name=CREDIT_CARD_PATTERN),
        page.get_by_label(CREDIT_CARD_PATTERN),
        page.get_by_text(CREDIT_CARD_PATTERN),
        page.locator('[data-autom*="credit" i], [data-autom*="card" i]'),
    ]
    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.first.click(timeout=2500)
            return
        except Exception:
            continue


async def _fill_billing(page, guest: GuestProfile | None) -> None:
    if guest is None:
        return
    await _choose_credit_card(page)
    await _fill_labeled(page, FIELD_CANDIDATES["card_number"], guest.card_number)
    await _fill_card_expiry(page, guest.card_month, guest.card_year)
    await _fill_labeled(page, FIELD_CANDIDATES["cvv"], guest.cvv)
    await _select_hong_kong(page)
    await _fill_labeled(page, FIELD_CANDIDATES["last_name"], guest.last_name)
    await _fill_labeled(page, FIELD_CANDIDATES["first_name"], guest.first_name)
    await _fill_address(page, guest)


async def _fill_guest(page, guest: GuestProfile | None) -> None:
    await _fill_contact(page, guest)
    await _fill_billing(page, guest)


async def _wait_for_pickup_location_ui(page, timeout: int = 8000) -> None:
    locators = [
        page.get_by_text(PICKUP_LOCATION_UI_PATTERN),
        page.get_by_role("button", name=APPLY_PATTERN),
        *[page.locator(selector) for selector in PICKUP_LOCATION_INPUT_SELECTORS],
        page.get_by_placeholder(PICKUP_LOCATION_PATTERN),
        page.get_by_label(PICKUP_LOCATION_PATTERN),
    ]
    slice_timeout = max(200, min(timeout // max(len(locators), 1), 1500))
    deadline = asyncio.get_running_loop().time() + max(timeout / 1000, 0.05)
    while asyncio.get_running_loop().time() < deadline:
        for locator in locators:
            try:
                await locator.first.wait_for(state="visible", timeout=slice_timeout)
                return
            except Exception:
                continue
        await asyncio.sleep(0.2)


def _pickup_location_locators(page) -> list:
    """Apple HK uses a store-search input; the 地區（例如「中環」）copy is often a floating label."""
    return [
        *[page.locator(selector) for selector in PICKUP_LOCATION_INPUT_SELECTORS],
        page.get_by_placeholder(PICKUP_LOCATION_PATTERN),
        page.get_by_label(PICKUP_LOCATION_PATTERN),
        page.get_by_role("textbox", name=PICKUP_LOCATION_PATTERN),
        page.get_by_role("combobox", name=PICKUP_LOCATION_PATTERN),
        page.get_by_role("searchbox", name=PICKUP_LOCATION_PATTERN),
    ]


async def _read_input_value(handle) -> str | None:
    try:
        return str(await handle.input_value() or "")
    except Exception:
        return None


def _value_has_query(current: str | None, query: str) -> bool:
    if current is None:
        return False
    return query.lower() in current.lower()


async def _focus_and_fill(handle, query: str) -> bool:
    try:
        await handle.click(timeout=1500)
    except Exception:
        pass
    wrote = False
    try:
        await handle.fill(query, timeout=2000)
        wrote = True
        current = await _read_input_value(handle)
        if current is None or _value_has_query(current, query):
            return True
    except Exception:
        pass
    for method_name in ("press_sequentially", "type"):
        method = getattr(handle, method_name, None)
        if method is None:
            continue
        try:
            await method(query, delay=30, timeout=3000)
            wrote = True
            current = await _read_input_value(handle)
            if current is None or _value_has_query(current, query):
                return True
        except Exception:
            continue
    try:
        await handle.evaluate(
            """(el, value) => {
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            query,
        )
        return True
    except Exception:
        return wrote


async def _type_into_district_label(page, query: str) -> bool:
    try:
        label = page.get_by_text(re.compile(r"地區（例如|地區\(例如")).first
        if not await _locator_is_visible(label):
            return False
        await label.click(timeout=1200)
    except Exception:
        return False
    keyboard = getattr(page, "keyboard", None)
    if keyboard is None:
        return False
    try:
        await keyboard.type(query, delay=25)
        return True
    except Exception:
        return False


async def _click_pickup_apply(page) -> None:
    locators = [
        page.locator(PICKUP_APPLY_SELECTOR),
        page.get_by_role("button", name=APPLY_PATTERN),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=1500)
            await handle.click(timeout=2000)
            return
        except Exception:
            continue
    if not await _click_role(page, APPLY_PATTERN, timeout=2500):
        try:
            await page.keyboard.press("Enter")
        except Exception:
            pass


async def _pickup_location_error_visible(page) -> bool:
    try:
        handle = page.get_by_text(PICKUP_LOCATION_ERROR_PATTERN).first
        return await _locator_is_visible(handle)
    except Exception:
        return False


async def _pickup_stores_visible(page, timeout: int = 3500) -> bool:
    try:
        await page.get_by_text(PICKUP_STORE_LIST_PATTERN).first.wait_for(
            state="visible",
            timeout=timeout,
        )
        return True
    except Exception:
        return False


async def _pickup_stores_ready(page) -> bool:
    try:
        handle = page.get_by_text(PICKUP_APPLIED_PATTERN).first
        if await _locator_is_visible(handle):
            return True
    except Exception:
        pass
    return await _pickup_stores_visible(page, timeout=800)


async def _is_checked(handle) -> bool:
    try:
        if await handle.is_checked():
            return True
    except Exception:
        pass
    try:
        if str(await handle.get_attribute("aria-checked") or "").lower() == "true":
            return True
    except Exception:
        pass
    return False


async def _pickup_already_active(page) -> bool:
    """Stores already listed means pickup is selected; re-clicking it resets the locator."""
    if await _pickup_stores_ready(page):
        return True
    locators = [
        page.get_by_role("radio", name=PICKUP_PATTERN),
        page.get_by_label(PICKUP_PATTERN),
    ]
    for locator in locators:
        try:
            handle = locator.first
            if await _locator_is_visible(handle) and await _is_checked(handle):
                return True
        except Exception:
            continue
    return False


async def _pickup_continue_enabled(page) -> bool:
    locators = [
        page.get_by_role("button", name=PICKUP_DETAILS_CONTINUE_PATTERN),
        page.get_by_role("link", name=PICKUP_DETAILS_CONTINUE_PATTERN),
    ]
    for locator in locators:
        try:
            handle = locator.first
            if not await _locator_is_visible(handle):
                continue
            try:
                if await handle.is_enabled():
                    return True
            except Exception:
                return True
        except Exception:
            continue
    return False


async def _store_is_selected(page, match: StockMatch) -> bool:
    selectors = [
        f'input[type="radio"][value="{match.store_id}"]',
        f'input[value="{match.store_id}"]',
        f'[data-store-id="{match.store_id}"]',
        f'[data-autom*="{match.store_id}" i]',
    ]
    for selector in selectors:
        try:
            handle = page.locator(selector).first
            if await _locator_is_visible(handle) and await _is_checked(handle):
                return True
        except Exception:
            continue
    return await _pickup_continue_enabled(page)


async def _wait_store_committed(page, match: StockMatch, timeout: int = 2500) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        if checkout_stage(getattr(page, "url", "") or "") == "contact":
            return True
        if await _store_is_selected(page, match):
            return True
        await asyncio.sleep(0.15)
    return False


async def _apply_pickup_location(
    page, query: str = PICKUP_LOCATION, timeout: int = 12_000
) -> bool:
    """Apple HK hides pickup stores until a district is applied. Hong Kong lists all six."""
    await _wait_for_pickup_location_ui(page, timeout=min(timeout, 8000))
    if await _pickup_stores_ready(page):
        return True
    deadline = asyncio.get_running_loop().time() + max(timeout / 1000, 0.05)
    filled = False
    while asyncio.get_running_loop().time() < deadline:
        for locator in _pickup_location_locators(page):
            try:
                handle = locator.first
                await handle.wait_for(state="visible", timeout=800)
                if await _focus_and_fill(handle, query):
                    filled = True
                    break
            except Exception:
                continue
        if not filled:
            filled = await _type_into_district_label(page, query)
        if filled:
            await _click_pickup_apply(page)
            if await _pickup_stores_visible(page, timeout=3500):
                hub.info("checkout", f"已填「{query}」並撳套用")
                return True
            if not await _pickup_location_error_visible(page):
                await asyncio.sleep(0.6)
                if await _pickup_stores_visible(page, timeout=2000):
                    hub.info("checkout", f"已填「{query}」並撳套用")
                    return True
        await asyncio.sleep(0.25)
    if filled:
        hub.warn("checkout", f"已填「{query}」並撳套用，但門市清單未出現")
        return True
    hub.warn("checkout", f"搵唔到地區欄，未能填「{query}」")
    return False


async def _click_pickup_store(page, match: StockMatch, timeout: int = 4000) -> bool:
    store_pattern = re.compile(re.escape(match.store_name) + r"|" + re.escape(match.store_id), re.I)
    candidates = [
        page.locator(f'input[type="radio"][value="{match.store_id}"]'),
        page.locator(f'input[value="{match.store_id}"]'),
        page.locator(f'[data-autom*="{match.store_id}" i]'),
        page.locator(f'[data-store-id="{match.store_id}"]'),
        page.get_by_role("radio", name=store_pattern),
        page.locator("label").filter(has_text=store_pattern),
        page.get_by_text(store_pattern),
    ]
    for locator in candidates:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=timeout)
            await handle.click(timeout=3000)
            if await _wait_store_committed(page, match, timeout=2000):
                return True
        except Exception:
            continue
    return await _wait_store_committed(page, match, timeout=800)


async def _select_pickup_store(page, match: StockMatch, timeout: int) -> bool:
    if not await _pickup_already_active(page):
        await _click_choice(page, PICKUP_PATTERN, timeout=timeout)
    if not await _pickup_stores_ready(page):
        await _apply_pickup_location(page, PICKUP_LOCATION)
    if await _click_pickup_store(page, match, timeout=max(timeout, 3000)):
        return True
    if not await _pickup_stores_ready(page):
        area = (STORE_BY_ID.get(match.store_id) or {}).get("area") or ""
        for query in (area, match.store_name):
            if not query:
                continue
            await _apply_pickup_location(page, query)
            if await _click_pickup_store(page, match):
                return True
    else:
        await asyncio.sleep(0.4)
        if await _click_pickup_store(page, match, timeout=4000):
            return True
    hub.warn("checkout", f"未能自動點選門市 {match.store_name}，將繼續嘗試結帳步驟")
    return False


async def _click_pickup_details_continue(page, timeout: int = 10_000) -> bool:
    """Wait until Apple enables 繼續前往取貨詳情 after the store radio commits."""
    deadline = asyncio.get_running_loop().time() + max(timeout / 1000, 0.05)
    while asyncio.get_running_loop().time() < deadline:
        if checkout_stage(getattr(page, "url", "") or "") == "contact":
            return True
        locators = [
            page.get_by_role("button", name=PICKUP_DETAILS_CONTINUE_PATTERN),
            page.get_by_role("link", name=PICKUP_DETAILS_CONTINUE_PATTERN),
            page.locator(
                '[data-autom*="fulfillmentContinue" i], '
                '[data-autom*="fulfillment-continue" i], '
                '[data-autom*="pickup-continue" i]'
            ),
            page.get_by_text(PICKUP_DETAILS_CONTINUE_PATTERN),
        ]
        for locator in locators:
            try:
                handle = locator.first
                if not await _locator_is_visible(handle):
                    continue
                try:
                    if await handle.is_enabled() is False:
                        continue
                except Exception:
                    pass
                await handle.click(timeout=2500)
                try:
                    await page.wait_for_url(
                        re.compile(r"PickupContact|timeSlot|Timeslot", re.I),
                        timeout=4000,
                    )
                except Exception:
                    await asyncio.sleep(0.35)
                if checkout_stage(getattr(page, "url", "") or "") == "contact":
                    return True
            except Exception:
                continue
        await asyncio.sleep(0.2)
    return checkout_stage(getattr(page, "url", "") or "") == "contact"


def _looks_like_fulfillment_method(text: str) -> bool:
    blob = text or ""
    return bool(DELIVERY_PATTERN.search(blob) or PICKUP_PATTERN.search(blob))


async def _control_label(handle) -> str:
    parts: list[str] = []
    for reader in (
        lambda: handle.inner_text(),
        lambda: handle.get_attribute("aria-label"),
        lambda: handle.get_attribute("data-autom"),
        lambda: handle.get_attribute("name"),
        lambda: handle.get_attribute("value"),
    ):
        try:
            parts.append(str(await reader() or ""))
        except Exception:
            continue
    return " ".join(parts)


async def _click_earliest_slot(page) -> bool:
    """Click a pickup time slot only. Never the 送貨/取貨 method radios on this page."""
    locators = [
        page.locator(
            "[data-autom*='timeslot' i], [data-autom*='timeSlot' i], "
            "[data-autom*='time-slot' i], [data-timeslot], "
            ".timeslot, .time-slot, [name*='timeSlot' i]"
        ),
        page.get_by_role("radio", name=TIMESLOT_PATTERN),
        page.get_by_role("button", name=TIMESLOT_PATTERN),
        page.get_by_label(TIMESLOT_PATTERN),
    ]
    for locator in locators:
        try:
            handle = locator.first
            await handle.wait_for(state="visible", timeout=1500)
            if _looks_like_fulfillment_method(await _control_label(handle)):
                continue
            await handle.click(timeout=2000)
            return True
        except Exception:
            continue
    return False


async def _delivery_days_from_page(page) -> int | None:
    try:
        text = await page.inner_text("body", timeout=3000)
    except Exception:
        return None
    return days_from_quote(text)


async def _abort_if_delivery_too_slow(page, match: StockMatch, delivery_max_days: int) -> str | None:
    days = await _delivery_days_from_page(page)
    if days is None or days <= delivery_max_days:
        return None
    hub.warn("checkout", f"預計送達需 {days} 日，超出設定的 {delivery_max_days} 日內，放棄今次機會")
    try:
        await page.goto(product_url(match.sku), wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        pass
    return "delivery_too_slow"


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
        return await _abort_if_delivery_too_slow(page, match, delivery_max_days)

    if checkout_stage(page.url) == "contact":
        return None
    if not await _select_pickup_store(page, match, timeout=4000):
        return RETRY_FULFILLMENT
    if checkout_stage(page.url) == "contact":
        return None
    if not await _click_pickup_details_continue(page, timeout=10_000):
        if checkout_stage(page.url) == "contact":
            return None
        hub.warn("checkout", "已揀門市，但未撳到「繼續前往取貨詳情」")
        return RETRY_FULFILLMENT
    hub.info("checkout", "已撳「繼續前往取貨詳情」")
    await _click_earliest_slot(page)
    return None


async def run_checkout(
    page,
    sku: str,
    match: StockMatch,
    test_mode: bool,
    worker_name: str,
    stop_event: asyncio.Event,
    checkout_mode: str = "guest",
    fulfillment: str = "pickup",
    guest: GuestProfile | None = None,
    delivery_max_days: int = 7,
    quantity: int = 1,
    empty_bag: bool = True,
) -> CheckoutResult:
    timer = StepTimer()
    if await _stopped(stop_event):
        return timer.announce(worker_name, False, "stopped")

    try:
        where = match.store_name if fulfillment == "pickup" else f"送貨 {delivery_max_days} 日內"
        hub.info(worker_name, f"開始搶購 {sku}（{where}）")
        if empty_bag:
            await _empty_bag(page)
        await page.goto(product_url(sku), wait_until="domcontentloaded", timeout=45_000)
        await _wait_for_configured_pdp(page)
        if await _stopped(stop_event):
            return timer.announce(worker_name, False, "stopped")

        hub.info(worker_name, f"產品頁已開（{page.url}），先揀不換購同無 AppleCare+，再開加車")
        await _decline_tradein_and_applecare(page)

        deadline = asyncio.get_running_loop().time() + 45
        added = False
        while asyncio.get_running_loop().time() < deadline:
            if await _stopped(stop_event):
                return timer.announce(worker_name, False, "stopped")
            outcome = await _complete_add_to_bag(page, timeout=4000)
            if outcome == "blocked":
                hub.error(
                    worker_name,
                    block_report(
                        "加車",
                        page.url,
                        await page_title(page),
                        "加車掣已撳但跳咗 404/541，未入到購物袋。唔好連撳。可改用平時 Chrome 人手試同一款。",
                    ),
                )
                return timer.announce(worker_name, False, "add_to_bag_blocked", pause=True)
            if outcome == "ok":
                added = True
                break
            await _decline_tradein_and_applecare(page)
            await _click_choice(page, SKIP_PATTERN, timeout=1500)
            if not await _on_place_order_step(page):
                await _maybe_click(page, CONTINUE_PATTERN, timeout=1500)
            await asyncio.sleep(0.3)

        if not added:
            return timer.announce(worker_name, False, "add_to_bag_failed")
        timer.mark("add_bag")

        hub.info(worker_name, "已加入購物袋，查看購物袋")
        bag_qty = 1
        await _open_bag(page)
        bag_qty = await _set_bag_quantity(page, quantity)
        hub.info(worker_name, "進入結帳（唔會撳 Apple Pay）")
        if not await _click_visible_checkout(page, timeout=CHECKOUT_STEP_TIMEOUT_MS):
            await page.goto(bag_url(), wait_until="domcontentloaded", timeout=30_000)
            bag_qty = await _set_bag_quantity(page, quantity)
            if not await _click_visible_checkout(page, timeout=CHECKOUT_STEP_TIMEOUT_MS):
                await page.goto(checkout_url(), wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_url(
                re.compile(r"signIn|checkout|/shop/sorry|/shop/541|/shop/404", re.I),
                timeout=CHECKOUT_STEP_TIMEOUT_MS,
            )
        except Exception:
            pass
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
            return timer.announce(worker_name, False, "checkout_blocked", pause=True)
        timer.mark("enter_checkout")

        guest_clicked = False
        if checkout_mode == "guest":
            blocked = await _continue_as_guest(page)
            if blocked == "guest_clicked":
                guest_clicked = True
            elif blocked:
                hub.error(
                    worker_name,
                    block_report(
                        "訪客結帳",
                        page.url,
                        await page_title(page),
                        guest_block_extra(blocked),
                    ),
                )
                return timer.announce(worker_name, False, blocked, pause=True)

        step_deadline = asyncio.get_running_loop().time() + 90
        fulfillment_done = False
        contact_done = False
        shipping_done = False
        billing_done = False
        while asyncio.get_running_loop().time() < step_deadline:
            if await _stopped(stop_event):
                return timer.announce(worker_name, False, "stopped")
            if checkout_is_blocked(page.url):
                hub.error(
                    worker_name,
                    block_report("結帳途中", page.url, await page_title(page)),
                )
                return timer.announce(worker_name, False, "guest_blocked", pause=True)
            if await _on_place_order_step(page):
                break
            stage = checkout_stage(page.url)
            if checkout_mode == "guest" and stage == "signin":
                if guest_clicked:
                    await asyncio.sleep(0.8)
                    continue
                blocked = await _continue_as_guest(page)
                if blocked == "guest_clicked":
                    guest_clicked = True
                    continue
                if blocked:
                    hub.error(
                        worker_name,
                        block_report(
                            "訪客結帳",
                            page.url,
                            await page_title(page),
                            guest_block_extra(blocked),
                        ),
                    )
                    return timer.announce(worker_name, False, blocked, pause=True)
                continue
            if not fulfillment_done and stage in ("fulfillment", "other"):
                skipped = await _handle_fulfillment(
                    page,
                    match,
                    fulfillment,
                    checkout_mode,
                    guest,
                    delivery_max_days,
                )
                if skipped == RETRY_FULFILLMENT:
                    if stage == "fulfillment":
                        await asyncio.sleep(0.6)
                        continue
                    skipped = None
                fulfillment_done = True
                timer.mark("fulfillment")
                if skipped:
                    return timer.announce(worker_name, False, skipped)
            if checkout_mode == "guest" and stage == "contact" and not contact_done:
                await _fill_contact(page, guest)
                contact_done = True
            if checkout_mode == "guest" and stage == "shipping" and not shipping_done:
                await _fill_shipping(page, guest)
                shipping_done = True
                skipped = await _abort_if_delivery_too_slow(page, match, delivery_max_days)
                if skipped:
                    return timer.announce(worker_name, False, skipped)
            if checkout_mode == "guest" and stage == "billing" and not billing_done:
                await _fill_billing(page, guest)
                billing_done = True
                timer.mark("billing")
            if await _on_place_order_step(page):
                break
            if stage == "billing":
                await _maybe_click(page, REVIEW_ORDER_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS)
            else:
                await _maybe_click(page, CONTINUE_PATTERN, timeout=CHECKOUT_STEP_TIMEOUT_MS)
            await asyncio.sleep(0.5)

        if checkout_mode == "guest" and _still_on_signin(page.url):
            hub.error(
                worker_name,
                block_report(
                    "訪客結帳",
                    page.url,
                    await page_title(page),
                    guest_block_extra("guest_nav_timeout"),
                ),
            )
            return timer.announce(worker_name, False, "guest_nav_timeout", pause=True)

        reached_end = await _on_place_order_step(page)
        reached_card = billing_done or checkout_stage(page.url) == "billing"
        if test_mode and (reached_end or reached_card):
            if reached_end:
                timer.mark("payment")
            elif "billing" not in timer.marks:
                timer.mark("billing")
            stop_at = (
                "檢查訂單頁（唔會撳立即下單）"
                if reached_end
                else "信用卡／付款頁（測試卡過唔到就停呢度；用真卡、測試模式仍然開住，就可以去到檢查訂單頁）"
            )
            hub.success(
                worker_name,
                f"測試模式：已停在{stop_at}，不會送出訂單。目前頁面：{page.url}",
            )
            return timer.announce(
                worker_name, True, "dry_run", quantity=bag_qty, level="success"
            )

        if not reached_end:
            raise CheckoutInterrupted("找不到付款前最後一步，可能被新頁面或手動操作打斷")
        timer.mark("payment")

        hub.warn(worker_name, "真實下單模式：正在送出訂單")
        if not await _click_role(page, PLACE_ORDER_PATTERN, CHECKOUT_STEP_TIMEOUT_MS):
            raise CheckoutInterrupted("未能點擊送出訂單")
        try:
            await page.wait_for_url(re.compile(r"checkout/(thankyou|status|complete)|order", re.I), timeout=20_000)
        except Exception:
            pass
        hub.success(worker_name, f"已送出訂單（或等待確認頁）。目前頁面：{page.url}")
        return timer.announce(worker_name, True, "ordered", quantity=bag_qty, level="success")
    except asyncio.CancelledError:
        raise
    except CheckoutInterrupted as exc:
        hub.error(worker_name, INTERRUPT_MESSAGE)
        if exc.detail and exc.detail != INTERRUPT_MESSAGE:
            hub.error(worker_name, "請喺已帶到最前嘅視窗手動處理，完成後撳「開始運作」再繼續。")
        return timer.announce(worker_name, False, "interrupted", pause=True, level="warn")
    except Exception as exc:
        if _looks_unexpected(exc):
            hub.error(worker_name, INTERRUPT_MESSAGE)
            return timer.announce(worker_name, False, "interrupted", pause=True, level="warn")
        return timer.announce(worker_name, False, "checkout_error")
