from __future__ import annotations

import atexit
import logging
from typing import Any

# Chromium bindings cost ~100ms and are only needed once a browser launches.
lazy from playwright.sync_api import sync_playwright

from autotrade.config import Settings

logger = logging.getLogger(__name__)

VIEWPORT = {"width": 1600, "height": 1000}

_GONE_MARKERS = (
    "target page, context or browser has been closed",
    "browser has been closed",
    "playwright connection closed",
    "connection closed while reading from the driver",
    "event loop is closed",
    "target closed",
)

_active: list[dict[str, Any]] = []


class BrowserGone(RuntimeError):
    """Playwright session is dead — stop retrying."""


def is_browser_gone(exc: BaseException | None) -> bool:
    seen = 0
    while exc is not None and seen < 10:
        if isinstance(exc, BrowserGone):
            return True
        text = str(exc).lower()
        if any(m in text for m in _GONE_MARKERS):
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False


def require_live_browser(exc: BaseException) -> None:
    if is_browser_gone(exc):
        raise BrowserGone(
            "Playwright browser/driver is gone (Ctrl+C or crash)"
        ) from exc


# Selectors verified against d.easytrader.ir
LOGIN_USER = "#user-name"
LOGIN_PASS = "#password"
LOGIN_SUBMIT = "#primary_form button"
LOGIN_OK = 'li[data-cy="mw-menu-icon"]'
ANNOUNCEMENT_CANCEL = "#cancel-action-confirm-btn"
CLOCK = "#easy-clock-id"


def launch_browser(settings: Settings):
    pw = sync_playwright().start()
    if settings.chrome_user_data_dir:
        context = pw.chromium.launch_persistent_context(
            settings.chrome_user_data_dir,
            channel="chrome",
            headless=settings.headless,
            ignore_https_errors=True,
            viewport=VIEWPORT,
        )
        browser = None
    else:
        browser = pw.chromium.launch(channel="chrome", headless=settings.headless)
        context = browser.new_context(
            ignore_https_errors=True, viewport=VIEWPORT
        )

    pages = context.pages
    page = pages[0] if pages else context.new_page()
    session = {"pw": pw, "browser": browser, "context": context, "done": False}
    _active.append(session)
    atexit.register(_cleanup, session)
    tag = f" ({settings.instance_id})" if settings.instance_id else ""
    logger.info("Browser ready%s.", tag)
    return page, context


def _cleanup(session: dict[str, Any]) -> None:
    if session.get("done"):
        return
    session["done"] = True
    if session in _active:
        _active.remove(session)
    try:
        session["context"].close()
    except Exception as exc:
        if not is_browser_gone(exc):
            logger.warning("Error closing context: %s", exc)
    if session.get("browser") is not None:
        try:
            session["browser"].close()
        except Exception:
            pass
    try:
        session["pw"].stop()
    except Exception:
        pass


def cleanup_all() -> None:
    for session in list(_active):
        _cleanup(session)


def login(page: Any, settings: Settings) -> bool:
    if not settings.mofid_user or not settings.mofid_pass:
        logger.error("Set MOFID_USER and MOFID_PASS in .env")
        return False

    for attempt in range(1, settings.login_max_attempts + 1):
        logger.info("Login attempt %d/%d", attempt, settings.login_max_attempts)
        try:
            page.goto(settings.broker_url, wait_until="domcontentloaded")
            timeout_ms = int(settings.login_timeout * 1000)
            page.locator(LOGIN_USER).fill(settings.mofid_user, timeout=timeout_ms)
            page.locator(LOGIN_PASS).fill(settings.mofid_pass, timeout=timeout_ms)
            page.locator(LOGIN_SUBMIT).first.click(timeout=timeout_ms)
            page.locator(LOGIN_OK).first.wait_for(state="visible", timeout=timeout_ms)
            logger.info("Login successful.")
            return True
        except Exception as exc:
            require_live_browser(exc)
            logger.warning("Login attempt %d failed: %s", attempt, exc)
    logger.error("Login failed.")
    return False


def dismiss_announcement(page: Any) -> None:
    try:
        el = page.locator(ANNOUNCEMENT_CANCEL).first
        if el.count() == 0:
            return
        el.click(timeout=3000)
        logger.info("Announcement dismissed.")
    except Exception:
        pass
