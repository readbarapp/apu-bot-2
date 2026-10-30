from __future__ import annotations

APPLE_ORIGIN = "https://www.apple.com"
APPLE_LOCALE = "hk-zh"
PICKUP_LOCATION = "Hong Kong"
POLL_SECONDS = 2.5
POLL_JITTER_SECONDS = (0.35, 1.15)
LAUNCH_STAGGER_SECONDS = 0.4
INVENTORY_TIMEOUT_MS = 15_000
CHECKOUT_STEP_TIMEOUT_MS = 12_000

STORES: list[dict[str, str]] = [
    {"id": "R428", "name": "ifc mall", "area": "中環"},
    {"id": "R409", "name": "Hysan Place", "area": "銅鑼灣"},
    {"id": "R499", "name": "Canton Road", "area": "尖沙咀"},
    {"id": "R485", "name": "Festival Walk", "area": "九龍塘"},
    {"id": "R673", "name": "apm Hong Kong", "area": "觀塘"},
    {"id": "R610", "name": "New Town Plaza", "area": "沙田"},
]

STORE_BY_ID = {store["id"]: store for store in STORES}

PRODUCTS: list[dict[str, str]] = [
    {"sku": "MK2D4ZA/A", "label": "iPhone Duo 256GB 星光白色", "family": "iphone-duo"},
    {"sku": "MK2E4ZA/A", "label": "iPhone Duo 256GB 夜空色", "family": "iphone-duo"},
    {"sku": "MK2F4ZA/A", "label": "iPhone Duo 512GB 星光白色", "family": "iphone-duo"},
    {"sku": "MK2G4ZA/A", "label": "iPhone Duo 512GB 夜空色", "family": "iphone-duo"},
    {"sku": "MK2H4ZA/A", "label": "iPhone Duo 1TB 星光白色", "family": "iphone-duo"},
    {"sku": "MK2J4ZA/A", "label": "iPhone Duo 1TB 夜空色", "family": "iphone-duo"},
    {"sku": "MK2K4ZA/A", "label": "iPhone Duo 2TB 星光白色", "family": "iphone-duo"},
    {"sku": "MK2L4ZA/A", "label": "iPhone Duo 2TB 夜空色", "family": "iphone-duo"},
]

PRODUCT_BY_SKU = {item["sku"]: item for item in PRODUCTS}

PICKUP_WINDOWS: list[dict[str, str | int]] = [
    {"id": "1d", "label": "一日內", "max_days": 1},
    {"id": "2d", "label": "兩日內", "max_days": 2},
    {"id": "3d", "label": "三日內", "max_days": 3},
]

PICKUP_WINDOW_BY_ID = {item["id"]: item for item in PICKUP_WINDOWS}

def catalog_payload() -> dict:
    return {
        "stores": STORES,
        "products": PRODUCTS,
        "pickup_windows": PICKUP_WINDOWS,
        "poll_seconds": POLL_SECONDS,
        "apple_origin": APPLE_ORIGIN,
        "apple_locale": APPLE_LOCALE,
    }


def product_url(sku: str) -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/goto/product/{sku}"


def bag_url() -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/bag"


def checkout_url() -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/checkout"


def shop_home_url() -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop"


def signin_url() -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/signIn"


def account_url() -> str:
    return f"{APPLE_ORIGIN}/{APPLE_LOCALE}/shop/account"
