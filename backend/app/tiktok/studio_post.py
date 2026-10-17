"""Post now or schedule in TikTok Studio: the upload form (shared steps in studio_upload), hashtags, Add link,
the AI label, When to post, a last check, and the one click on Post / Schedule.

Surveyed 2026-10-17 (English UI, nothing posted); selectors live in tiktok-selectors.yaml:
- Hashtags only become real tags when picked from the suggestions: typing "#tag" lists [role=option] items
  (.hash-tag-topic), the first one selected; Enter turns the text into span[data-testid=mentionText] and adds
  a space. Clicking a suggestion fails in a background tab (the list is outside the viewport).
- Add link: anchor_container's "Add" → "Add link" (Link type: Products) → Next → "Add product links": the search
  leaves only rows whose 2nd cell (Product ID) is the ID, or none when the product is not in the account's
  showcase (no message, an empty table). Radio → Next → "Product name" (pre-filled, 30 chars; TikTok may answer
  "Remove invalid characters: +") → Add; both dialogs close and the name shows in anchor_container.
- When to post: radios post_now / schedule. Schedule shows a read-only time input "HH:MM" (an hour column
  00–23 then a minute column 00–55 by 5) and a date input "YYYY-MM-DD" (calendar, today + 30 days). The post
  button keeps data-e2e=post_video_button and reads "Schedule".
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import TikTokConfig
from ..flow.flow_selectors import FlowSelectors, build_locator
from .post_plan import slot_label
from .studio_upload import (MAX_DESCRIPTION, StudioError, ai_label_on, fill_description, has_description,
                            load_selectors, open_upload_form, turn_on_ai_label, upload_video, wait_until)

DATE_VALUE, TIME_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$"), re.compile(r"^\d{2}:\d{2}$")
PRODUCT_NAME_MAX = 30


class ProductNotFound(StudioError):
    pass


@dataclass
class PostPlan:
    video: Path
    title: str
    hashtags: list[str]
    product_id: str
    schedule_at: datetime | None = None  # None = post now


# ---- pure parts ---------------------------------------------------------------------

def invalid_chars(message: str, pattern: re.Pattern) -> list[str]:
    """Characters TikTok refuses in the product name, from e.g. "Remove invalid characters: +"."""
    match = pattern.search(message or "")
    if not match:
        return []
    return list(dict.fromkeys(c for c in match.group(1) if not c.isspace()))


def clean_product_name(name: str, bad: list[str]) -> str:
    for char in bad:
        name = name.replace(char, " ")
    return " ".join(name.split())[:PRODUCT_NAME_MAX].strip() or "Sản phẩm"


def button_label(sel: FlowSelectors, schedule: bool) -> str:
    return sel.data["post_button_text"]["schedule" if schedule else "now"]


def pick_suggestion(page, sel: FlowSelectors, tag: str, wait_sec: float = 6.0) -> bool:
    """Move the selection onto the exact tag with the arrow keys and press Enter. False (nothing pressed but
    arrows) when TikTok does not suggest that tag: Enter would then pick a different one."""
    want = tag.casefold()
    topics = sel.locate(page, "hashtag_topics")
    selected = sel.locate(page, "hashtag_selected")

    def shown() -> list[str]:
        return [t.strip().casefold() for t in topics.all_inner_texts()]

    if not wait_until(page, lambda: want in shown(), wait_sec):
        return False
    for _ in range(shown().index(want)):
        page.keyboard.press("ArrowDown")
    if not wait_until(page, lambda: selected.count() and selected.first.inner_text().strip().casefold() == want, 2):
        return False
    page.keyboard.press("Enter")
    return True


# ---- the form -------------------------------------------------------------------------

def post_video(page, cfg: TikTokConfig, plan: PostPlan, report: Callable[[float, str], None],
               log: Callable[[str], None], before_click: Callable[[], None], dry_run: bool = False,
               selectors: FlowSelectors | None = None) -> None:
    sel, texts = load_selectors(selectors)
    schedule = plan.schedule_at is not None
    label = button_label(sel, schedule)

    report(0.15, "Mở trang tải lên TikTok Studio")
    open_upload_form(page, sel, texts, cfg.post_url)
    report(0.2, f"Tải {plan.video.name} lên TikTok")
    upload_video(page, sel, texts, plan.video, cfg.timeout_sec)

    report(0.5, "Điền mô tả và hashtag")
    title = plan.title[:MAX_DESCRIPTION]
    fill_description(page, sel, title, plan.video, log)
    picked = add_hashtags(page, sel, plan.hashtags, log)

    report(0.6, f"Gắn link sản phẩm {plan.product_id}")
    product_name = add_product_link(page, sel, texts, plan.product_id, log)

    if cfg.ai_generated_label:
        report(0.7, "Bật nhãn nội dung do AI tạo")
        turn_on_ai_label(page, sel, texts["ai_label_row"])

    if schedule:
        report(0.8, f"Chọn lịch {slot_label(plan.schedule_at, weekday=False)}")
        choose_schedule(page, sel, plan.schedule_at)
    else:
        choose_when(page, sel, "post_now")

    button = check_ready(page, sel, texts, cfg, plan, product_name, label)
    log(f"tiktok_post: sẵn sàng bấm {label}: '{title[:40]}', {picked}/{len(plan.hashtags)} hashtag thật, "
        f"link '{product_name}'")
    if dry_run:
        report(1, f"Chạy thử xong, dừng trước khi bấm {label}")
        return
    before_click()
    report(0.9, f"Bấm {label}")
    button.click()
    wait_submitted(page, sel, log, schedule)


def add_hashtags(page, sel: FlowSelectors, tags: list[str], log: Callable[[str], None]) -> int:
    """On a new line after the title, type each tag and pick it from TikTok's suggestions so it becomes a real
    hashtag; a tag TikTok does not suggest stays as text. Returns how many became real hashtags."""
    editor = sel.locate(page, "description_editor").first
    picked = 0
    for i, tag in enumerate(tags):
        editor.click()
        page.keyboard.press("Meta+ArrowDown")  # caret to the end of the text
        if i == 0:
            page.keyboard.insert_text("\n")
        page.keyboard.type(tag, delay=60)
        if pick_suggestion(page, sel, tag):
            picked += 1  # TikTok adds the space after a picked tag
        else:
            log(f"tiktok_post: TikTok không gợi ý {tag}, để dạng chữ")
            page.keyboard.press("Escape")
            page.keyboard.type(" ")
    log(f"tiktok_post: {sel.locate(page, 'hashtag_done').count()} hashtag thật trong mô tả")
    return picked


def add_product_link(page, sel: FlowSelectors, texts: dict[str, re.Pattern], product_id: str,
                     log: Callable[[str], None]) -> str:
    """Returns the product name shown on the form."""
    sel.locate(page, "add_link_button").first.click(timeout=10000)
    link_dialog = sel.locate(page, "link_dialog").first
    link_dialog.wait_for(state="visible", timeout=10000)
    sel.locate(link_dialog, "dialog_next").first.click(timeout=10000)  # Link type is "Products" by default

    products = sel.locate(page, "product_dialog").last
    search = sel.locate(products, "product_search").first
    search.wait_for(state="visible", timeout=15000)
    search.fill(product_id)
    search.press("Enter")
    exact_id = re.compile(rf"^\s*{re.escape(product_id)}\s*$")
    row = sel.locate(products, "product_rows").filter(has=sel.locate(page, "product_id_cell").filter(has_text=exact_id))
    if not wait_until(page, lambda: row.count() > 0, 15):
        close_dialogs(page, sel)
        raise ProductNotFound(f"Không tìm thấy sản phẩm {product_id} khi Add link. Kiểm tra sản phẩm đã có trong "
                              "showcase/shop của tài khoản TikTok này rồi bấm Thử lại.")
    sel.locate(row.first, "product_radio").first.check(force=True)
    sel.locate(products, "dialog_next").first.click(timeout=10000)

    name_box = sel.locate(products, "product_name_input").first
    name_box.wait_for(state="visible", timeout=10000)
    for _ in range(3):
        added = name_box.input_value()
        sel.locate(products, "dialog_add").first.click(timeout=10000)
        if wait_until(page, lambda: sel.locate(page, "product_dialog").count() == 0, 5):
            break
        message = products.inner_text()
        bad = invalid_chars(message, texts["invalid_chars"])
        if not bad:
            raise StudioError(f"TikTok không nhận link sản phẩm: {' '.join(message.split())[:200]}")
        cleaned = clean_product_name(name_box.input_value(), bad)
        log(f"tiktok_post: bỏ ký tự {' '.join(bad)} khỏi tên sản phẩm → {cleaned!r}")
        name_box.fill(cleaned)
    else:
        raise StudioError("Không gắn được link sản phẩm: TikTok vẫn từ chối tên sản phẩm.")

    if added not in sel.locate(page, "anchor_container").first.inner_text():
        raise StudioError("Đã bấm Add nhưng form chưa hiện link sản phẩm.")
    return added


def close_dialogs(page, sel: FlowSelectors) -> None:
    for _ in range(3):
        dialogs = sel.locate(page, "any_dialog")
        if not dialogs.count():
            return
        cancel = sel.locate(dialogs.last, "dialog_cancel")
        if not cancel.count():
            return
        cancel.first.click(timeout=5000)
        page.wait_for_timeout(500)


def choose_when(page, sel: FlowSelectors, value: str) -> None:
    sel.locate(page, "when_option", value).first.click(timeout=10000)
    if not wait_until(page, lambda: sel.locate(page, "when_input", value).first.get_attribute("aria-checked") == "true", 5):
        raise StudioError(f"Không chọn được '{value}' ở mục When to post.")


def choose_schedule(page, sel: FlowSelectors, when: datetime) -> None:
    """Date first (a time can depend on the day), then hour and minute; then read both inputs back."""
    choose_when(page, sel, "schedule")
    box = sel.locate(page, "schedule_container").first
    if not wait_until(page, lambda: _picker(sel, box, DATE_VALUE) is not None and _picker(sel, box, TIME_VALUE) is not None, 10):
        raise StudioError("Không thấy ô chọn ngày giờ sau khi chọn Schedule.")
    _pick_date(page, sel, box, when)
    _pick_time(page, sel, box, when)
    shown = (_picker(sel, box, DATE_VALUE).input_value(), _picker(sel, box, TIME_VALUE).input_value())
    if shown != (f"{when:%Y-%m-%d}", f"{when:%H:%M}"):
        raise StudioError(f"TikTok đang hiện lịch {shown[1]} {shown[0]}, không phải {when:%H:%M %Y-%m-%d}; "
                          "tool dừng trước khi bấm Schedule.")


def _picker(sel: FlowSelectors, box, pattern: re.Pattern):
    fields = sel.locate(box, "schedule_inputs")
    for i in range(fields.count()):
        if pattern.match(fields.nth(i).input_value() or ""):
            return fields.nth(i)
    return None


def _pick_date(page, sel: FlowSelectors, box, when: datetime) -> None:
    _picker(sel, box, DATE_VALUE).click()
    calendar = sel.locate(box, "calendar").first
    calendar.wait_for(state="visible", timeout=5000)
    target = when.year * 12 + when.month - 1
    for _ in range(3):
        title = sel.locate(calendar, "calendar_month").first.inner_text().strip()
        months = sel.data["calendar_months"]
        if title not in months:
            raise StudioError(f"Lịch của TikTok hiện tháng '{title}', tool không đọc được.")
        month = months.index(title)
        shown = int(sel.locate(calendar, "calendar_year").first.inner_text().strip()) * 12 + month
        if shown == target:
            break
        arrows = sel.locate(calendar, "calendar_arrow")
        (arrows.last if shown < target else arrows.first).click()
        page.wait_for_timeout(400)
    day = sel.locate(calendar, "calendar_day").filter(has_text=re.compile(rf"^\s*{when.day}\s*$"))
    if day.count() != 1:
        raise StudioError(f"Lịch của TikTok không cho chọn ngày {when:%d/%m/%Y}.")
    day.first.click()
    if not wait_until(page, lambda: not calendar.is_visible(), 3):
        page.keyboard.press("Escape")


def _pick_time(page, sel: FlowSelectors, box, when: datetime) -> None:
    """The hour column comes first in the DOM and the minute column last, so "15" (both) is told apart by order."""
    _picker(sel, box, TIME_VALUE).click()
    page.wait_for_timeout(500)
    visible = sel.locate(box, "time_options").filter(visible=True)
    visible.filter(has_text=re.compile(rf"^{when.hour:02d}$")).first.click()
    page.wait_for_timeout(400)
    visible.filter(has_text=re.compile(rf"^{when.minute:02d}$")).last.click()
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")


def check_ready(page, sel: FlowSelectors, texts: dict[str, re.Pattern], cfg: TikTokConfig, plan: PostPlan,
                product_name: str, label: str):
    """Last look before the click; returns the button to press."""
    if not has_description(page, sel, plan.title[:MAX_DESCRIPTION]):
        raise StudioError("Mô tả trên TikTok Studio bị mất trước khi đăng; tool dừng, không bấm.")
    if product_name not in sel.locate(page, "anchor_container").first.inner_text():
        raise StudioError("Link sản phẩm không còn trên form; tool dừng, không bấm.")
    if cfg.ai_generated_label and not ai_label_on(page, texts["ai_label_row"]):
        raise StudioError("Nhãn 'AI-generated content' chưa bật; tool dừng, không bấm.")
    value = "schedule" if plan.schedule_at else "post_now"
    if sel.locate(page, "when_input", value).first.get_attribute("aria-checked") != "true":
        raise StudioError("Mục When to post không đúng lựa chọn; tool dừng, không bấm.")
    button = sel.locate(page, "post_button").first
    if button.get_attribute("data-e2e") != "post_video_button" or button.inner_text().strip() != label:
        raise StudioError(f"Nút {label} không đúng như mong đợi; tool dừng, không bấm.")
    if not wait_until(page, lambda: button.is_enabled() and button.get_attribute("data-disabled") != "true", 30):
        raise StudioError(f"Nút {label} đang bị khoá; tool dừng, không bấm.")
    return button


def wait_submitted(page, sel: FlowSelectors, log: Callable[[str], None], schedule: bool,
                   timeout: float = 90) -> None:
    """After the click: leave at once when the form is gone; otherwise answer a confirm dialog of this mode.
    Not seeing the form leave is not an error here; the Content page check that follows decides."""
    mode = "schedule" if schedule else "now"
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(1500)
        if "/upload" not in page.url:
            return
        dialogs = sel.locate(page, "any_dialog")
        for spec in sel.data.get("confirm_post_buttons", {}).get(mode, []):
            button = build_locator(dialogs, spec)
            if button.count() and button.first.is_visible():
                log(f"tiktok_post: TikTok hỏi lại, bấm '{spec.get('name')}'")
                button.first.click(timeout=5000)
                break
    log("tiktok_post: sau khi bấm, trang tải lên vẫn còn; kiểm tra trên trang Content")
