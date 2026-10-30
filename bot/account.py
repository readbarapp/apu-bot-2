from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
SKIP_EMAILS = {
    "noreply@apple.com",
    "appleid@id.apple.com",
    "support@apple.com",
    "webmaster@apple.com",
}


def extract_email_from_text(text: str) -> str | None:
    if not text:
        return None
    for match in EMAIL_RE.findall(text):
        email = match.strip().rstrip(".")
        if email.lower() in SKIP_EMAILS:
            continue
        if email.lower().endswith("@apple.com") and "icloud" not in email.lower():
            continue
        return email
    return None


def looks_like_signin(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in ("signin", "sign-in", "authenticate", "login"))


async def detect_apple_id(page) -> str | None:
    if page is None:
        return None
    try:
        url = page.url
    except Exception:
        url = ""
    if looks_like_signin(url):
        return None
    try:
        from_dom = await page.evaluate(
            """() => {
              const selectors = [
                '[data-autom*="email" i]',
                '[data-testid*="email" i]',
                '.rs-account-email',
                '#login-appleId',
                'input[type="email"]'
              ];
              for (const selector of selectors) {
                const node = document.querySelector(selector);
                if (!node) continue;
                const value = (node.value || node.textContent || "").trim();
                if (value.includes("@")) return value;
              }
              return document.body ? document.body.innerText : "";
            }"""
        )
    except Exception:
        from_dom = ""
    if isinstance(from_dom, str) and "@" in from_dom and " " not in from_dom.strip():
        return extract_email_from_text(from_dom) or from_dom.strip()
    return extract_email_from_text(str(from_dom or ""))
