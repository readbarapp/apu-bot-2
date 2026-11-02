from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.inventory import (
    INVENTORY_BLOCK_PAUSE_AFTER,
    backoff_seconds,
    days_from_quote,
    is_rate_limited,
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
    url = pickup_url("MK2E4ZA/A")
    assert "pickup-message" in url
    assert "hk-zh" in url
    assert "MK2E4ZA" in url
    assert "Hong+Kong" in url or "Hong%20Kong" in url


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
    assert not is_rate_limited(200)
    assert backoff_seconds(1) == 12
    assert backoff_seconds(2) == 24
    assert backoff_seconds(3) == 48
    assert INVENTORY_BLOCK_PAUSE_AFTER == 4
