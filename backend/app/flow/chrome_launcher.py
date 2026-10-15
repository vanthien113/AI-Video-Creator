"""Start a real Google Chrome with a dedicated profile and a CDP port, and report its tabs."""

import json
import subprocess
import urllib.request
from pathlib import Path

FLOW_HOME = "https://flow.google.com/"


def cdp_tabs(port: int) -> list[dict] | None:
    """Return open page tabs, or None when Chrome is not listening on the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
            tabs = json.loads(resp.read())
    except (OSError, ValueError):
        return None
    return [t for t in tabs if t.get("type") == "page"]


def open_tab(port: int, url: str) -> None:
    """New tab through the DevTools endpoint; Chrome opens a window for it if none is open."""
    request = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(request, timeout=5):
        pass


def chrome_status(port: int) -> dict:
    tabs = cdp_tabs(port)
    if tabs is None:
        return {"running": False, "state": "closed", "tabs": []}
    urls = [t.get("url", "") for t in tabs]
    if any("accounts.google.com" in u for u in urls):
        state = "login_required"
    elif any("flow.google.com" in u for u in urls):
        state = "ready"
    else:
        state = "open"
    return {"running": True, "state": state, "tabs": urls}


def launch_chrome(chrome_app: str, profile_dir: Path, port: int) -> dict:
    tabs = cdp_tabs(port)
    if tabs is not None:
        if not tabs:  # still running after its last window was closed
            open_tab(port, FLOW_HOME)
            return {"launched": False, "message": "Đã mở lại cửa sổ Chrome cho Flow."}
        return {"launched": False, "message": "Chrome đã mở sẵn."}
    if not Path(chrome_app).exists():
        raise FileNotFoundError(f"Không thấy Google Chrome tại {chrome_app}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [chrome_app, f"--user-data-dir={profile_dir}", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check", FLOW_HOME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    return {"launched": True, "message": "Đã mở Chrome. Đăng nhập Google trong cửa sổ này nếu chưa đăng nhập."}
