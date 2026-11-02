from bot.account import cookies_indicate_apple_login, extract_email_from_text, looks_like_signin
from bot.worker import should_open_account_page


def test_extract_email_ignores_apple_system_addresses() -> None:
    html = "聯絡 support@apple.com 或用 my.shopper@icloud.com 登入"
    assert extract_email_from_text(html) == "my.shopper@icloud.com"


def test_extract_email_none_when_empty() -> None:
    assert extract_email_from_text("") is None
    assert extract_email_from_text("尚未登入") is None


def test_store_session_cookie_means_logged_in() -> None:
    assert cookies_indicate_apple_login([{"name": "myacinfo", "value": "token"}])
    assert not cookies_indicate_apple_login([{"name": "geo", "value": "HK"}])


def test_signin_url_detection() -> None:
    assert looks_like_signin("https://secure.store.apple.com/hk/shop/signIn")
    assert looks_like_signin("https://appleid.apple.com/auth/authenticate")
    assert not looks_like_signin("https://www.apple.com/hk-zh/shop/bag")


def test_guest_mode_never_opens_shop_account() -> None:
    assert not should_open_account_page("guest", sniping=False)
    assert not should_open_account_page("guest", sniping=True)
    assert should_open_account_page("apple_id", sniping=False)
    assert not should_open_account_page("apple_id", sniping=True)
