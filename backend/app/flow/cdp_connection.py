"""Connect to the tool's own Chrome over CDP (shared by the Flow and TikTok steps)."""

import time
from contextlib import contextmanager

from .chrome_launcher import FLOW_HOME, cdp_tabs, open_tab


class BrowserNotRunning(Exception):
    pass


def ensure_window(port: int) -> bool:
    """False when Chrome is not running. Playwright cannot attach to a Chrome whose windows were all
    closed ("Browser context management is not supported"), so open a Flow window first."""
    tabs = cdp_tabs(port)
    if tabs is None:
        return False
    if not tabs:
        try:
            open_tab(port, FLOW_HOME)
        except OSError as exc:
            raise BrowserNotRunning("Chrome của tool không còn cửa sổ nào. Bấm 'Mở Chrome cho Flow' trên giao diện.") from exc
        deadline = time.time() + 5
        while not cdp_tabs(port) and time.time() < deadline:
            time.sleep(0.3)
    return True


@contextmanager
def browser_context(port: int):
    """Yield the default BrowserContext of the running Chrome; never launches or closes it."""
    if not ensure_window(port):
        raise BrowserNotRunning("Chrome của tool chưa mở. Bấm 'Mở Chrome cho Flow' trên giao diện.")
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not browser.contexts:
            raise BrowserNotRunning("Chrome của tool chưa có cửa sổ nào. Mở lại Chrome cho Flow.")
        yield browser.contexts[0]
    finally:
        pw.stop()  # disconnect only; the user's Chrome window stays open


def capture_page_error(page, errors_dir) -> str | None:
    """Save a screenshot + HTML of `page`; return the screenshot path relative to the job dir."""
    import time

    try:
        errors_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shot = errors_dir / f"{stamp}.png"
        page.screenshot(path=str(shot))
        (errors_dir / f"{stamp}.html").write_text(page.content(), encoding="utf-8")
        return f"errors/{shot.name}"
    except Exception:
        return None
