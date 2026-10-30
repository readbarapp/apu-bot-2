from bot.account import extract_email_from_text, looks_like_signin


def test_extract_email_ignores_apple_system_addresses() -> None:
    html = "聯絡 support@apple.com 或用 my.shopper@icloud.com 登入"
    assert extract_email_from_text(html) == "my.shopper@icloud.com"


def test_extract_email_none_when_empty() -> None:
    assert extract_email_from_text("") is None
    assert extract_email_from_text("尚未登入") is None


def test_signin_url_detection() -> None:
    assert looks_like_signin("https://secure.store.apple.com/hk/shop/signIn")
    assert looks_like_signin("https://appleid.apple.com/auth/authenticate")
    assert not looks_like_signin("https://www.apple.com/hk-zh/shop/bag")
