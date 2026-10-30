from __future__ import annotations

from typing import Any


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
