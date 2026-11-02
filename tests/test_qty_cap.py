from __future__ import annotations

from bot.checkout import CheckoutResult
from bot.inventory import StockMatch
from bot.models import GuestProfile, WorkerProfile
from bot.worker import WATCH_HEARTBEAT_POLLS, Worker

GUEST = GuestProfile(
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

IFC = StockMatch(
    store_id="R428",
    store_name="ifc mall",
    sku="MK2E4ZA/A",
    quote="今天可取貨",
    days=0,
    pickup_display="available",
)
SHA_TIN = StockMatch(
    store_id="R610",
    store_name="New Town Plaza",
    sku="MK2E4ZA/A",
    quote="今天可取貨",
    days=0,
    pickup_display="available",
)


async def test_qty_cap_counts_all_selected_stores_together(monkeypatch) -> None:
    profile = WorkerProfile(
        id="w1",
        name="Worker_1",
        session_dir="session_worker_1",
        sku="MK2E4ZA/A",
        stores=["R428", "R610"],
        pickup_window="1d",
        max_qty=2,
        guest=GUEST,
    )
    worker = Worker(profile, test_mode=True, playwright=None)
    worker.context = object()
    worker.logged_in = True
    worker.apple_id = "tester@icloud.com"

    checkouts: list[str] = []

    async def fake_inventory() -> list[StockMatch]:
        if len(checkouts) == 0:
            return [IFC]
        if len(checkouts) == 1:
            return [SHA_TIN]
        return [IFC, SHA_TIN]

    async def fake_page():
        return object()

    async def fake_checkout(page, **kwargs) -> CheckoutResult:
        checkouts.append(kwargs["match"].store_id)
        return CheckoutResult(ok=True, reason="dry_run")

    monkeypatch.setattr(worker, "_check_inventory", fake_inventory)
    monkeypatch.setattr(worker, "_page", fake_page)
    monkeypatch.setattr("bot.worker.run_checkout", fake_checkout)
    monkeypatch.setattr("bot.worker.next_poll_delay", lambda *_args, **_kwargs: 0)

    await worker._snipe_loop()

    assert checkouts == ["R428", "R610"]
    assert worker.purchased == 2
    assert worker.status == "dry_run_paused"
    assert worker.sniping is False


def _guest_worker() -> Worker:
    profile = WorkerProfile(
        id="w1",
        name="Worker_1",
        session_dir="session_worker_1",
        sku="MK2L4ZA/A",
        stores=["R428"],
        pickup_window="1d",
        max_qty=1,
        checkout_mode="guest",
        guest=GUEST,
    )
    worker = Worker(profile, test_mode=True, playwright=None)
    worker.context = object()
    worker.status = "watching"
    worker.last_message = "開始搶購（訪客）"
    worker.sniping = True
    return worker


async def test_snipe_loop_logs_oos_heartbeat(monkeypatch) -> None:
    worker = _guest_worker()
    polls = {"n": 0}
    logs: list[str] = []

    async def fake_inventory() -> list:
        polls["n"] += 1
        if polls["n"] >= WATCH_HEARTBEAT_POLLS:
            worker.snipe_stop.set()
        return []

    def fake_set(status: str, message: str, *, level: str = "info") -> None:
        logs.append(message)
        worker.status = status
        worker.last_message = message

    monkeypatch.setattr(worker, "_check_inventory", fake_inventory)
    monkeypatch.setattr(worker, "_set", fake_set)
    monkeypatch.setattr("bot.worker.next_poll_delay", lambda *_args, **_kwargs: 0)

    await worker._snipe_loop()

    assert any("正在查貨：第 1 次仍暫無供應" in msg for msg in logs)
    assert any(f"第 {WATCH_HEARTBEAT_POLLS} 次仍暫無供應" in msg for msg in logs)
    assert any("唔會整頁 refresh" in msg for msg in logs)
    assert any("官網 JSON 200" in msg for msg in logs)


async def test_dry_run_last_message_includes_timing_report(monkeypatch) -> None:
    worker = _guest_worker()

    async def fake_inventory() -> list:
        return [IFC]

    async def fake_page():
        return object()

    async def fake_checkout(page, **kwargs) -> CheckoutResult:
        return CheckoutResult(
            ok=True,
            reason="dry_run",
            timings={"add_bag": 1.0, "billing": 2.0},
            total_seconds=12.34,
        )

    monkeypatch.setattr(worker, "_check_inventory", fake_inventory)
    monkeypatch.setattr(worker, "_page", fake_page)
    monkeypatch.setattr("bot.worker.run_checkout", fake_checkout)
    monkeypatch.setattr("bot.worker.next_poll_delay", lambda *_args, **_kwargs: 0)

    await worker._snipe_loop()

    assert worker.status == "dry_run_paused"
    assert "效能實測報告" in worker.last_message
    assert "總耗時 12.34 秒" in worker.last_message
