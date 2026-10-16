"""The tool's Chrome may keep running with every window closed; then the tool opens one itself."""

from pathlib import Path

from app.flow import cdp_connection, chrome_launcher


class FakeCdp:
    """Stands in for Chrome's DevTools HTTP endpoint: /json/list and PUT /json/new."""

    def __init__(self, tabs):
        self.tabs, self.opened = tabs, []

    def list_tabs(self, port):
        return self.tabs

    def open_tab(self, port, url):
        self.opened.append(url)
        self.tabs = [{"type": "page", "url": url}]


def test_launch_button_opens_a_window_when_chrome_runs_without_one(monkeypatch):
    fake = FakeCdp(tabs=[])
    monkeypatch.setattr(chrome_launcher, "cdp_tabs", fake.list_tabs)
    monkeypatch.setattr(chrome_launcher, "open_tab", fake.open_tab)
    result = chrome_launcher.launch_chrome("/nonexistent/chrome", Path("/tmp/profile"), 9222)
    assert fake.opened == [chrome_launcher.FLOW_HOME] and "cửa sổ" in result["message"]


def test_launch_button_leaves_an_open_window_alone(monkeypatch):
    fake = FakeCdp(tabs=[{"type": "page", "url": "https://flow.google.com/"}])
    monkeypatch.setattr(chrome_launcher, "cdp_tabs", fake.list_tabs)
    monkeypatch.setattr(chrome_launcher, "open_tab", fake.open_tab)
    assert chrome_launcher.launch_chrome("/nonexistent/chrome", Path("/tmp/profile"), 9222)["launched"] is False
    assert fake.opened == []


def test_steps_reopen_a_window_before_attaching(monkeypatch):
    fake = FakeCdp(tabs=[])
    monkeypatch.setattr(cdp_connection, "cdp_tabs", fake.list_tabs)
    monkeypatch.setattr(cdp_connection, "open_tab", fake.open_tab)
    cdp_connection.ensure_window(9222)
    assert fake.opened == [chrome_launcher.FLOW_HOME]
    cdp_connection.ensure_window(9222)  # a window exists now: nothing more to open
    assert len(fake.opened) == 1


def test_new_tab_opens_in_the_background_without_focusing_chrome():
    # context.new_page() and page.bring_to_front() made Chrome the frontmost app on every run (measured 2026-10-16).
    sent, page = [], object()

    class Session:
        def send(self, method, params):
            sent.append((method, params))
            return {"targetId": "t1"}

        def detach(self):
            sent.append(("detach", None))

    class Context:
        class browser:
            @staticmethod
            def new_browser_cdp_session():
                return Session()

        def expect_page(self):
            class Waiter:
                value = page

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return Waiter()

    assert cdp_connection.new_tab(Context()) is page
    assert sent == [("Target.createTarget", {"url": "about:blank", "background": True}), ("detach", None)]
