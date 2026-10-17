"""TikTok Studio's Content page: when the latest post goes (or went) out, and whether a new post is there.

Surveyed 2026-10-17: the page embeds its first batch of posts as HTML-escaped JSON in
<script id="__Creator_Center_Context__" type="application/json"> under firstBatchQueryItems.item_list.
Each item has desc, create_time, post_time (epoch seconds; for a scheduled post the time it goes out),
schedule_time (scheduled posts only), status (140 = scheduled, 102 = public) and is_pinned.
Order: scheduled first, then pinned, then the rest newest first, so the latest time is the max, not the first row.
"""

import html as html_lib
import json
import re
from datetime import datetime, timedelta

CONTEXT_SCRIPT = re.compile(r'<script[^>]*id="__Creator_Center_Context__"[^>]*>(.*?)</script>', re.S)
CLOCK_SKEW = timedelta(minutes=2)


class ContentPageError(Exception):
    """The Content page could not be read; message is meant for the user."""


def read_items(page, url: str) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if "/login" in page.url:
        raise ContentPageError("Chrome của tool chưa đăng nhập TikTok. Đăng nhập TikTok trong cửa sổ Chrome đó "
                               "rồi bấm 'Thử lại'.")
    try:
        page.locator("#__Creator_Center_Context__").wait_for(state="attached", timeout=20000)
    except Exception:
        pass  # items_from_html explains what is missing
    return items_from_html(page.content())


def items_from_html(page_html: str) -> list[dict]:
    match = CONTEXT_SCRIPT.search(page_html or "")
    if not match:
        raise ContentPageError("Không thấy danh sách bài trên trang Content của TikTok Studio (TikTok đổi giao diện?).")
    try:
        data = json.loads(html_lib.unescape(match.group(1)))
    except ValueError as exc:
        raise ContentPageError("Danh sách bài trên trang Content của TikTok Studio không đọc được.") from exc
    batch = _find(data, "firstBatchQueryItems")
    if not isinstance(batch, dict) or not isinstance(batch.get("item_list"), list):
        raise ContentPageError("Trang Content của TikTok Studio không có danh sách bài như mong đợi.")
    return batch["item_list"]


def item_time(item: dict) -> datetime | None:
    """When the post goes out (scheduled) or went out, local time."""
    for key in ("schedule_time", "post_time", "create_time"):
        try:
            value = int(item.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return datetime.fromtimestamp(value)
    return None


def latest_time(items: list[dict]) -> datetime | None:
    times = [t for t in map(item_time, items) if t]
    return max(times) if times else None


def find_new_post(items: list[dict], title: str, since: datetime, scheduled_for: datetime | None) -> dict | None:
    """The post the tool just made: its description starts with the product title (punctuation aside: TikTok
    turned "sục+Tặng" into "sục Tặng"), it was created after `since` and, when scheduled, goes out at
    `scheduled_for`."""
    head = _words(title)[:40]
    if not head:
        return None
    for item in items:
        try:
            created = datetime.fromtimestamp(int(item.get("create_time") or 0))
        except (TypeError, ValueError):
            continue
        if created < since - CLOCK_SKEW or not _words(item.get("desc", "")).startswith(head):
            continue
        if scheduled_for and item_time(item) != scheduled_for:
            continue
        return item
    return None


def _words(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", text or "").casefold().split())


def _find(node, key: str):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            found = _find(child, key)
            if found is not None:
                return found
    return None
