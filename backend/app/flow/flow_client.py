"""Drive Google Flow in the user's real Chrome: project, ingredient upload, prompt (agent settings: flow_agent)."""

import random
import time
from contextlib import contextmanager
from pathlib import Path

from ..config import FlowConfig
from .cdp_connection import BrowserNotRunning, browser_context
from .flow_selectors import FlowSelectors, build_locator


IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class FlowError(Exception):
    """Something on the Flow page did not go as expected. `kind` drives retry policy."""

    def __init__(self, message: str, kind: str = "ui"):
        super().__init__(message)
        self.kind = kind  # ui | not_logged_in | out_of_credits | policy_blocked | generation_failed | timeout


class FlowClient:
    def __init__(self, page, selectors: FlowSelectors):
        self.page, self.sel = page, selectors

    # ---- small helpers ----------------------------------------------------
    @staticmethod
    def pause(low: float = 0.5, high: float = 1.5) -> None:
        time.sleep(random.uniform(low, high))

    def find(self, key: str, value=None):
        return self.sel.locate(self.page, key, value)

    def click(self, key: str, value=None, timeout: float = 15000, scope=None) -> None:
        """Click `key`, searched inside `scope` (a Locator) when given, else the whole page."""
        target = self.sel.locate(scope or self.page, key, value).first
        try:
            target.click(timeout=timeout)
        except Exception as exc:
            raise FlowError(f"Không bấm được '{key}' trên Flow ({type(exc).__name__}).") from exc
        self.pause()

    def dismiss_popups(self) -> None:
        for spec in self.sel.dismiss_specs():
            try:
                button = build_locator(self.page, spec)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=3000)
                    self.pause(0.5, 1)
            except Exception:
                pass  # popup vanished between check and click: nothing to dismiss

    def ensure_logged_in(self) -> None:
        if "accounts.google.com" in self.page.url:
            raise FlowError("Chrome chưa đăng nhập Google. Đăng nhập trong cửa sổ Chrome rồi thử lại.", "not_logged_in")

    # ---- project ----------------------------------------------------------
    def open_project(self, project_url: str | None) -> str:
        if project_url:
            # Always reload: leftover menus/overlays from an earlier run would block clicks.
            self.page.goto(project_url, wait_until="domcontentloaded")
        else:
            self.page.goto(self.sel.home_url, wait_until="domcontentloaded")
            self.pause(2, 3)
            self.ensure_logged_in()
            self.dismiss_popups()
            self.click("new_project_button")
            self.page.wait_for_url("**/project/**", timeout=30000)
        self.pause(2, 3)
        self.ensure_logged_in()
        self.dismiss_popups()
        self.find("prompt_box").first.wait_for(state="visible", timeout=30000)
        return self.page.url.split("?")[0]

    # ---- ingredient -------------------------------------------------------
    def clear_ingredients(self) -> None:
        for _ in range(10):
            remove = self.find("ingredient_remove_button")
            if not remove.count():
                return
            remove.first.click()
            self.pause(0.4, 0.8)

    def upload_ingredients(self, images: list[tuple[Path, str]]) -> None:
        """Put every (image, upload name) into the prompt box as an ingredient, main product image first."""
        self.clear_ingredients()
        for image, upload_name in images:
            self._add_ingredient(image, upload_name)

    def _add_ingredient(self, image: Path, upload_name: str) -> None:
        in_prompt = self.find("ingredient_in_prompt")
        before = in_prompt.count()
        self.click("add_ingredient_button")
        mime = IMAGE_MIME.get(image.suffix.lower(), "image/png")
        try:
            with self.page.expect_file_chooser(timeout=15000) as chooser:
                self.find("upload_media_button").first.click()
            chooser.value.set_files({"name": upload_name, "mimeType": mime, "buffer": image.read_bytes()})
        except FlowError:
            raise
        except Exception as exc:
            raise FlowError(f"Không mở được hộp chọn file trên Flow ({type(exc).__name__}).") from exc

        agree = self.find("rights_agree_button")
        try:
            agree.first.wait_for(state="visible", timeout=15000)
            agree.first.click()
        except Exception:
            pass  # dialog not shown (e.g. already accepted in this session)

        option = self.find("asset_option").filter(has_text=upload_name).first
        deadline = time.time() + 180
        while time.time() < deadline:
            if option.count() and "Uploading" not in option.inner_text():
                break
            time.sleep(1)
        else:
            raise FlowError("Tải ảnh lên Flow quá 3 phút chưa xong.")
        self.pause()
        option.click()
        self.pause()
        add = self.find("add_to_prompt_button")
        if add.count() and add.first.is_visible():  # picker sometimes shows a preview first
            add.first.click()
            self.pause()
        deadline = time.time() + 20
        while in_prompt.count() <= before:
            if time.time() > deadline:
                raise FlowError(f"Ảnh {upload_name} đã tải lên nhưng chưa vào ô prompt.")
            time.sleep(0.5)

    # ---- prompt + submit --------------------------------------------------
    def fill_prompt(self, text: str) -> None:
        box = self.find("prompt_box").first
        box.click()
        self.page.keyboard.press("Meta+A")
        self.page.keyboard.press("Backspace")
        self.page.keyboard.insert_text(text)
        self.pause()
        typed = box.inner_text().strip()
        if text[:40].strip() not in typed:
            raise FlowError("Không nhập được prompt vào Flow.")

    def submit(self) -> None:
        self.click("generate_button")


@contextmanager
def flow_session(cfg: FlowConfig, selectors: FlowSelectors | None = None):
    """Connect to the running Chrome and reuse (or open) the Flow tab."""
    selectors = selectors or FlowSelectors.load()
    try:
        with browser_context(cfg.cdp_port) as context:
            host = selectors.home_url.split("/")[2]
            page = next((p for p in context.pages if host in p.url), None) or context.new_page()
            page.bring_to_front()
            yield FlowClient(page, selectors)
    except BrowserNotRunning as exc:
        raise FlowError(str(exc), "not_logged_in") from exc
