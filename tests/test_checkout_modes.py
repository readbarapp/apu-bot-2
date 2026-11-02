from __future__ import annotations

from pathlib import Path

import pytest

from bot.checkout import (
    ADD_BAG_PATTERN,
    CHECKOUT_PATTERN,
    CONTINUE_PATTERN,
    CREDIT_CARD_PATTERN,
    CheckoutResult,
    DELIVERY_PATTERN,
    GUEST_BUTTON_PATTERN,
    GUEST_PATTERN,
    INTERRUPT_MESSAGE,
    NO_APPLECARE_PATTERN,
    NO_TRADEIN_PATTERN,
    PICKUP_PATTERN,
    REVIEW_ORDER_PATTERN,
    SKIP_PATTERN,
    VIEW_BAG_PATTERN,
    _click_add_to_bag,
    _continue_as_guest,
    guest_block_extra,
    _decline_tradein_and_applecare,
    _fill_card_expiry,
    _fill_guest,
    _set_bag_quantity,
    block_report,
    card_month_options,
    card_year_options,
    checkout_is_blocked,
    checkout_stage,
    mm_yy,
    wait_if_checkout_blocked,
    _response_looks_blocked,
)
from bot.models import GuestProfile
from bot.inventory import days_from_quote
from bot.logs import hub, redact_message
from bot.secrets import encrypt_text, decrypt_text, public_guest, save_guest_secrets, load_guest_secrets

SAMPLE_WORKER = {
    "id": "w1",
    "name": "Worker_1",
    "session_dir": "session_worker_1",
    "sku": "MK2E4ZA/A",
    "stores": ["R428", "R409"],
    "pickup_window": "1d",
    "max_qty": 1,
}

SAMPLE_GUEST = {
    "id": "g1",
    "name": "Guest_1",
    "session_dir": "session_guest_1",
    "sku": "MK2E4ZA/A",
    "stores": ["R428"],
    "pickup_window": "1d",
    "max_qty": 1,
    "checkout_mode": "guest",
    "fulfillment": "pickup",
    "guest": {
        "last_name": "Chan",
        "first_name": "Tai Man",
        "email": "chan@example.com",
        "phone": "51234567",
        "address": "中環金融街 8 號",
        "address_street": "中環金融街 8 號",
        "address_building": "國際金融中心一期 15 樓 1501 室",
        "card_number": "4111111111111111",
        "card_month": "12",
        "card_year": "2028",
        "cvv": "123",
    },
}


def test_apple_id_mode_requires_session_dir(client) -> None:
    payload = {**SAMPLE_WORKER, "session_dir": ""}
    response = client.post("/api/start", json={"test_mode": True, "workers": [payload]})
    assert response.status_code == 422


def test_guest_profile_lists_every_empty_field() -> None:
    guest = GuestProfile(last_name="Chan", first_name="Tai Man")
    missing = guest.missing_labels()
    assert "電郵地址" in missing
    assert "信用卡號碼" in missing
    assert "有效月份" in missing
    assert "CVV 安全碼" in missing
    assert "街道地址" in "".join(missing)
    assert "屋苑或大廈" in "".join(missing)
    assert "英文姓氏" not in missing


def test_legacy_address_copies_into_street_line() -> None:
    guest = GuestProfile(
        last_name="Chan",
        first_name="Tai Man",
        email="chan@example.com",
        phone="51234567",
        address="中環金融街 8 號",
        card_number="4111111111111111",
        card_month="12",
        card_year="2028",
        cvv="123",
    )
    assert guest.address_street == "中環金融街 8 號"
    assert "屋苑或大廈" in "".join(guest.missing_labels())


def test_card_expiry_prefers_two_digit_year_for_apple_mm_yy() -> None:
    assert card_year_options("2028") == ["28", "2028"]
    assert card_year_options("28") == ["28", "2028"]
    assert card_month_options("12") == ["12"]
    assert card_month_options("1") == ["01", "1"]
    assert mm_yy("12", "2028") == "12/28"
    assert mm_yy("09", "2031") == "09/31"
    assert mm_yy("1", "28") == "01/28"
    assert "2028" not in mm_yy("12", "2028")
    assert mm_yy("", "2028") == ""


class _FakeExpiryHandle:
    def __init__(self, page: "_FakeExpiryPage", kind: str, tag: str = "input") -> None:
        self._page = page
        self._kind = kind
        self._tag = tag
        self.first = self

    async def wait_for(self, **_kwargs) -> None:
        if self._kind not in self._page.fields:
            raise RuntimeError("missing")

    async def count(self) -> int:
        return 1 if self._kind in self._page.fields else 0

    async def click(self, **_kwargs) -> None:
        return None

    async def evaluate(self, _script: str) -> str:
        return self._tag

    async def get_attribute(self, name: str) -> str | None:
        field = self._page.fields.get(self._kind) or {}
        return field.get(name)

    async def select_option(self, value=None, label=None, **_kwargs) -> None:
        candidate = value or label
        options = (self._page.fields.get(self._kind) or {}).get("options") or []
        if candidate not in options:
            raise RuntimeError("no option")
        self._page.filled[self._kind] = candidate

    async def fill(self, value: str, **_kwargs) -> None:
        self._page.filled[self._kind] = value


class _FakeExpiryPage:
    def __init__(self, fields: dict[str, dict]) -> None:
        self.fields = fields
        self.filled: dict[str, str] = {}

    def _match(self, text: str) -> _FakeExpiryHandle | None:
        lowered = text.lower()
        if "mm" in lowered and "yy" in lowered and "combined" in self.fields:
            return _FakeExpiryHandle(self, "combined")
        if "expiration" in lowered and "month" not in lowered and "year" not in lowered and "combined" in self.fields:
            return _FakeExpiryHandle(self, "combined")
        if "expmonth" in lowered or ("月" in text and "年" not in text):
            tag = (self.fields.get("month") or {}).get("tag", "select")
            return _FakeExpiryHandle(self, "month", tag)
        if "expyear" in lowered or ("年" in text and "月" not in text):
            tag = (self.fields.get("year") or {}).get("tag", "select")
            return _FakeExpiryHandle(self, "year", tag)
        return None

    def get_by_label(self, pattern):
        handle = self._match(pattern.pattern if hasattr(pattern, "pattern") else str(pattern))
        return handle or _FakeExpiryHandle(self, "missing")

    def get_by_placeholder(self, pattern):
        return self.get_by_label(pattern)

    def get_by_role(self, _role, name=None):
        return self.get_by_label(name or _role)

    def get_by_text(self, pattern):
        return self.get_by_label(pattern)

    def locator(self, selector: str):
        handle = self._match(selector)
        return handle or _FakeExpiryHandle(self, "missing")


@pytest.mark.asyncio
async def test_fill_card_expiry_uses_mm_yy_not_four_digit_year() -> None:
    page = _FakeExpiryPage({"combined": {"tag": "input", "maxlength": "5"}})
    await _fill_card_expiry(page, "12", "2028")
    assert page.filled == {"combined": "12/28"}
    assert "2028" not in page.filled["combined"]


@pytest.mark.asyncio
async def test_fill_card_expiry_year_select_prefers_two_digit_option() -> None:
    page = _FakeExpiryPage({
        "month": {"tag": "select", "options": ["12"]},
        "year": {"tag": "select", "options": ["28", "2028"]},
    })
    await _fill_card_expiry(page, "12", "2028")
    assert page.filled["year"] == "28"


@pytest.mark.asyncio
async def test_fill_card_expiry_year_select_tries_yy_then_yyyy() -> None:
    page = _FakeExpiryPage({
        "month": {"tag": "select", "options": ["12"]},
        "year": {"tag": "select", "options": ["2028"]},
    })
    await _fill_card_expiry(page, "12", "2028")
    assert page.filled["month"] == "12"
    assert page.filled["year"] == "2028"


@pytest.mark.asyncio
async def test_fill_card_expiry_year_input_uses_two_digits() -> None:
    page = _FakeExpiryPage({
        "month": {"tag": "select", "options": ["12"]},
        "year": {"tag": "input", "maxlength": "2"},
    })
    await _fill_card_expiry(page, "12", "2028")
    assert page.filled["year"] == "28"


@pytest.mark.asyncio
async def test_fill_guest_does_not_type_four_digit_year_into_mm_yy() -> None:
    page = _FakeExpiryPage({"combined": {"tag": "input", "placeholder": "MM/YY"}})
    guest = GuestProfile(
        last_name="Chan",
        first_name="Tai Man",
        email="chan@example.com",
        phone="51234567",
        address_street="中環金融街 8 號",
        address_building="國際金融中心一期 15 樓 1501 室",
        card_number="4111111111111111",
        card_month="12",
        card_year="2028",
        cvv="123",
    )
    await _fill_guest(page, guest)
    assert page.filled.get("combined") == "12/28"


def test_guest_card_must_be_sixteen_digits(client) -> None:
    payload = {
        **SAMPLE_GUEST,
        "guest": {**SAMPLE_GUEST["guest"], "card_number": "41111111"},
    }
    response = client.post("/api/start", json={"test_mode": True, "workers": [payload]})
    assert response.status_code == 422


def test_guest_incomplete_is_rejected(client) -> None:
    payload = {
        **SAMPLE_GUEST,
        "guest": {**SAMPLE_GUEST["guest"], "first_name": "", "cvv": ""},
    }
    response = client.post("/api/start", json={"test_mode": True, "workers": [payload]})
    assert response.status_code == 422


def test_guest_missing_card_or_cvv_is_rejected(client) -> None:
    no_cvv = {
        **SAMPLE_GUEST,
        "guest": {**SAMPLE_GUEST["guest"], "cvv": ""},
    }
    no_card = {
        **SAMPLE_GUEST,
        "id": "g2",
        "session_dir": "session_guest_2",
        "guest": {**SAMPLE_GUEST["guest"], "card_number": ""},
    }
    assert client.post("/api/start", json={"test_mode": True, "workers": [no_cvv]}).status_code == 422
    assert client.post("/api/start", json={"test_mode": True, "workers": [no_card]}).status_code == 422


def test_guest_can_resave_with_masked_card_and_blank_cvv(client) -> None:
    first = client.post("/api/workers/secrets", json={"test_mode": True, "worker": SAMPLE_GUEST})
    assert first.status_code == 200, first.text
    edited = {
        **SAMPLE_GUEST,
        "guest": {
            **SAMPLE_GUEST["guest"],
            "first_name": "Siu Ming",
            "card_number": "•••• 1111",
            "cvv": "",
        },
    }
    saved = client.post("/api/workers/secrets", json={"test_mode": True, "worker": edited})
    assert saved.status_code == 200, saved.text
    started = client.post("/api/start", json={"test_mode": True, "workers": [edited]})
    assert started.status_code == 200, started.text
    client.post("/api/stop")


def test_guest_can_start_without_apple_id_login(client) -> None:
    denied = client.post(
        "/api/start",
        json={"test_mode": True, "workers": [SAMPLE_WORKER]},
    )
    assert denied.status_code == 409

    started = client.post("/api/start", json={"test_mode": True, "workers": [SAMPLE_GUEST]})
    assert started.status_code == 200, started.text
    body = next(item for item in started.json()["workers"] if item["id"] == "g1")
    assert body["checkout_mode"] == "guest"
    assert body["sniping"] is True
    assert "4111111111111111" not in str(body)
    assert body["guest"]["cvv"] == ""
    assert "1111" in body["guest"]["card_number"]
    client.post("/api/stop")


def test_pickup_requires_store_delivery_does_not(client) -> None:
    pickup = {**SAMPLE_WORKER, "stores": []}
    assert client.post("/api/start", json={"test_mode": True, "workers": [pickup]}).status_code == 422
    delivery = {
        **SAMPLE_WORKER,
        "id": "d1",
        "session_dir": "session_delivery_1",
        "fulfillment": "delivery",
        "stores": [],
        "delivery_max_days": 7,
    }
    client.post("/api/workers/login", json={"test_mode": True, "worker": delivery})
    started = client.post("/api/start", json={"test_mode": True, "workers": [delivery]})
    assert started.status_code == 200, started.text
    client.post("/api/stop")


def test_guest_secrets_are_encrypted_and_not_logged(client) -> None:
    started = client.post("/api/start", json={"test_mode": True, "workers": [SAMPLE_GUEST]})
    assert started.status_code == 200
    history = " ".join(item["message"] for item in hub.history())
    assert "4111111111111111" not in history
    assert "cvv" not in history.lower() or "123" not in history
    public = public_guest(SAMPLE_GUEST["guest"])
    assert public["cvv"] == ""
    assert "••••" in public["card_number"]
    client.post("/api/stop")


def test_secret_roundtrip_and_gitignore() -> None:
    save_guest_secrets("t1", SAMPLE_GUEST["guest"])
    loaded = load_guest_secrets("t1")
    assert loaded is not None
    assert loaded["card_number"] == "4111111111111111"
    blob = encrypt_text("hello")
    assert "hello" not in blob
    assert decrypt_text(blob) == "hello"
    gitignore = Path(".gitignore").read_text()
    assert ".env" in gitignore
    assert "secrets/" in gitignore
    assert "sessions/*" in gitignore


def test_redact_message_hides_pan_and_cvv() -> None:
    text = redact_message("card_number=4111111111111111 cvv 123")
    assert "4111111111111111" not in text
    assert "123" not in text or "已隱藏" in text


def test_delivery_days_over_limit_is_detectable() -> None:
    assert days_from_quote("3 日後送達") == 3
    assert days_from_quote("14 日後送到") == 14
    assert days_from_quote("14 日後送到") > 7


def test_guest_continue_pattern_and_blocked_urls() -> None:
    assert GUEST_PATTERN.search("以訪客身份繼續")
    assert GUEST_PATTERN.search("訪客結帳")
    assert GUEST_BUTTON_PATTERN.search("以訪客身份繼續")
    assert GUEST_BUTTON_PATTERN.search("Continue as Guest")
    assert not GUEST_BUTTON_PATTERN.search("訪客結帳")
    assert not GUEST_BUTTON_PATTERN.search("以訪客身份")
    assert guest_block_extra("guest_button_missed").startswith("畫面停喺登入牆")
    assert "被擋" in guest_block_extra("guest_blocked")
    assert checkout_is_blocked("https://www.apple.com/hk-zh/shop/404")
    assert checkout_is_blocked("https://secure9.store.apple.com/shop/go/404")
    assert checkout_is_blocked("https://www.apple.com/hk-zh/shop/sorry/message_generic")
    assert not checkout_is_blocked(
        "https://secure9.store.apple.com/hk-zh/shop/checkout/start"
    )


def _pattern_matches_guest_button(pattern) -> bool:
    label = "以訪客身份繼續"
    if hasattr(pattern, "search"):
        return bool(pattern.search(label))
    return str(pattern) == label


class _FakeGuestPage:
    def __init__(
        self,
        after_url: str,
        *,
        has_autom: bool = True,
        has_button: bool = True,
        frames: list | None = None,
    ) -> None:
        self.url = "https://secure.store.apple.com/hk-zh/shop/signIn"
        self.after_url = after_url
        self.clicks: list[str] = []
        self.has_autom = has_autom
        self.has_button = has_button
        self.frames = frames or []

    def locator(self, selector: str):
        clickable = self.has_button and (
            ("guest-checkout-btn" in selector and self.has_autom)
            or ("guest-checkout" in selector and self.has_autom)
            or ("guestCheckout" in selector and self.has_autom)
            or "以訪客身份繼續" in selector
            or "guestLogin" in selector
        )
        return _FakeGuestButton(self, selector, clickable=clickable)

    def get_by_role(self, role: str, name=None, **_kwargs):
        clickable = self.has_button and role in {"button", "link"} and _pattern_matches_guest_button(name)
        return _FakeGuestButton(self, f"role:{role}", clickable=clickable)

    def get_by_text(self, pattern, **_kwargs):
        clickable = self.has_button and _pattern_matches_guest_button(pattern)
        return _FakeGuestButton(self, "text", clickable=clickable)

    def on(self, *_args, **_kwargs) -> None:
        return None

    def remove_listener(self, *_args, **_kwargs) -> None:
        return None

    async def wait_for_url(self, *_args, **_kwargs) -> None:
        self.url = self.after_url


class _FakeGuestButton:
    def __init__(self, page: _FakeGuestPage, name: str, clickable: bool = False) -> None:
        self._page = page
        self._name = name
        self._clickable = clickable
        self.first = self

    async def count(self) -> int:
        return 1 if self._clickable else 0

    async def is_visible(self) -> bool:
        return self._clickable

    async def wait_for(self, **_kwargs) -> None:
        if not self._clickable:
            raise TimeoutError(self._name)

    async def scroll_into_view_if_needed(self, **_kwargs) -> None:
        return None

    async def click(self, **_kwargs) -> None:
        if not self._clickable:
            raise TimeoutError(self._name)
        self._page.clicks.append(self._name)
        self._page.url = self._page.after_url


@pytest.mark.asyncio
async def test_continue_as_guest_detects_apple_404() -> None:
    page = _FakeGuestPage("https://www.apple.com/hk-zh/shop/404")
    assert await _continue_as_guest(page) == "guest_blocked"
    assert page.clicks[0].startswith('[data-autom="guest-checkout-btn"]')


@pytest.mark.asyncio
async def test_continue_as_guest_allows_real_checkout() -> None:
    page = _FakeGuestPage("https://secure.store.apple.com/hk-zh/shop/checkout/start")
    assert await _continue_as_guest(page) is None
    assert page.clicks


@pytest.mark.asyncio
async def test_continue_as_guest_blocks_if_still_on_signin() -> None:
    page = _FakeGuestPage("https://secure.store.apple.com/hk-zh/shop/signIn?ssi=abc")
    assert await _continue_as_guest(page) == "guest_blocked"
    assert page.clicks


@pytest.mark.asyncio
async def test_continue_as_guest_clicks_visible_label_without_data_autom() -> None:
    page = _FakeGuestPage(
        "https://secure.store.apple.com/hk-zh/shop/checkout?_s=Fulfillment-init",
        has_autom=False,
    )
    assert await _continue_as_guest(page) is None
    assert page.clicks
    assert not any("guest-checkout-btn" in click for click in page.clicks)


@pytest.mark.asyncio
async def test_continue_as_guest_clicks_button_inside_iframe() -> None:
    frame = _FakeGuestPage(
        "https://secure.store.apple.com/hk-zh/shop/checkout/start",
        has_autom=False,
    )
    page = _FakeGuestPage(
        "https://secure.store.apple.com/hk-zh/shop/checkout/start",
        has_button=False,
        frames=[frame],
    )
    page.after_url = frame.after_url
    assert await _continue_as_guest(page) is None
    assert frame.clicks
    assert page.url.endswith("/shop/checkout/start")


@pytest.mark.asyncio
async def test_continue_as_guest_reports_missed_button() -> None:
    page = _FakeGuestPage(
        "https://secure.store.apple.com/hk-zh/shop/signIn?ssi=abc",
        has_autom=False,
        has_button=False,
    )
    assert await _continue_as_guest(page, timeout=200) == "guest_button_missed"
    assert page.clicks == []


def test_block_report_is_copyable_without_reading_code() -> None:
    text = block_report(
        "加車",
        "https://www.apple.com/hk-zh/shop/404",
        "未找到頁面 - Apple (香港)",
        "加車掣已撳但跳咗 404/541",
    )
    assert text.startswith("【請複製呢段到對話】")
    assert "步驟=加車" in text
    assert "被擋頁=是" in text
    assert "shop/404" in text
    assert block_report("訪客結帳", "https://secure.store.apple.com/hk-zh/shop/checkout") == (
        "【請複製呢段到對話】；步驟=訪客結帳；"
        "網址=https://secure.store.apple.com/hk-zh/shop/checkout；"
        "標題=（無）；被擋頁=否"
    )


class _FakeNavPage:
    def __init__(self, url: str) -> None:
        self.url = url

    async def wait_for_url(self, *_args, **_kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_wait_if_checkout_blocked_detects_404_not_bag() -> None:
    assert await wait_if_checkout_blocked(_FakeNavPage("https://www.apple.com/hk-zh/shop/404"))
    assert not await wait_if_checkout_blocked(
        _FakeNavPage("https://www.apple.com/hk-zh/shop/bag")
    )


def test_product_option_patterns_match_current_apple_hk_labels() -> None:
    assert NO_TRADEIN_PATTERN.search("不換購")
    assert NO_APPLECARE_PATTERN.search("無 AppleCare+ 服務計劃保障")
    assert SKIP_PATTERN.search("不換購")
    assert SKIP_PATTERN.search("無 AppleCare+ 服務計劃保障")
    assert ADD_BAG_PATTERN.search("加入購物袋")
    assert ADD_BAG_PATTERN.search("Add to Bag") is not None
    assert not ADD_BAG_PATTERN.search("使用 Apple Pay 結帳")
    assert VIEW_BAG_PATTERN.search("查看購物袋")
    assert CHECKOUT_PATTERN.search("結帳")
    assert not CHECKOUT_PATTERN.search("使用 Apple Pay 結帳")
    assert CONTINUE_PATTERN.search("繼續前往付款")
    assert CREDIT_CARD_PATTERN.search("信用卡或扣帳卡")
    assert REVIEW_ORDER_PATTERN.search("檢查你的訂單")
    assert PICKUP_PATTERN.search("我會前來取貨")
    assert DELIVERY_PATTERN.search("我希望送貨")
    assert not PICKUP_PATTERN.search("取貨分店")
    assert not DELIVERY_PATTERN.search("送貨地址")


class _FakeResponse:
    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status


def test_add_to_cart_541_is_treated_as_blocked() -> None:
    assert _response_looks_blocked(
        _FakeResponse(
            "https://www.apple.com/hk-zh/shop/buy-iphone/iphone-17e?product=MHRV4ZA/A&add-to-cart=add-to-cart",
            541,
        )
    )
    assert not _response_looks_blocked(
        _FakeResponse(
            "https://www.apple.com/hk-zh/shop/fulfillment-messages?parts.0=MGDM4ZA/A",
            541,
        )
    )
    assert not _response_looks_blocked(
        _FakeResponse("https://www.apple.com/hk-zh/shop/bag", 200)
    )


def test_checkout_stage_follows_iphone_guest_pickup_urls() -> None:
    assert checkout_stage(
        "https://www.apple.com/hk-zh/shop/buy-iphone/iphone-17e?product=mhrv4za/a&step=attach"
    ) == "attach"
    assert checkout_stage("https://www.apple.com/hk-zh/shop/bag") == "bag"
    assert checkout_stage(
        "https://secure6.store.apple.com/hk-zh/shop/signIn?ssi=abc"
    ) == "signin"
    assert checkout_stage(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Fulfillment-init"
    ) == "fulfillment"
    assert checkout_stage(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=PickupContact-init"
    ) == "contact"
    assert checkout_stage(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Shipping-init"
    ) == "shipping"
    assert checkout_stage(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Billing-init"
    ) == "billing"


class _FakeQtyHandle:
    def __init__(self, page: "_FakeQtyPage") -> None:
        self._page = page
        self.first = self

    async def wait_for(self, **_kwargs) -> None:
        return None

    async def select_option(self, value=None, label=None, **_kwargs) -> None:
        candidate = value or label
        if candidate not in self._page.options:
            raise RuntimeError("no option")
        self._page.selected = candidate


class _FakeQtyPage:
    def __init__(self, options: list[str]) -> None:
        self.options = options
        self.selected = "1"

    def locator(self, _selector: str) -> _FakeQtyHandle:
        return _FakeQtyHandle(self)

    def get_by_label(self, _pattern) -> _FakeQtyHandle:
        return _FakeQtyHandle(self)


@pytest.mark.asyncio
async def test_bag_quantity_selects_two() -> None:
    page = _FakeQtyPage(["1", "2"])
    assert await _set_bag_quantity(page, 2) == 2
    assert page.selected == "2"


class _FakeHandle:
    def __init__(self, page: "_FakeProductPage", kind: str) -> None:
        self._page = page
        self._kind = kind
        self.first = self

    async def wait_for(self, **_kwargs) -> None:
        return None

    async def is_enabled(self) -> bool:
        if self._kind != "add_bag":
            return True
        return self._page.tradein_declined and self._page.applecare_declined

    async def is_visible(self) -> bool:
        return True

    async def count(self) -> int:
        return 1

    async def click(self, **_kwargs) -> None:
        self._page.clicks.append(self._kind)
        if self._kind == "no_tradein":
            self._page.tradein_declined = True
        elif self._kind == "no_applecare":
            self._page.applecare_declined = True
        elif self._kind == "add_bag":
            if not await self.is_enabled():
                raise RuntimeError("add-to-bag is disabled until options are selected")
            self._page.added = True

    def filter(self, **_kwargs) -> "_FakeHandle":
        return self


class _FakeProductPage:
    def __init__(self) -> None:
        self.clicks: list[str] = []
        self.tradein_declined = False
        self.applecare_declined = False
        self.added = False

    def _handle(self, pattern, fallback: str) -> _FakeHandle:
        text = pattern.pattern if hasattr(pattern, "pattern") else str(pattern)
        if "不換購" in text or "trade" in text.lower():
            return _FakeHandle(self, "no_tradein")
        if "AppleCare" in text:
            return _FakeHandle(self, "no_applecare")
        if "加入購物袋" in text or "add-to-cart" in text:
            return _FakeHandle(self, "add_bag")
        return _FakeHandle(self, fallback)

    def get_by_label(self, pattern):
        return self._handle(pattern, "label")

    def get_by_role(self, role, name=None):
        return self._handle(name or role, role)

    def get_by_text(self, pattern):
        return self._handle(pattern, "text")

    def locator(self, selector: str):
        return self._handle(selector, "locator")


@pytest.mark.asyncio
async def test_decline_options_before_add_to_bag() -> None:
    page = _FakeProductPage()
    assert await _click_add_to_bag(page) is False
    assert page.added is False
    await _decline_tradein_and_applecare(page)
    assert page.clicks[:2] == ["no_tradein", "no_applecare"]
    assert page.tradein_declined and page.applecare_declined
    assert await _click_add_to_bag(page)
    assert page.added is True
    assert page.clicks[-1] == "add_bag"


def test_performance_report_lists_four_steps() -> None:
    result = CheckoutResult(
        ok=True,
        reason="dry_run",
        timings={"add_bag": 1.2, "enter_checkout": 0.8, "fulfillment": 2.5, "payment": 0.6},
        total_seconds=5.1,
    )
    report = result.report()
    assert "Step 1 加車" in report
    assert "Step 2 進入結帳" in report
    assert "Step 3 處理取貨/送貨" in report
    assert "Step 4 到達付款前最後一步" in report
    assert "5.10 秒" in report
    assert INTERRUPT_MESSAGE.startswith("⚠️")


def test_frontend_exposes_checkout_and_fulfillment_controls() -> None:
    js = Path("static/js/app.js").read_text()
    page = Path("templates/index.html").read_text()
    assert "結帳模式 (Checkout Mode)" in js
    assert "訪客 (Guest) 模式" in js
    assert "門市自取 (Store Pickup)" in js
    assert "送貨上門 (Home Delivery)" in js
    assert "guest-cvv" in js
    assert "delivery-days" in js
    assert "訪客模式請填妥" in js
    assert "填晒先可以儲存同開始運作" in js
    assert "可以再改再存" in js
    assert "guestHasMaskedCard" in js
    assert "訪客資料已修改成功" in js
    assert "guestResave" in js
    assert "slice(-2)" in js
    assert "唔會填 12/2028" in js
    assert "MM/YY" in js
    assert "guest-address-street" in js
    assert "guest-address-building" in js
    assert "屋苑或大廈" in js
    assert "請選擇" in js
    assert 'card_month: ""' in js
    assert "digits.length < 3" in js
    assert "待命（已填妥資料）" in js
    assert "maxlength=\"16\"" in js
    assert "slice(0, 16)" in js
    assert "paused" in js
    assert "揀結帳模式" in page
    readme = Path("README.md").read_text()
    assert "組合 A：Apple ID + 門市自取" in readme
    assert "組合 D：訪客 + 送貨上門" in readme
    assert "User Journey" in readme or "你點用" in readme
    assert "不換購" in readme
    assert "無 AppleCare+" in readme
    assert "以訪客身份繼續" in readme
    assert "已撳「以訪客身份繼續」" in readme
    assert "--no-sandbox" in readme
    assert "signInx" in readme
    assert "本機 Google Chrome" in readme
    assert "屋企 IP 都被當 bot" in readme
    assert "Duo 冇貨" in readme
    assert "MHRV4ZA/A" in readme
    assert "揀返 Duo" in readme
    assert "3.2–3.9 秒" in readme
    assert "【請複製呢段到對話】" in readme
    assert "平時用嘅 Chrome" in readme
    assert "唔會填 12/2028" in readme
    assert "訪客資料已修改成功" in readme
    assert "MM/YY" in readme
    assert "查看購物袋" in readme
    assert "繼續前往付款" in readme
    assert "信用卡或扣帳卡" in readme
    assert "檢查你的訂單" in readme
    assert "使用 Apple Pay 結帳" in readme
    assert "我會前來取貨" in readme
    assert "我希望送貨" in readme
    assert "Shipping-init" in readme
    assert "訪客模式搶購流程" in readme
    assert "PickupContact-init" in readme
    assert "Billing-init" in readme
    assert "step=attach" in readme
