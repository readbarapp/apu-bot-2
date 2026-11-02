from __future__ import annotations

from typing import Any

# Playwright otherwise sets navigator.webdriver and --enable-automation, which
# Apple Shield can treat like a bot even on a home IP.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


def persistent_launch_kwargs(user_data_dir: str) -> dict[str, Any]:
    return {
        "user_data_dir": user_data_dir,
        "headless": False,
        "viewport": {"width": 1440, "height": 900},
        "locale": "zh-HK",
        "timezone_id": "Asia/Hong_Kong",
        "extra_http_headers": {"Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }


async def apply_stealth(context: Any) -> None:
    if context is None:
        return
    try:
        await context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass


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
