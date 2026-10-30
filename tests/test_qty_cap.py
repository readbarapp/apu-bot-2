from __future__ import annotations

from bot.checkout import CheckoutResult
from bot.inventory import StockMatch
from bot.models import WorkerProfile
from bot.worker import Worker

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
