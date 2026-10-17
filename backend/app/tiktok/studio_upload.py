"""Shared steps of TikTok Studio's upload form, and Save draft on top of them.

Observed 2026-10-15: the upload page has a hidden <input type=file accept=video/*>; once a file is
chosen the form appears with a DraftJS description editor (pre-filled with the file name), a
"Show more" section holding the "AI-generated content" switch (turning it on opens a dialog:
"Not now" / "Turn on"), and the buttons Post / Save draft / Discard (data-e2e attributes).
Observed 2026-10-17: the upload is done when [data-e2e=upload_status_container] says "Uploaded（30.44MB）".
The page body cannot tell: it always says "Checks can only start after the file is uploaded."
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


def load_selectors(selectors: FlowSelectors | None = None) -> tuple[FlowSelectors, dict[str, re.Pattern]]:
    sel = selectors or FlowSelectors.load(SELECTORS_FILE)
    return sel, {k: re.compile(v, re.I) for k, v in sel.data.get("texts", {}).items()}


def save_draft(page, cfg: TikTokConfig, video: Path, description: str,
               report: Callable[[float, str], None], log: Callable[[str], None],
               selectors: FlowSelectors | None = None) -> None:
    sel, texts = load_selectors(selectors)

    report(0.05, "Mở TikTok Studio")
    open_upload_form(page, sel, texts, cfg.upload_url)
    report(0.1, f"Tải {video.name} lên TikTok")
    upload_video(page, sel, texts, video, cfg.timeout_sec)
    save = sel.locate(page, "save_draft_button").first
    if not wait_until(page, lambda: save.count() and save.is_enabled(), 30):
        raise StudioError("Nút lưu nháp vẫn bị khoá sau khi tải video xong.")

    report(0.6, "Điền mô tả")
    text = description[:MAX_DESCRIPTION]
    fill_description(page, sel, text, video, log)

    if cfg.ai_generated_label:
        report(0.7, "Gắn nhãn nội dung do AI tạo")
        turn_on_ai_label(page, sel, texts["ai_label_row"])

    report(0.85, "Lưu nháp")
    if not has_description(page, sel, text):
        log("tiktok_draft: mô tả bị mất trước khi lưu, điền lại")
        fill_description(page, sel, text, video, log)
    if save.get_attribute("data-e2e") != "save_draft_button":
        raise StudioError("Nút lưu nháp không đúng như mong đợi, tool dừng để không bấm nhầm nút đăng.")
    save.click()
    _wait_saved(page, sel, texts["draft_saved"])
    log(f"tiktok_draft: saved draft '{description[:60]}' (AI label: {cfg.ai_generated_label})")


# ---- shared with the post step (studio_post) -------------------------------------------

def open_upload_form(page, sel: FlowSelectors, texts: dict[str, re.Pattern], url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        sel.locate(page, "file_input").first.wait_for(state="attached", timeout=30000)
    except Exception as exc:
        if texts["login_page"].search(page.title()) or "/login" in page.url:
            raise StudioError("Chrome của tool chưa đăng nhập TikTok. Đăng nhập TikTok trong cửa sổ Chrome đó rồi bấm 'Thử lại'.") from exc
        raise StudioError("Không thấy ô chọn video trên trang tải lên của TikTok Studio.") from exc


def upload_video(page, sel: FlowSelectors, texts: dict[str, re.Pattern], video: Path, timeout_sec: int) -> None:
    sel.locate(page, "file_input").first.set_input_files(str(video))
    status = sel.locate(page, "upload_status").first
    deadline = time.time() + timeout_sec
    while not (status.count() and texts["upload_done"].search(status.inner_text())):
        if time.time() > deadline:
            raise StudioError(f"Quá {timeout_sec}s video vẫn chưa tải xong lên TikTok.")
        page.wait_for_timeout(2000)
    dismiss(page, sel)


def wait_until(page, condition: Callable[[], bool], seconds: float) -> bool:
    deadline = time.time() + seconds
    while not condition():
        if time.time() > deadline:
            return False
        page.wait_for_timeout(300)
    return True


def has_description(page, sel: FlowSelectors, text: str) -> bool:
    return text[:40].strip() in sel.locate(page, "description_editor").first.inner_text()


def fill_description(page, sel: FlowSelectors, text: str, video: Path, log: Callable[[str], None]) -> None:
    """Once seen: right after "Uploaded", typed text vanished and left the box empty. TikTok pre-fills the
    file name when the editor is ready, so wait for that, then type and check, a few times if needed."""
    editor = sel.locate(page, "description_editor").first
    if not wait_until(page, lambda: video.stem[:20] in editor.inner_text(), 15):
        log("tiktok: ô mô tả chưa điền sẵn tên file sau 15s, vẫn điền tiếp")
    for attempt in range(1, 4):
        editor.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        page.keyboard.press("Escape")  # closes the hashtag / mention suggestions
        if wait_until(page, lambda: has_description(page, sel, text), 5):
            return
        log(f"tiktok: lần {attempt} điền mô tả chưa vào ô (đang là: {editor.inner_text()[:60]!r})")
        page.wait_for_timeout(1500)
    raise StudioError("Không điền được mô tả vào TikTok Studio.")


def dismiss(page, sel: FlowSelectors) -> None:
    for spec in sel.dismiss_specs():
        button = build_locator(page, spec)
        if button.count() and button.first.is_visible():
            button.first.click(timeout=3000)
            page.wait_for_timeout(500)


def _ai_switch(page, row_text: re.Pattern):
    row = page.locator("div").filter(has_text=row_text).filter(has=page.locator("input[role=switch]")).last
    return row.locator("input[role=switch]").first


def ai_label_on(page, row_text: re.Pattern) -> bool:
    return _ai_switch(page, row_text).is_checked()


def turn_on_ai_label(page, sel: FlowSelectors, row_text: re.Pattern) -> None:
    # The switch is in the DOM even while "Show more" is collapsed, so check visibility, not presence.
    # The input itself is covered by the switch body; its parent is what shows and takes clicks.
    if not _ai_switch(page, row_text).locator("xpath=..").is_visible():
        sel.locate(page, "show_more").first.click(timeout=10000)
        page.wait_for_timeout(1000)
    switch = _ai_switch(page, row_text)
    if not switch.locator("xpath=..").is_visible():
        raise StudioError("Không thấy công tắc 'AI-generated content'. Tắt tiktok.ai_generated_label nếu muốn đăng không gắn nhãn.")
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
