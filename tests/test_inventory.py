from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bot.inventory import (
    INVENTORY_BLOCK_PAUSE_AFTER,
    InventoryLimited,
    backoff_seconds,
    days_from_quote,
    fetch_json_in_page,
    fulfillment_url,
    inventory_urls,
    is_rate_limited,
    load_pickup_matches,
    looks_like_inventory_waf,
    matches_window,
    parse_pickup_payload,
    pickup_url,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pickup_mixed.json"
HK = ZoneInfo("Asia/Hong_Kong")
NOW = datetime(2026, 10, 30, 16, 0, tzinfo=HK)


def test_hong_kong_timezone_loads() -> None:
    assert HK.key == "Asia/Hong_Kong"


def test_pickup_url_contains_sku_and_hk_location() -> None:
    url = pickup_url("MK2L4ZA/A")
    assert "pickup-message" in url
    assert "hk-zh" in url
    assert "MK2L4ZA" in url
    assert "Hong+Kong" in url or "Hong%20Kong" in url


def test_fulfillment_url_matches_storefront_query() -> None:
    url = fulfillment_url("MK2L4ZA/A")
    assert "fulfillment-messages" in url
    assert "MK2L4ZA" in url
    assert "mts.0" in url or "mts.0=" in url
    assert inventory_urls("MK2L4ZA/A")[0] == url


def test_days_from_quote_variants() -> None:
    assert days_from_quote("今天可取貨", NOW) == 0
    assert days_from_quote("明天可取貨", NOW) == 1
    assert days_from_quote("3 日後可取貨", NOW) == 3
    assert days_from_quote("兩日後可取貨", NOW) == 2
    assert days_from_quote("11 月 1 日可取貨", NOW) == 2
    assert days_from_quote("暫無供應", NOW) is None


def test_window_filter() -> None:
    assert matches_window(0, "1d")
    assert matches_window(1, "1d")
    assert not matches_window(2, "1d")
    assert matches_window(3, "3d")
    assert not matches_window(4, "3d")
    assert not matches_window(None, "3d")


def test_parse_payload_honours_store_and_pickup_window() -> None:
    payload = json.loads(FIXTURE.read_text())
    matches = parse_pickup_payload(
        payload,
        sku="MK2E4ZA/A",
        store_ids=["R428", "R409", "R499"],
        pickup_window="1d",
        now=NOW,
    )
    assert [item.store_id for item in matches] == ["R428"]
    assert matches[0].days == 0

    three_day = parse_pickup_payload(
        payload,
        sku="MK2E4ZA/A",
        store_ids=["R499"],
        pickup_window="3d",
        now=NOW,
    )
    assert three_day == []

    ignored_store = parse_pickup_payload(
        payload,
        sku="MK2E4ZA/A",
        store_ids=["R409"],
        pickup_window="3d",
        now=NOW,
    )
    assert ignored_store == []


def test_inventory_541_is_rate_limited_and_backs_off() -> None:
    assert is_rate_limited(541)
    assert is_rate_limited(429)
    assert is_rate_limited(404)
    assert not is_rate_limited(200)
    assert looks_like_inventory_waf(541, None, "")
    assert looks_like_inventory_waf(200, None, "https://www.apple.com/hk-zh/shop/go/404")
    assert not looks_like_inventory_waf(200, {"body": {"stores": []}}, "")
    assert backoff_seconds(1) == 12
    assert backoff_seconds(2) == 24
    assert backoff_seconds(3) == 48
    assert INVENTORY_BLOCK_PAUSE_AFTER == 4


class _FakeFetchPage:
    def __init__(self, replies: list[tuple[int, dict | None]]) -> None:
        self.replies = list(replies)
        self.urls: list[str] = []

    async def evaluate(self, _script, url: str):
        self.urls.append(url)
        status, data = self.replies.pop(0)
        return {"status": status, "data": data}


@pytest.mark.asyncio
async def test_fetch_json_in_page_returns_status_and_payload() -> None:
    page = _FakeFetchPage([(200, {"body": {"stores": []}})])
    status, data, final_url = await fetch_json_in_page(
        page, "https://www.apple.com/hk-zh/shop/fulfillment-messages"
    )
    assert status == 200
    assert data == {"body": {"stores": []}}
    assert final_url == ""


@pytest.mark.asyncio
async def test_load_pickup_matches_oos_json_is_not_541() -> None:
    page = _FakeFetchPage([(200, {"body": {"stores": []}})])
    matches = await load_pickup_matches(
        page,
        sku="MK2L4ZA/A",
        store_ids=["R428"],
        pickup_window="1d",
    )
    assert matches == []
    assert "fulfillment-messages" in page.urls[0]


@pytest.mark.asyncio
async def test_load_pickup_matches_raises_after_both_endpoints_541() -> None:
    page = _FakeFetchPage([(541, None), (541, None)])
    with pytest.raises(InventoryLimited) as caught:
        await load_pickup_matches(
            page,
            sku="MK2L4ZA/A",
            store_ids=["R428"],
            pickup_window="1d",
        )
    assert caught.value.status == 541
    assert len(page.urls) == 2


@pytest.mark.asyncio
async def test_load_pickup_matches_404_after_waf_redirect_is_limited() -> None:
    page = _FakeFetchPage([(404, None), (404, None)])
    with pytest.raises(InventoryLimited) as caught:
        await load_pickup_matches(
            page,
            sku="MK2L4ZA/A",
            store_ids=["R428"],
            pickup_window="1d",
        )
    assert caught.value.status == 404


@pytest.mark.asyncio
async def test_load_pickup_matches_falls_back_when_first_endpoint_is_541() -> None:
    page = _FakeFetchPage([(541, None), (200, {"body": {"stores": []}})])
    matches = await load_pickup_matches(
        page,
        sku="MK2L4ZA/A",
        store_ids=["R428"],
        pickup_window="1d",
    )
    assert matches == []
    assert "pickup-message" in page.urls[1]


def test_worker_polls_inventory_inside_the_browser() -> None:
    text = Path("bot/worker.py").read_text(encoding="utf-8")
    assert "load_pickup_matches" in text
    assert "context.request.get" not in text
    assert "page.request" not in text
    assert "_open_product_watch_page" in text
    assert "InventoryLimited" in text
    assert "WATCH_HEARTBEAT_POLLS" in text
    assert "正在查貨" in text
