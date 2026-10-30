from __future__ import annotations

from pathlib import Path

from bot.manager import manager

SAMPLE_WORKER = {
    "id": "w1",
    "name": "Worker_1",
    "session_dir": "session_worker_1",
    "sku": "MK2E4ZA/A",
    "stores": ["R428", "R409"],
    "pickup_window": "1d",
    "max_qty": 1,
}


def test_catalog_lists_hk_stores_and_duo_skus(client) -> None:
    data = client.get("/api/catalog").json()
    store_ids = {item["id"] for item in data["stores"]}
    assert store_ids == {"R428", "R409", "R499", "R485", "R673", "R610"}
    skus = {item["sku"] for item in data["products"]}
    assert "MK2E4ZA/A" in skus
    assert "MK2D4ZA/A" in skus
    labels = {item["label"] for item in data["pickup_windows"]}
    assert labels == {"一日內", "兩日內", "三日內"}


def test_index_and_frontend_assets(client) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "全域啟動 (Start)" in page.text
    assert "緊急停止所有 Bot (Emergency Stop)" in page.text
    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？" in js.text
    assert "window.confirm" in js.text
    assert "FALLBACK_CATALOG" in js.text
    assert "STATUS_LABELS" in js.text
    assert "待命（未啟動）" in js.text
    assert "儲存設定" in page.text
    assert "初次設定流程" in page.text
    assert "搶夠自動停" in page.text
    assert "複製做新 Apple ID" in js.text
    assert "mountWorker" in js.text
    preview = Path("preview.html").read_text()
    assert 'href="static/css/app.css"' in preview
    assert 'src="static/js/app.js"' in preview
    assert "預覽模式" in preview
    assert "儲存設定" in preview
    assert "加入此 SKU" in js.text
    assert "複製做新 Apple ID" in js.text
    assert "初次設定流程" in preview


def test_duplicate_session_dir_rejected(client) -> None:
    twin = {**SAMPLE_WORKER, "id": "w2", "name": "Worker_2"}
    response = client.post("/api/start", json={"test_mode": True, "workers": [SAMPLE_WORKER, twin]})
    assert response.status_code == 422


def test_start_requires_worker_and_known_store(client) -> None:
    empty = client.post("/api/start", json={"test_mode": True, "workers": []})
    assert empty.status_code == 422
    bad_store = client.post(
        "/api/start",
        json={"test_mode": True, "workers": [{**SAMPLE_WORKER, "stores": ["R000"]}]},
    )
    assert bad_store.status_code == 422


def test_frontend_driven_start_focus_and_emergency_stop(client) -> None:
    idle = client.get("/api/status").json()
    assert idle["running"] is False

    started = client.post("/api/start", json={"test_mode": True, "workers": [SAMPLE_WORKER]})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["running"] is True
    assert body["test_mode"] is True
    assert body["workers"][0]["status"] == "watching"
    worker = manager.workers["w1"]
    assert worker.focused >= 1

    focused = client.post("/api/workers/w1/focus")
    assert focused.status_code == 200
    assert worker.focused >= 2

    duplicate = client.post("/api/start", json={"test_mode": True, "workers": [SAMPLE_WORKER]})
    assert duplicate.status_code == 409

    stopped = client.post("/api/stop")
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
    assert manager.workers["w1"].status == "stopped"


def test_live_mode_is_backend_accepted_without_server_side_confirm(client) -> None:
    started = client.post("/api/start", json={"test_mode": False, "workers": [SAMPLE_WORKER]})
    assert started.status_code == 200
    assert started.json()["test_mode"] is False
    client.post("/api/stop")


def test_live_log_websocket_replays_history(client) -> None:
    with client.websocket_connect("/ws/logs") as socket:
        first = socket.receive_json()
        assert "message" in first
        assert "ts" in first


def test_confirm_copy_lives_only_on_frontend() -> None:
    js = Path("static/js/app.js").read_text()
    app = Path("app.py").read_text()
    assert "window.confirm" in js
    assert "window.confirm" not in app
