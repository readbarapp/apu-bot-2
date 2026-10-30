from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bot.catalogs import APPLE_LOCALE, APPLE_ORIGIN, PICKUP_LOCATION, PICKUP_WINDOW_BY_ID

HK = ZoneInfo("Asia/Hong_Kong")

UNAVAILABLE_MARKERS = (
    "暫無供應",
    "目前無法提供",
    "暫時無法提供",
    "currently unavailable",
    "not available",
    "unavailable",
)

AVAILABLE_DISPLAYS = {"available", "instock", "in_stock", "ok"}
UNAVAILABLE_DISPLAYS = {"unavailable", "ineligible", "unknown"}

CN_NUM = {
    "零": 0,
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "星期一": 0,
    "星期二": 1,
    "星期三": 2,
    "星期四": 3,
    "星期五": 4,
    "星期六": 5,
    "星期日": 6,
    "週一": 0,
    "週二": 1,
    "週三": 2,
    "週四": 3,
    "週五": 4,
    "週六": 5,
    "週日": 6,
    "周日": 6,
}


@dataclass(frozen=True)
class StockMatch:
    store_id: str
    store_name: str
    sku: str
    quote: str
    days: int
    pickup_display: str


def pickup_url(sku: str, location: str = PICKUP_LOCATION) -> str:
    query = urlencode({"pl": "true", "parts.0": sku, "location": location})
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/retail/pickup-message?{query}"


def _today(now: datetime | None = None) -> date:
    current = now or datetime.now(HK)
    return current.astimezone(HK).date()


def _extract_stores(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, dict):
        return []
    stores = body.get("stores")
    if isinstance(stores, list):
        return [store for store in stores if isinstance(store, dict)]
    content = body.get("content")
    if isinstance(content, dict):
        pickup = content.get("pickupMessage")
        if isinstance(pickup, dict) and isinstance(pickup.get("stores"), list):
            return [store for store in pickup["stores"] if isinstance(store, dict)]
    return []


def _availability_blob(store: dict[str, Any], sku: str) -> dict[str, Any]:
    parts = store.get("partsAvailability") or store.get("parts") or {}
    if not isinstance(parts, dict):
        return {}
    blob = parts.get(sku) or parts.get(sku.replace("/", "%2F"))
    return blob if isinstance(blob, dict) else {}


def _quote_from_blob(blob: dict[str, Any]) -> str:
    regular = (blob.get("messageTypes") or {}).get("regular") or {}
    compact = (blob.get("messageTypes") or {}).get("compact") or {}
    pieces = [
        blob.get("pickupSearchQuote"),
        blob.get("storePickupQuote"),
        regular.get("storePickupQuote") if isinstance(regular, dict) else None,
        regular.get("pickupSearchQuote") if isinstance(regular, dict) else None,
        compact.get("storePickupQuote") if isinstance(compact, dict) else None,
    ]
    return " ".join(str(piece) for piece in pieces if piece)


def days_from_quote(quote: str, now: datetime | None = None) -> int | None:
    text = (quote or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if any(marker in text or marker in lowered for marker in UNAVAILABLE_MARKERS):
        return None
    if any(token in text for token in ("今天", "今日", "此刻", "現可取貨", "現在可取貨")) or "today" in lowered:
        return 0
    if any(token in text for token in ("明天", "翌日")) or "tomorrow" in lowered:
        return 1
    if "後日" in text or "day after tomorrow" in lowered:
        return 2

    md = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if md:
        return _days_until_month_day(int(md.group(1)), int(md.group(2)), now)

    slash = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if slash:
        return _days_until_month_day(int(slash.group(1)), int(slash.group(2)), now)

    numeric = re.search(r"(\d+)\s*(?:個)?\s*(?:工作)?\s*[日天](?:後|內)?", text)
    if numeric:
        return int(numeric.group(1))

    cn_day = re.search(r"([一二兩三四五六七八九十])\s*(?:個)?\s*(?:工作)?\s*[日天](?:後|內)?", text)
    if cn_day:
        return CN_NUM.get(cn_day.group(1))

    for label, weekday in WEEKDAYS.items():
        if label in text or label in lowered:
            return _days_until_weekday(weekday, now)

    if "可取貨" in text or "available" in lowered:
        return 0
    return None


def _days_until_month_day(month: int, day: int, now: datetime | None) -> int | None:
    today = _today(now)
    try:
        target = date(today.year, month, day)
    except ValueError:
        return None
    if target < today:
        try:
            target = date(today.year + 1, month, day)
        except ValueError:
            return None
    return (target - today).days


def _days_until_weekday(weekday: int, now: datetime | None) -> int:
    today = _today(now)
    delta = (weekday - today.weekday()) % 7
    return delta


def window_max_days(pickup_window: str) -> int:
    item = PICKUP_WINDOW_BY_ID.get(pickup_window)
    if not item:
        raise ValueError(f"unknown pickup window: {pickup_window}")
    return int(item["max_days"])


def matches_window(days: int | None, pickup_window: str) -> bool:
    return days is not None and 0 <= days <= window_max_days(pickup_window)


def _is_buyable(blob: dict[str, Any]) -> bool:
    display = str(blob.get("pickupDisplay") or "").lower()
    if display in AVAILABLE_DISPLAYS:
        return True
    if display in UNAVAILABLE_DISPLAYS:
        return False

    buyability = blob.get("buyability") if isinstance(blob.get("buyability"), dict) else {}
    if buyability.get("isBuyable") is True:
        inventory = buyability.get("inventory")
        if inventory is None or inventory > 0:
            return True
    if blob.get("isBuyable") is True:
        inventory = blob.get("inventory")
        if inventory is None or inventory > 0:
            return True

    regular = blob.get("messageTypes", {}).get("regular") if isinstance(blob.get("messageTypes"), dict) else {}
    if isinstance(regular, dict) and regular.get("storeSelectionEnabled") is True:
        return True
    return False


def parse_pickup_payload(
    payload: dict[str, Any],
    sku: str,
    store_ids: list[str],
    pickup_window: str,
    now: datetime | None = None,
) -> list[StockMatch]:
    wanted = set(store_ids)
    matches: list[StockMatch] = []
    for store in _extract_stores(payload):
        store_id = str(store.get("storeNumber") or "").strip()
        if store_id not in wanted:
            continue
        blob = _availability_blob(store, sku)
        if not blob:
            continue
        quote = _quote_from_blob(blob)
        if not _is_buyable(blob):
            continue
        days = days_from_quote(quote, now=now)
        duration = blob.get("pickupDurationInDays")
        if days is None and isinstance(duration, (int, float)):
            days = int(duration)
        if not matches_window(days, pickup_window):
            continue
        matches.append(
            StockMatch(
                store_id=store_id,
                store_name=str(store.get("storeName") or store_id),
                sku=sku,
                quote=quote.strip() or str(blob.get("pickupDisplay") or "available"),
                days=int(days or 0),
                pickup_display=str(blob.get("pickupDisplay") or ""),
            )
        )

    order = {store_id: index for index, store_id in enumerate(store_ids)}
    matches.sort(key=lambda item: order.get(item.store_id, 99))
    return matches


def is_rate_limited(status: int) -> bool:
    return status in {429, 503, 541}


def backoff_seconds(consecutive_blocks: int) -> float:
    return min(90.0, 12.0 * (2 ** max(0, consecutive_blocks - 1)))


def next_poll_delay(base_seconds: float, jitter: tuple[float, float], rng) -> float:
    low, high = jitter
    return max(0.8, base_seconds + rng.uniform(low, high))
