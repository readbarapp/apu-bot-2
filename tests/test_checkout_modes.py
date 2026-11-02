from __future__ import annotations

from pathlib import Path
import re
import time

import pytest

from bot.inventory import StockMatch
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
    PICKUP_LOCATION_PATTERN,
    PICKUP_LOCATION_UI_PATTERN,
    APPLY_PATTERN,
    REVIEW_ORDER_PATTERN,
    SKIP_PATTERN,
    VIEW_BAG_PATTERN,
    _click_add_to_bag,
    _continue_as_guest,
    PICKUP_DETAILS_CONTINUE_PATTERN,
    _apply_pickup_location,
    _pickup_search_queries,
    _click_earliest_slot,
    _empty_bag,
    _handle_fulfillment,
    _select_pickup_store,
    _fill_phone,
    _guest_nav_done,
    _still_on_signin,
    guest_block_extra,
    _decline_tradein_and_applecare,
    _choose_credit_card,
    _click_pickup_details_continue,
    _fill_billing,
    _fill_card_expiry,
    _fill_contact,
    _fill_guest,
    hk_phone_number,
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
from bot.secrets import (
    encrypt_text,
    decrypt_text,
    public_guest,
    save_guest_secrets,
    load_guest_secrets,
    merge_guest_payload,
)

SAMPLE_WORKER = {
    "id": "w1",
    "name": "Worker_1",
    "session_dir": "session_worker_1",
    "sku": "MK2E4ZA/A",
    "stores": ["R428", "R409"],
    "pickup_window": "1d",
    "max_qty": 1,
    "checkout_mode": "guest",
    "guest": {
        "last_name": "Chan",
        "first_name": "Tai Man",
        "email": "chan@example.com",
        "phone": "51234567",
        "address_street": "中環金融街 8 號",
        "address_building": "國際金融中心一期 15 樓 1501 室",
        "card_number": "4111111111111111",
        "card_month": "12",
        "card_year": "2028",
        "cvv": "123",
    },
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


def test_empty_session_dir_is_auto_assigned(client) -> None:
    payload = {**SAMPLE_WORKER, "id": "auto1", "session_dir": ""}
    response = client.post("/api/start", json={"test_mode": True, "workers": [payload]})
    assert response.status_code == 200, response.text
    assert response.json()["workers"][0]["session_dir"].startswith("session_guest_")
    client.post("/api/stop")


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
    assert hk_phone_number("51234567") == "51234567"
    assert hk_phone_number("+852 5123 4567") == "51234567"
    assert hk_phone_number("85251234567") == "51234567"


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

    async def is_visible(self) -> bool:
        return self._kind in self._page.fields

    def filter(self, has_text=None, **_kwargs):
        return _FakeExpiryHandle(self._page, "missing")

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
        "id": "g_missing_cvv",
        "session_dir": "session_guest_missing_cvv",
        "guest": {**SAMPLE_GUEST["guest"], "cvv": ""},
    }
    no_card = {
        **SAMPLE_GUEST,
        "id": "g_missing_card",
        "session_dir": "session_guest_missing_card",
        "guest": {**SAMPLE_GUEST["guest"], "card_number": ""},
    }
    assert client.post("/api/start", json={"test_mode": True, "workers": [no_cvv]}).status_code == 400
    assert client.post("/api/start", json={"test_mode": True, "workers": [no_card]}).status_code == 400


def test_guest_can_start_with_blank_card_fields_after_secrets(client) -> None:
    first = client.post("/api/workers/secrets", json={"test_mode": True, "worker": SAMPLE_GUEST})
    assert first.status_code == 200, first.text
    blank = {
        **SAMPLE_GUEST,
        "guest": {**SAMPLE_GUEST["guest"], "card_number": "", "cvv": ""},
    }
    started = client.post("/api/start", json={"test_mode": True, "workers": [blank]})
    assert started.status_code == 200, started.text
    client.post("/api/stop")


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


def test_delete_worker_removes_secrets(client) -> None:
    saved = client.post("/api/workers/secrets", json={"test_mode": True, "worker": SAMPLE_GUEST})
    assert saved.status_code == 200
    assert load_guest_secrets("g1") is not None
    gone = client.delete("/api/workers/g1?session_dir=session_guest_1")
    assert gone.status_code == 200, gone.text
    assert load_guest_secrets("g1") is None


def test_merge_skips_masked_cvv(client) -> None:
    saved = client.post("/api/workers/secrets", json={"test_mode": True, "worker": SAMPLE_GUEST})
    assert saved.status_code == 200
    merged = merge_guest_payload(
        "g1",
        {**SAMPLE_GUEST["guest"], "card_number": "•••• 1111", "cvv": "•••"},
    )
    assert merged["card_number"] == "4111111111111111"
    assert merged["cvv"] == "123"


def test_delete_session_dir_only_inside_sessions(tmp_path, monkeypatch) -> None:
    root = tmp_path / "sessions"
    monkeypatch.setattr("bot.worker.SESSIONS_ROOT", root)
    from bot.worker import delete_session_dir

    folder = root / "session_abc"
    folder.mkdir(parents=True)
    (folder / "x.txt").write_text("keep-me-not", encoding="utf-8")
    delete_session_dir("session_abc")
    assert not folder.exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    delete_session_dir(str(outside))
    assert outside.exists()


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
    assert "未跳去結帳" in guest_block_extra("guest_nav_timeout")
    assert "唔好連撳訪客" in guest_block_extra("guest_nav_timeout")
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
async def test_continue_as_guest_waits_if_still_on_signin() -> None:
    page = _FakeGuestPage("https://secure.store.apple.com/hk-zh/shop/signIn?ssi=abc")
    assert await _continue_as_guest(page) == "guest_clicked"
    assert page.clicks


def test_guest_nav_done_uses_path_not_query() -> None:
    signin = (
        "https://secure6.store.apple.com/hk-zh/shop/signIn?ssi="
        "abccheckoutstartFulfillment"
    )
    assert _still_on_signin(signin)
    assert not _guest_nav_done(signin)
    assert _guest_nav_done(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Fulfillment-init"
    )
    assert _guest_nav_done("https://www.apple.com/hk-zh/shop/404")
    assert not _still_on_signin(
        "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Fulfillment-init"
    )


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
    assert CONTINUE_PATTERN.search("繼續前往取貨詳情")
    assert PICKUP_DETAILS_CONTINUE_PATTERN.search("繼續前往取貨詳情")
    assert not PICKUP_DETAILS_CONTINUE_PATTERN.search("繼續前往付款")
    assert CONTINUE_PATTERN.search("繼續前往送貨詳情")
    assert not CONTINUE_PATTERN.search("我希望送貨")
    assert not CONTINUE_PATTERN.search("我會前來取貨")
    assert CREDIT_CARD_PATTERN.search("信用卡或扣帳卡")
    assert REVIEW_ORDER_PATTERN.search("檢查你的訂單")
    assert PICKUP_PATTERN.search("我會前來取貨")
    assert APPLY_PATTERN.search("套用")
    assert APPLY_PATTERN.search("Apply")
    assert PICKUP_LOCATION_PATTERN.search("地區（例如「中環」）")
    assert PICKUP_LOCATION_UI_PATTERN.search("了解你可在哪裡取貨。")
    assert PICKUP_LOCATION_UI_PATTERN.search("地區（例如「中環」）")
    assert DELIVERY_PATTERN.search("我希望送貨")


class _FakePickupPage:
    def __init__(self, mode: str = "placeholder") -> None:
        self.mode = mode
        self.filled: list[str] = []
        self.typed: list[str] = []
        self.clicks: list[str] = []
        self.value = ""
        self.stores_listed = mode == "already_applied"
        self.keyboard = self

    def _store_list_text(self, name) -> bool:
        text = str(getattr(name, "pattern", name) or "")
        return bool(
            re.search(
                r"正在顯示|ifc mall|Apple Store|Hysan|Festival Walk|Canton Road|"
                r"New Town Plaza|apm Hong Kong|取貨地點",
                text,
                re.I,
            )
        )

    def _visible(self, kind: str, name) -> bool:
        if self.mode == "missing":
            return False
        if self.mode == "already_applied":
            return kind == "text" and self._store_list_text(name)
        if kind == "text" and self._store_list_text(name):
            return self.stores_listed
        if self.mode == "placeholder":
            return True
        text = str(getattr(name, "pattern", name) or "")
        if kind in {"placeholder", "label"}:
            return False
        if kind == "locator":
            return bool(
                re.search(
                    r"storelocator|store-locator|storeLocator|searchInput|search-input|store-search",
                    text,
                    re.I,
                )
            )
        if kind in {"textbox", "combobox", "searchbox"}:
            return False
        return True

    def get_by_placeholder(self, pattern):
        return _FakePickupControl(self, "placeholder", pattern)

    def get_by_label(self, pattern):
        return _FakePickupControl(self, "label", pattern)

    def locator(self, selector: str):
        return _FakePickupControl(self, "locator", selector)

    def get_by_role(self, role: str, name=None, **_kwargs):
        return _FakePickupControl(self, role, name)

    def get_by_text(self, pattern, **_kwargs):
        return _FakePickupControl(self, "text", pattern)

    async def press(self, key: str) -> None:
        self.clicks.append(key)

    async def type(self, text: str, **_kwargs) -> None:
        self.typed.append(text)
        self.value = text
        self.filled.append(text)


class _FakePickupControl:
    def __init__(self, page: _FakePickupPage, kind: str, name) -> None:
        self._page = page
        self._kind = kind
        self._name = name
        self.first = self

    def _visible(self) -> bool:
        return self._page._visible(self._kind, self._name)

    async def wait_for(self, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(f"{self._kind}:{self._name}")

    async def is_visible(self) -> bool:
        return self._visible()

    async def fill(self, value: str, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(self._kind)
        self._page.value = value
        self._page.filled.append(value)

    async def input_value(self) -> str:
        return self._page.value

    async def click(self, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(self._kind)
        name = str(getattr(self._name, "pattern", self._name))
        self._page.clicks.append(name)
        if "套用" in name or "Apply" in name or "search-button" in name.lower() or "searchButton" in name:
            self._page.stores_listed = True

    async def get_attribute(self, name: str) -> str:
        if name == "type":
            return "text"
        return ""

    async def evaluate(self, _script: str) -> str:
        return "input"

    async def type(self, value: str, **_kwargs) -> None:
        await self.fill(value)

    async def press_sequentially(self, value: str, **_kwargs) -> None:
        await self.fill(value)

    async def is_checked(self) -> bool:
        return False

    async def is_enabled(self) -> bool:
        return True

    def filter(self, has_text=None, **_kwargs):
        return _FakePickupControl(self._page, self._kind, has_text or self._name)


@pytest.mark.asyncio
async def test_apply_pickup_location_fills_hong_kong_and_clicks_apply() -> None:
    from bot.catalogs import PICKUP_LOCATION

    page = _FakePickupPage()
    assert await _apply_pickup_location(page) is True
    assert page.filled[0] == PICKUP_LOCATION
    assert page.filled[0] == "Hong Kong"
    assert any(
        "套用" in click or "Apply" in click or "search-button" in click.lower() or "storelocator" in click.lower()
        for click in page.clicks
    )
    assert not PICKUP_PATTERN.search("取貨分店")
    assert not DELIVERY_PATTERN.search("送貨地址")


@pytest.mark.asyncio
async def test_apply_pickup_location_fills_apple_store_search_input() -> None:
    from bot.catalogs import PICKUP_LOCATION

    page = _FakePickupPage(mode="search_input")
    assert await _apply_pickup_location(page, timeout=2000) is True
    assert page.filled[0] == PICKUP_LOCATION
    assert page.value == "Hong Kong"
    assert any("search" in click.lower() or "storelocator" in click.lower() for click in page.clicks)


@pytest.mark.asyncio
async def test_apply_pickup_location_reports_missing_district_field() -> None:
    page = _FakePickupPage(mode="missing")
    assert await _apply_pickup_location(page, timeout=400) is False
    assert page.filled == []


@pytest.mark.asyncio
async def test_apply_pickup_location_skips_when_stores_already_listed() -> None:
    page = _FakePickupPage(mode="already_applied")
    assert await _apply_pickup_location(page, timeout=400) is True
    assert page.filled == []


IFC_MATCH = StockMatch(
    store_id="R428",
    store_name="ifc mall",
    sku="MK2E4ZA/A",
    quote="今天可取貨",
    days=0,
    pickup_display="available",
)


class _FakeFulfillmentPage:
    CONTACT_URL = "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=PickupContact-init"
    FULFILL_URL = "https://secure6.store.apple.com/hk-zh/shop/checkout?_s=Fulfillment-init"

    def __init__(self, *, stores_listed: bool = True) -> None:
        self.url = self.FULFILL_URL
        self.pickup_checked = stores_listed
        self.stores_listed = stores_listed
        self.store_checked: str | None = None
        self.filled: list[str] = []
        self.clicks: list[str] = []
        self.pickup_clicks = 0
        self.continue_clicks = 0
        self.keyboard = self

    def get_by_placeholder(self, pattern):
        return _FakeFulfillHandle(self, "placeholder", pattern)

    def get_by_label(self, pattern):
        return _FakeFulfillHandle(self, "label", pattern)

    def locator(self, selector: str):
        return _FakeFulfillHandle(self, "locator", selector)

    def get_by_role(self, role: str, name=None, **_kwargs):
        return _FakeFulfillHandle(self, role, name)

    def get_by_text(self, pattern, **_kwargs):
        return _FakeFulfillHandle(self, "text", pattern)

    async def wait_for_url(self, pattern, timeout: int = 0):
        if re.search(getattr(pattern, "pattern", pattern), self.url, re.I):
            return
        raise TimeoutError(self.url)

    async def press(self, key: str) -> None:
        self.clicks.append(key)


class _FakeFulfillHandle:
    def __init__(self, page: _FakeFulfillmentPage, kind: str, name) -> None:
        self._page = page
        self._kind = kind
        self._name = name
        self.first = self

    def _text(self) -> str:
        return str(getattr(self._name, "pattern", self._name) or "")

    def _is_pickup(self) -> bool:
        return bool(PICKUP_PATTERN.search(self._text()))

    def _is_continue(self) -> bool:
        return bool(PICKUP_DETAILS_CONTINUE_PATTERN.search(self._text())) or bool(
            re.search(r"fulfillmentContinue|pickup-continue|fulfillment-continue", self._text(), re.I)
        )

    def _is_store_radio(self) -> bool:
        text = self._text()
        return "R428" in text and bool(
            re.search(r"input|radio|data-store|data-autom", text, re.I)
        )

    def _is_store_text(self) -> bool:
        return bool(re.search(r"ifc mall|R428", self._text(), re.I)) and not self._is_store_radio()

    def _is_listed_copy(self) -> bool:
        return bool(re.search(r"正在顯示|ifc mall|Apple Store|取貨地點", self._text(), re.I))

    def _visible(self) -> bool:
        if self._is_continue():
            return True
        if self._is_listed_copy():
            return self._page.stores_listed
        if self._is_store_radio() or self._is_store_text():
            return self._page.stores_listed
        if self._is_pickup():
            return True
        if self._kind == "locator" and re.search(
            r"storelocator|searchInput|search-button|套用|Apply", self._text(), re.I
        ):
            return True
        if self._kind in {"placeholder", "label"} and PICKUP_LOCATION_PATTERN.search(self._text()):
            return True
        return self._kind in {"button", "radio", "textbox"}

    async def wait_for(self, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(f"{self._kind}:{self._name}")

    async def is_visible(self) -> bool:
        return self._visible()

    async def count(self) -> int:
        return 1 if self._visible() else 0

    async def is_enabled(self) -> bool:
        if self._is_continue():
            return self._page.store_checked == "R428"
        return True

    async def is_checked(self) -> bool:
        if self._is_pickup():
            return self._page.pickup_checked
        if self._is_store_radio():
            return self._page.store_checked == "R428"
        return False

    async def get_attribute(self, name: str) -> str:
        if name == "aria-checked":
            return "true" if await self.is_checked() else "false"
        if name == "type":
            return "radio" if self._is_store_radio() or self._is_pickup() else "text"
        return ""

    async def fill(self, value: str, **_kwargs) -> None:
        self._page.filled.append(value)

    async def input_value(self) -> str:
        return self._page.filled[-1] if self._page.filled else ""

    async def click(self, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(self._kind)
        if self._is_continue() and not await self.is_enabled():
            raise TimeoutError("continue disabled")
        self._page.clicks.append(self._text())
        if self._is_pickup():
            self._page.pickup_clicks += 1
            if self._page.pickup_checked:
                self._page.stores_listed = False
                self._page.store_checked = None
            self._page.pickup_checked = True
            return
        if self._is_store_radio():
            self._page.store_checked = "R428"
            return
        if self._is_continue():
            self._page.continue_clicks += 1
            self._page.url = _FakeFulfillmentPage.CONTACT_URL
            return
        if "套用" in self._text() or "Apply" in self._text() or "search-button" in self._text().lower():
            self._page.stores_listed = True

    def filter(self, has_text=None, **_kwargs):
        return _FakeFulfillHandle(self._page, "label", has_text or self._name)

    async def evaluate(self, _script: str) -> str:
        return "input"


def test_pickup_search_queries_prefer_area_over_hong_kong() -> None:
    assert _pickup_search_queries(IFC_MATCH) == ["中環", "ifc mall", "Hong Kong"]


@pytest.mark.asyncio
async def test_select_pickup_store_does_not_reclick_pickup_when_list_visible() -> None:
    page = _FakeFulfillmentPage(stores_listed=True)
    assert await _select_pickup_store(page, IFC_MATCH, timeout=1500) is True
    assert page.pickup_clicks == 0
    assert page.filled == []
    assert page.store_checked == "R428"


@pytest.mark.asyncio
async def test_select_pickup_store_searches_area_before_hong_kong() -> None:
    page = _FakeFulfillmentPage(stores_listed=False)
    assert await _select_pickup_store(page, IFC_MATCH, timeout=1500) is True
    assert page.filled[0] == "中環"
    assert "Hong Kong" not in page.filled
    assert page.store_checked == "R428"


@pytest.mark.asyncio
async def test_handle_fulfillment_clicks_continue_once_without_reapplying_hong_kong() -> None:
    page = _FakeFulfillmentPage(stores_listed=True)
    assert await _handle_fulfillment(page, IFC_MATCH, "pickup", "guest", None, 7) is None
    assert page.filled == []
    assert page.pickup_clicks == 0
    assert page.continue_clicks == 1
    assert "PickupContact" in page.url


class _FakeContactPage:
    def __init__(self) -> None:
        self.filled: dict[str, str] = {}
        self.clicks: list[str] = []

    def locator(self, selector: str):
        if re.search(r"tel|phone|fullDaytimePhone", selector, re.I):
            return _FakeContactHandle(self, "phone", "tel")
        return _FakeContactHandle(self, "missing", "text")

    def get_by_label(self, pattern):
        text = pattern.pattern if hasattr(pattern, "pattern") else str(pattern)
        if re.search(text, "我沒有手提電話號碼"):
            return _FakeContactHandle(self, "no_mobile", "checkbox")
        if re.search(text, "手提電話號碼"):
            return _FakeContactHandle(self, "phone", "tel")
        return _FakeContactHandle(self, "missing", "text")

    def get_by_placeholder(self, pattern):
        return self.get_by_label(pattern)

    def get_by_role(self, _role, name=None, **_kwargs):
        return self.get_by_label(name or _role)

    def get_by_text(self, pattern, **_kwargs):
        return self.get_by_label(pattern)


class _FakeContactHandle:
    def __init__(self, page: _FakeContactPage, kind: str, input_type: str) -> None:
        self._page = page
        self._kind = kind
        self._type = input_type
        self.first = self

    async def wait_for(self, **_kwargs) -> None:
        if self._kind == "missing":
            raise TimeoutError(self._kind)

    async def count(self) -> int:
        return 0 if self._kind == "missing" else 1

    async def is_visible(self) -> bool:
        return self._kind != "missing"

    async def get_attribute(self, name: str) -> str:
        if name == "type":
            return self._type
        return ""

    async def evaluate(self, _script: str) -> str:
        return "input"

    async def click(self, **_kwargs) -> None:
        self._page.clicks.append(self._kind)

    async def fill(self, value: str, **_kwargs) -> None:
        if self._type in {"checkbox", "radio"}:
            raise RuntimeError("cannot fill checkbox")
        self._page.filled[self._kind] = value


@pytest.mark.asyncio
async def test_fill_phone_uses_tel_input_not_no_mobile_checkbox() -> None:
    page = _FakeContactPage()
    assert await _fill_phone(page, "+852 5123 4567") is True
    assert page.filled["phone"] == "51234567"
    assert "no_mobile" not in page.clicks


@pytest.mark.asyncio
async def test_fill_contact_fills_phone() -> None:
    page = _FakeContactPage()
    guest = GuestProfile(
        last_name="testing",
        first_name="testing",
        email="testing@gmail.com",
        phone="51234567",
    )
    await _fill_contact(page, guest)
    assert page.filled["phone"] == "51234567"


BILLING_GUEST = GuestProfile(
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


class _FakeBillingPage:
    BILLING_URL = "https://secure7.store.apple.com/hk-zh/shop/checkout?_s=Billing-init"

    def __init__(self, *, button_delay: float = 0.0) -> None:
        self.url = self.BILLING_URL
        self.button_delay = button_delay
        self.started = time.perf_counter()
        self.method_clicked = False
        self.clicks: list[str] = []
        self.filled: dict[str, str] = {}

    def _button_ready(self) -> bool:
        return time.perf_counter() - self.started >= self.button_delay

    def get_by_placeholder(self, pattern, **_kwargs):
        return _FakeBillingHandle(self, "placeholder", pattern)

    def get_by_label(self, pattern, **_kwargs):
        return _FakeBillingHandle(self, "label", pattern)

    def locator(self, selector: str):
        return _FakeBillingHandle(self, "locator", selector)

    def get_by_role(self, role: str, name=None, **_kwargs):
        return _FakeBillingHandle(self, role, name)

    def get_by_text(self, pattern, **_kwargs):
        return _FakeBillingHandle(self, "text", pattern)


class _FakeBillingHandle:
    def __init__(self, page: _FakeBillingPage, kind: str, name) -> None:
        self._page = page
        self._kind = kind
        self._name = name
        self.first = self

    def _text(self) -> str:
        return str(getattr(self._name, "pattern", self._name) or "")

    def _is_card_number(self) -> bool:
        return bool(re.search(r"卡號|信用卡號碼|cardNumber|cc-number|card-number", self._text(), re.I))

    def _is_credit_method(self) -> bool:
        text = self._text()
        if self._is_card_number():
            return False
        if CREDIT_CARD_PATTERN.search(text):
            return True
        return bool(re.search(r"creditcard|credit-card|creditCard|credit_card", text, re.I))

    def _is_broad_card_autom(self) -> bool:
        text = self._text()
        return bool(re.search(r'data-autom\*=["\']card["\']', text, re.I)) and "credit" not in text.lower()

    def _visible(self) -> bool:
        if self._is_broad_card_autom():
            return True
        if self._is_credit_method():
            return self._page._button_ready()
        if self._is_card_number():
            return self._page.method_clicked
        return False

    async def wait_for(self, **_kwargs) -> None:
        if not self._visible():
            raise TimeoutError(self._text())

    async def is_visible(self) -> bool:
        return self._visible()

    async def count(self) -> int:
        return 1 if self._visible() or self._is_broad_card_autom() else 0

    async def click(self, **_kwargs) -> None:
        if self._is_broad_card_autom() and not self._is_credit_method():
            self._page.clicks.append("wrong-card-autom")
            return
        if not self._visible():
            raise TimeoutError("not visible")
        if self._is_credit_method():
            self._page.method_clicked = True
            self._page.clicks.append("credit-card")
            return
        self._page.clicks.append(self._text())

    async def fill(self, value: str, **_kwargs) -> None:
        if self._is_card_number():
            self._page.filled["card_number"] = value
            return
        self._page.filled[self._text() or self._kind] = value

    async def get_attribute(self, _name: str) -> str:
        return ""

    async def evaluate(self, _script: str) -> str:
        return "input"

    async def scroll_into_view_if_needed(self, **_kwargs) -> None:
        return None

    def filter(self, has_text=None, **_kwargs):
        return _FakeBillingHandle(self._page, "label", has_text or self._name)


@pytest.mark.asyncio
async def test_choose_credit_card_clicks_as_soon_as_button_appears() -> None:
    page = _FakeBillingPage(button_delay=0.35)
    started = time.perf_counter()
    assert await _choose_credit_card(page) is True
    elapsed = time.perf_counter() - started
    assert page.method_clicked is True
    assert page.clicks[0] == "credit-card"
    assert "wrong-card-autom" not in page.clicks
    assert elapsed < 1.8


@pytest.mark.asyncio
async def test_choose_credit_card_does_not_click_generic_card_autom() -> None:
    page = _FakeBillingPage(button_delay=0.2)
    await _choose_credit_card(page)
    assert "wrong-card-autom" not in page.clicks
    assert "credit-card" in page.clicks


@pytest.mark.asyncio
async def test_fill_billing_clicks_payment_method_then_fills_card_number() -> None:
    page = _FakeBillingPage(button_delay=0.25)
    await _fill_billing(page, BILLING_GUEST)
    assert page.method_clicked is True
    assert page.filled.get("card_number") == "4111111111111111"
    assert "wrong-card-autom" not in page.clicks


@pytest.mark.asyncio
async def test_click_pickup_details_continue_returns_when_already_on_contact() -> None:
    page = _FakeFulfillmentPage(stores_listed=True)
    page.url = _FakeFulfillmentPage.CONTACT_URL
    started = time.perf_counter()
    assert await _click_pickup_details_continue(page, timeout=4000) is True
    assert page.continue_clicks == 0
    assert time.perf_counter() - started < 0.5


class _FakeSlotPage:
    def __init__(self, *, has_slot: bool = False) -> None:
        self.clicks: list[str] = []
        self.has_slot = has_slot

    def locator(self, selector: str):
        is_slot = bool(re.search(r"timeslot|time-slot|timeSlot", selector, re.I))
        if is_slot:
            if self.has_slot:
                return _FakeSlotControl(self, "slot", "上午 10:00", visible=True)
            return _FakeSlotControl(self, "missing", "", visible=False)
        return _FakeSlotControl(self, "delivery", "我希望送貨", visible=True)

    def get_by_role(self, role: str, name=None, **_kwargs):
        if name is None:
            return _FakeSlotControl(self, "delivery", "我希望送貨", visible=True)
        matched = hasattr(name, "search") and bool(name.search("上午 10:00"))
        if self.has_slot and role in {"radio", "button"} and matched:
            return _FakeSlotControl(self, "slot", "上午 10:00", visible=True)
        return _FakeSlotControl(self, "missing", "", visible=False)

    def get_by_label(self, pattern, **_kwargs):
        if self.has_slot and hasattr(pattern, "search") and pattern.search("上午 10:00"):
            return _FakeSlotControl(self, "slot", "上午 10:00", visible=True)
        return _FakeSlotControl(self, "missing", "", visible=False)


class _FakeSlotControl:
    def __init__(self, page: _FakeSlotPage, kind: str, label: str, visible: bool) -> None:
        self._page = page
        self._kind = kind
        self._label = label
        self._visible = visible
        self.first = self

    async def wait_for(self, **_kwargs) -> None:
        if not self._visible:
            raise TimeoutError(self._kind)

    async def click(self, **_kwargs) -> None:
        if not self._visible:
            raise TimeoutError(self._kind)
        self._page.clicks.append(self._kind)

    async def inner_text(self) -> str:
        return self._label

    async def get_attribute(self, _name: str) -> str:
        return self._label


@pytest.mark.asyncio
async def test_click_earliest_slot_does_not_click_delivery_radio() -> None:
    page = _FakeSlotPage(has_slot=False)
    assert await _click_earliest_slot(page) is False
    assert page.clicks == []


@pytest.mark.asyncio
async def test_click_earliest_slot_clicks_timeslot_not_delivery() -> None:
    page = _FakeSlotPage(has_slot=True)
    assert await _click_earliest_slot(page) is True
    assert page.clicks == ["slot"]


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


class _FakeBagPage:
    def __init__(self, items: int) -> None:
        self.url = "https://www.apple.com/hk-zh/shop/bag"
        self.items = items
        self.removed = 0
        self.wait_for_calls = 0

    def get_by_role(self, _role, name=None, **_kwargs):
        return _FakeBagHandle(self, name)

    def get_by_text(self, pattern, **_kwargs):
        return _FakeBagHandle(self, pattern)

    def locator(self, selector: str):
        return _FakeBagHandle(self, selector)

    async def goto(self, url, **_kwargs) -> None:
        self.url = url

    async def wait_for_url(self, *_args, **_kwargs) -> None:
        return None


class _FakeBagHandle:
    def __init__(self, page: _FakeBagPage, name) -> None:
        self._page = page
        self._name = str(getattr(name, "pattern", name) or "")
        self.first = self

    def _is_remove(self) -> bool:
        return bool(re.search(r"移除|Remove|remove", self._name, re.I))

    async def wait_for(self, **_kwargs) -> None:
        self._page.wait_for_calls += 1
        if self._page.items <= 0 or not self._is_remove():
            raise TimeoutError("no remove")

    async def is_visible(self) -> bool:
        return self._page.items > 0 and self._is_remove()

    async def click(self, **_kwargs) -> None:
        if self._page.items <= 0:
            raise TimeoutError("empty")
        self._page.items -= 1
        self._page.removed += 1

    async def count(self) -> int:
        return 1 if self._page.items and self._is_remove() else 0


@pytest.mark.asyncio
async def test_empty_bag_removes_leftover_items() -> None:
    page = _FakeBagPage(2)
    assert await _empty_bag(page) == 2
    assert page.items == 0
    assert page.removed == 2
    assert page.wait_for_calls == 0


@pytest.mark.asyncio
async def test_empty_bag_returns_immediately_when_already_empty() -> None:
    page = _FakeBagPage(0)
    assert await _empty_bag(page) == 0
    assert page.removed == 0
    assert page.wait_for_calls == 0


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


def test_performance_report_lists_pages_not_four_coarse_steps() -> None:
    result = CheckoutResult(
        ok=True,
        reason="dry_run",
        timings={
            "pdp": 0.8,
            "add_bag": 1.2,
            "bag": 0.4,
            "checkout": 1.6,
            "guest": 2.1,
            "pickup_search": 3.4,
            "pickup_store": 1.1,
            "pickup_continue": 0.9,
            "contact": 1.5,
            "contact_continue": 0.6,
            "billing": 2.4,
            "review": 0.7,
        },
        total_seconds=16.7,
    )
    report = result.report()
    assert "產品頁（不換購／無 AppleCare+）" in report
    assert "登入牆（以訪客身份繼續）" in report
    assert "填地區／套用門市" in report
    assert "揀指定門市" in report
    assert "繼續前往取貨詳情" in report
    assert "取貨人資料" in report
    assert "信用卡／帳單頁" in report
    assert "檢查訂單頁" in report
    assert "16.70 秒" in report
    assert "Step 1 加車" not in report
    assert INTERRUPT_MESSAGE.startswith("⚠️")


def test_performance_report_includes_total_when_stopped_at_card() -> None:
    result = CheckoutResult(
        ok=True,
        reason="dry_run",
        timings={"add_bag": 1.1, "checkout": 0.9, "guest": 2.0, "pickup_store": 3.2, "billing": 2.4},
        total_seconds=8.25,
    )
    report = result.report()
    assert "信用卡／帳單頁" in report
    assert "總耗時 8.25 秒" in report
    assert "檢查訂單頁" not in report


def test_frontend_exposes_checkout_and_fulfillment_controls() -> None:
    js = Path("static/js/app.js").read_text()
    page = Path("templates/index.html").read_text()
    assert "訪客 · 門市自取" in js
    assert "訪客 · 送貨上門" in js
    assert "guest-cvv" in js
    assert "delivery-days" in js
    assert "訪客模式請填妥" in js
    assert "填晒先可以儲存同開始運作" in js
    assert "都可以再撳「儲存此 Worker」" in js
    assert "guestHasMaskedCard" in js
    assert "guestHasStoredCard" in js
    assert "已儲存信用卡" in js
    assert "畫面顯示圓點" in js
    assert "removeWorker" in js
    assert "collapseWorkerCard" in js
    assert "而家未有 Worker。請撳「新增 Worker」加入搶購程序。" in js
    assert "session_${short}" in js
    assert "訪客資料已修改成功" in js
    assert "document.activeElement !== cardInput" in js
    assert "document.activeElement !== cvvInput" in js
    assert "...incoming, guest" not in js
    assert "incoming.guest" not in js
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
    assert "maxlength=\"19\"" in js
    assert "slice(0, 16)" in js
    assert "paused" in js
    assert "唔使登入 Apple ID" in page
    assert "撳「登入 Apple ID」" not in js
    assert '<select class="checkout-mode">' not in js
    assert "結帳模式" not in js
    assert 'class="login"' not in js
    readme = Path("README.md").read_text()
    assert "組合 A：訪客 + 門市自取" in readme
    assert "組合 B：訪客 + 送貨上門" in readme
    assert "初次點樣登入 Apple ID" not in readme
    assert "唔開瀏覽器會唔會快啲" in readme
    assert "有頭（headed）本機 Chrome" in readme
    assert "唔好用無痕視窗" in readme
    assert "唔使自己開無痕" in readme
    assert "唔會撳立即下單" in readme
    assert "計時｜" in readme
    assert "每個結帳分頁" in readme
    assert "已撳「信用卡或扣帳卡」" in Path("bot/checkout.py").read_text()
    assert "暫停計時" in Path("bot/checkout.py").read_text()
    assert "計時｜" in Path("bot/checkout.py").read_text()
    assert "清購物袋會唔會拖慢搶貨" in readme
    assert "唔會再繞去購物袋" in readme
    assert "已清走購物袋" in Path("bot/checkout.py").read_text()
    assert "empty_bag=not self._bag_cleared" in Path("bot/worker.py").read_text()
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
    assert "繼續前往取貨詳情" in readme
    assert "信用卡或扣帳卡" in readme
    assert "已撳「信用卡或扣帳卡」" in readme
    assert "入晒所有資料之後即停計時" in readme
    assert "檢查你的訂單" in readme
    assert "使用 Apple Pay 結帳" in readme
    assert "我會前來取貨" in readme
    assert "Hong Kong" in readme
    assert "套用" in readme
    assert "該店地區" in readme
    assert "store radio" in readme.lower() or "Store ID" in readme
    assert "自動收合" in readme
    assert "我希望送貨" in readme
    assert "Shipping-init" in readme
    assert "訪客模式搶購流程" in readme
    assert "我更新咗程式之後你要點做" in readme
    assert "請新增 Worker 加入搶購程序" in readme
    assert "新增嘅卡唔會帶返舊卡資料" in readme
    assert "唔使重新裝 Python" in readme
    assert "更新完程式，洗唔洗清 cookie" in readme
    assert "PickupContact-init" in readme
    assert "Billing-init" in readme
    assert "step=attach" in readme
