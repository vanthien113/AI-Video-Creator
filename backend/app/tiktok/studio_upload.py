"""Upload a video in TikTok Studio, fill the description, label it AI-generated, and Save draft.

Observed 2026-10-15: the upload page has a hidden <input type=file accept=video/*>; once a file is
chosen the form appears with a DraftJS description editor (pre-filled with the file name), a
"Show more" section holding the "AI-generated content" switch (turning it on opens a dialog:
"Not now" / "Turn on"), and the buttons Post / Save draft / Discard (data-e2e attributes).
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from ..config import ROOT, TikTokConfig
from ..flow.flow_selectors import FlowSelectors, build_locator

SELECTORS_FILE = ROOT / "tiktok-selectors.yaml"
MAX_DESCRIPTION = 2000


class StudioError(Exception):
    pass


def save_draft(page, cfg: TikTokConfig, video: Path, description: str,
               report: Callable[[float, str], None], log: Callable[[str], None],
               selectors: FlowSelectors | None = None) -> None:
    sel = selectors or FlowSelectors.load(SELECTORS_FILE)
    texts = {k: re.compile(v, re.I) for k, v in sel.data.get("texts", {}).items()}

    report(0.05, "Mở TikTok Studio")
    page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=60000)
    file_input = sel.locate(page, "file_input").first
    try:
        file_input.wait_for(state="attached", timeout=30000)
    except Exception as exc:
        if texts["login_page"].search(page.title()) or "/login" in page.url:
            raise StudioError("Chrome của tool chưa đăng nhập TikTok. Đăng nhập TikTok trong cửa sổ Chrome đó rồi bấm 'Thử lại'.") from exc
        raise StudioError("Không thấy ô chọn video trên trang tải lên của TikTok Studio.") from exc

    report(0.1, f"Tải {video.name} lên TikTok")
    file_input.set_input_files(str(video))
    save = sel.locate(page, "save_draft_button").first
    deadline = time.time() + cfg.timeout_sec
    while not (save.count() and save.is_enabled() and texts["upload_done"].search(page.inner_text("body"))):
        if time.time() > deadline:
            raise StudioError(f"Quá {cfg.timeout_sec}s video vẫn chưa tải xong lên TikTok.")
        page.wait_for_timeout(2000)
    _dismiss(page, sel)

    report(0.6, "Điền mô tả")
    text = description[:MAX_DESCRIPTION]
    _fill_description(page, sel, text, video, log)

    if cfg.ai_generated_label:
        report(0.7, "Gắn nhãn nội dung do AI tạo")
        _turn_on_ai_label(page, sel, texts["ai_label_row"])

    report(0.85, "Lưu nháp")
    if not _has_description(page, sel, text):
        log("tiktok_draft: mô tả bị mất trước khi lưu, điền lại")
        _fill_description(page, sel, text, video, log)
    if save.get_attribute("data-e2e") != "save_draft_button":
        raise StudioError("Nút lưu nháp không đúng như mong đợi, tool dừng để không bấm nhầm nút đăng.")
    save.click()
    _wait_saved(page, sel, texts["draft_saved"])
    log(f"tiktok_draft: saved draft '{description[:60]}' (AI label: {cfg.ai_generated_label})")


def _wait_until(page, condition: Callable[[], bool], seconds: float) -> bool:
    deadline = time.time() + seconds
    while not condition():
        if time.time() > deadline:
            return False
        page.wait_for_timeout(300)
    return True


def _has_description(page, sel: FlowSelectors, text: str) -> bool:
    return text[:40].strip() in sel.locate(page, "description_editor").first.inner_text()


def _fill_description(page, sel: FlowSelectors, text: str, video: Path, log: Callable[[str], None]) -> None:
    """Once seen: right after "Uploaded", typed text vanished and left the box empty. TikTok pre-fills the
    file name when the editor is ready, so wait for that, then type and check, a few times if needed."""
    editor = sel.locate(page, "description_editor").first
    if not _wait_until(page, lambda: video.stem[:20] in editor.inner_text(), 15):
        log("tiktok_draft: ô mô tả chưa điền sẵn tên file sau 15s, vẫn điền tiếp")
    for attempt in range(1, 4):
        editor.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        page.keyboard.press("Escape")  # closes the hashtag / mention suggestions
        if _wait_until(page, lambda: _has_description(page, sel, text), 5):
            return
        log(f"tiktok_draft: lần {attempt} điền mô tả chưa vào ô (đang là: {editor.inner_text()[:60]!r})")
        page.wait_for_timeout(1500)
    raise StudioError("Không điền được mô tả vào TikTok Studio.")


def _dismiss(page, sel: FlowSelectors) -> None:
    for spec in sel.dismiss_specs():
        button = build_locator(page, spec)
        if button.count() and button.first.is_visible():
            button.first.click(timeout=3000)
            page.wait_for_timeout(500)


def _turn_on_ai_label(page, sel: FlowSelectors, row_text: re.Pattern) -> None:
    def ai_switch():
        row = page.locator("div").filter(has_text=row_text).filter(has=page.locator("input[role=switch]")).last
        return row.locator("input[role=switch]").first

    # The switch is in the DOM even while "Show more" is collapsed, so check visibility, not presence.
    # The input itself is covered by the switch body; its parent is what shows and takes clicks.
    if not ai_switch().locator("xpath=..").is_visible():
        sel.locate(page, "show_more").first.click(timeout=10000)
        page.wait_for_timeout(1000)
    switch = ai_switch()
    if not switch.locator("xpath=..").is_visible():
        raise StudioError("Không thấy công tắc 'AI-generated content'. Tắt tiktok.ai_generated_label nếu muốn lưu nháp không gắn nhãn.")
    if not switch.is_checked():
        switch.locator("xpath=..").click(timeout=10000)
        # The "Labeling AI-generated content" dialog (Not now / Turn on) only shows the first time.
        confirm = sel.locate(page, "ai_label_confirm").first
        deadline = time.time() + 10
        while not switch.is_checked() and time.time() < deadline:
            if confirm.count() and confirm.is_visible():
                confirm.click()
            page.wait_for_timeout(500)
    if not switch.is_checked():
        raise StudioError("Không bật được nhãn 'AI-generated content' trên TikTok Studio.")


def _wait_saved(page, sel: FlowSelectors, saved_text: re.Pattern, timeout: float = 90) -> None:
    """Saved when a confirmation shows, the page leaves the upload form, or the form resets."""
    save_anyway = sel.locate(page, "save_anyway_button").first
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        if save_anyway.count() and save_anyway.is_visible():
            save_anyway.click()  # "Content check lite" takes ~10 min; saving now stops it (not waited for)
            continue
        if "/upload" not in page.url or saved_text.search(page.inner_text("body")):
            return
        if not sel.locate(page, "save_draft_button").count() and sel.locate(page, "file_input").count():
            return
    raise StudioError("Đã bấm 'Save draft' nhưng không thấy TikTok xác nhận đã lưu. Kiểm tra mục Bản nháp trên TikTok Studio.")
