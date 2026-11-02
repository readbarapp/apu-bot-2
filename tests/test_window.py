from bot.window import STEALTH_INIT_SCRIPT, persistent_launch_kwargs


def test_persistent_launch_hides_playwright_automation_flags() -> None:
    options = persistent_launch_kwargs("session_worker_1")
    assert options["headless"] is False
    assert options["locale"] == "zh-HK"
    assert options["timezone_id"] == "Asia/Hong_Kong"
    assert options["extra_http_headers"]["Accept-Language"].startswith("zh-HK")
    assert "--enable-automation" in options["ignore_default_args"]
    assert any("AutomationControlled" in arg for arg in options["args"])
    assert "webdriver" in STEALTH_INIT_SCRIPT
