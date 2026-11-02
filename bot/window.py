from __future__ import annotations

from typing import Any

# Playwright otherwise sets navigator.webdriver and --enable-automation, which
# Apple Shield can treat like a bot even on a home IP.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""

PREFERRED_CHANNELS = ("chrome", "msedge")


def persistent_launch_kwargs(
    user_data_dir: str, channel: str | None = None
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "user_data_dir": user_data_dir,
        "headless": False,
        "viewport": {"width": 1440, "height": 900},
        "locale": "zh-HK",
        "timezone_id": "Asia/Hong_Kong",
        "extra_http_headers": {"Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if channel:
        options["channel"] = channel
    return options


def browser_launch_message(label: str) -> str:
    if label == "chrome":
        return "已用本機 Google Chrome 開視窗。呢個比 Playwright 內建 Chromium 更似平時上網。"
    if label == "msedge":
        return "搵唔到 Google Chrome，已改用本機 Microsoft Edge。"
    return (
        "搵唔到本機 Chrome／Edge，已改用 Playwright Chromium。"
        "若果加車或訪客結帳仍然 541，請先安裝 Google Chrome 再重開。"
    )


async def apply_stealth(context: Any) -> None:
    if context is None:
        return
    try:
        await context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass


async def launch_stealth_context(playwright: Any, user_data_dir: str) -> tuple[Any, str]:
    """Prefer installed Chrome/Edge; fall back to Playwright's Chromium."""
    last_error: Exception | None = None
    tried: list[str] = []
    for channel in (*PREFERRED_CHANNELS, None):
        label = channel or "chromium"
        tried.append(label)
        options = persistent_launch_kwargs(user_data_dir, channel=channel)
        path = options.pop("user_data_dir")
        try:
            context = await playwright.chromium.launch_persistent_context(path, **options)
        except Exception as exc:
            last_error = exc
            continue
        await apply_stealth(context)
        return context, label
    detail = last_error or RuntimeError("unknown launch error")
    raise RuntimeError(f"無法啟動瀏覽器（已試：{' / '.join(tried)}）：{detail}") from last_error


async def bring_context_to_front(context: Any) -> None:
    """Raise a Playwright persistent-context Chromium window to the foreground."""
    if context is None:
        return
    pages = list(getattr(context, "pages", []) or [])
    if not pages:
        return
    page = pages[-1]
    await page.bring_to_front()
    try:
        await page.evaluate("() => { try { window.focus(); } catch (e) {} }")
    except Exception:
        pass
    try:
        session = await context.new_cdp_session(page)
        info = await session.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id is not None:
            await session.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "normal"}},
            )
        target = await session.send("Target.getTargetInfo")
        target_id = (target.get("targetInfo") or {}).get("targetId")
        if target_id:
            await session.send("Target.activateTarget", {"targetId": target_id})
    except Exception:
        pass
