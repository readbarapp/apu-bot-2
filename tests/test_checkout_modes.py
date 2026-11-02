from __future__ import annotations

from pathlib import Path

from bot.checkout import CheckoutResult, INTERRUPT_MESSAGE
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
        "address": "1 IFC, Central, Hong Kong",
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
    assert "待命（已填妥資料）" in js
    assert "maxlength=\"16\"" in js
    assert "slice(0, 16)" in js
    assert "paused" in js
    assert "揀結帳模式" in page
    readme = Path("README.md").read_text()
    assert "組合 A：Apple ID + 門市自取" in readme
    assert "組合 D：訪客 + 送貨上門" in readme
    assert "User Journey" in readme or "你點用" in readme
