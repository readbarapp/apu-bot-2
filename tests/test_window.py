from __future__ import annotations

import os
from typing import Any

import pytest

from bot.window import (
    PREFERRED_CHANNELS,
    STEALTH_INIT_SCRIPT,
    browser_launch_message,
    launch_stealth_context,
    persistent_launch_kwargs,
)


class _FakeContext:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    async def add_init_script(self, script: str) -> None:
        self.scripts.append(script)


class _FakeChromium:
    def __init__(self, fail: tuple[str | None, ...] = ()) -> None:
        self.fail = set(fail)
        self.calls: list[str | None] = []
        self.kwargs: list[dict[str, Any]] = []

    async def launch_persistent_context(self, user_data_dir: str, **kwargs: Any):
        channel = kwargs.get("channel")
        self.calls.append(channel)
        self.kwargs.append(kwargs)
        if channel in self.fail or (channel is None and "chromium" in self.fail):
            raise RuntimeError(f"missing {channel or 'chromium'}")
        return _FakeContext()


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


def test_persistent_launch_hides_playwright_automation_flags() -> None:
    options = persistent_launch_kwargs("session_worker_1")
    assert options["headless"] is False
    assert options["locale"] == "zh-HK"
    assert options["timezone_id"] == "Asia/Hong_Kong"
    assert options["extra_http_headers"]["Accept-Language"].startswith("zh-HK")
    assert "--enable-automation" in options["ignore_default_args"]
    assert options["chromium_sandbox"] is (os.name == "nt")
    if os.name == "nt":
        assert "--no-sandbox" in options["ignore_default_args"]
    else:
        assert "--no-sandbox" not in options["ignore_default_args"]
    assert any("AutomationControlled" in arg for arg in options["args"])
    assert "channel" not in options
    assert "webdriver" in STEALTH_INIT_SCRIPT
    chrome = persistent_launch_kwargs("session_worker_1", channel="chrome")
    assert chrome["channel"] == "chrome"


def test_preferred_channels_are_real_browsers_first() -> None:
    assert PREFERRED_CHANNELS == ("chrome", "msedge")


def test_browser_launch_message_tells_user_which_engine() -> None:
    assert "Google Chrome" in browser_launch_message("chrome")
    assert "Edge" in browser_launch_message("msedge")
    assert "Chromium" in browser_launch_message("chromium")
    assert "安裝 Google Chrome" in browser_launch_message("chromium")


@pytest.mark.asyncio
async def test_launch_prefers_installed_chrome() -> None:
    chromium = _FakeChromium()
    context, label = await launch_stealth_context(_FakePlaywright(chromium), "sessions/x")
    assert label == "chrome"
    assert chromium.calls == ["chrome"]
    assert context.scripts and "webdriver" in context.scripts[0]
    assert "--enable-automation" in chromium.kwargs[0]["ignore_default_args"]


@pytest.mark.asyncio
async def test_launch_falls_back_to_edge_then_chromium() -> None:
    chromium = _FakeChromium(fail=("chrome", "msedge"))
    context, label = await launch_stealth_context(_FakePlaywright(chromium), "sessions/x")
    assert label == "chromium"
    assert chromium.calls == ["chrome", "msedge", None]
    assert "channel" not in chromium.kwargs[-1]
    assert isinstance(context, _FakeContext)


@pytest.mark.asyncio
async def test_launch_raises_after_every_engine_fails() -> None:
    chromium = _FakeChromium(fail=("chrome", "msedge", "chromium"))
    with pytest.raises(RuntimeError, match="無法啟動瀏覽器"):
        await launch_stealth_context(_FakePlaywright(chromium), "sessions/x")
    assert chromium.calls == ["chrome", "msedge", None]
