"""TikTok Studio's Content page: the embedded post list (saved HTML, no browser)."""

import html
import json
from datetime import datetime

import pytest

from app.tiktok.studio_content import ContentPageError, find_new_post, item_time, items_from_html, latest_time


def epoch(day, hour, minute=0, month=10):
    return str(int(datetime(2026, month, day, hour, minute).timestamp()))


def page(items) -> str:
    # Shaped like the real page (2026-10-17): HTML-escaped JSON in a script tag.
    payload = json.dumps({"appContext": {"x": 1},
                          "firstBatchQueryItems": {"cursor": 5, "has_more": True, "item_list": items}})
    return ('<html><head><script type="application/json" id="__Creator_Center_Context__">'
            f"{html.escape(payload)}</script></head><body></body></html>")


SCHEDULED = {"desc": "0807 (1)", "create_time": epoch(17, 10, 3), "post_time": epoch(17, 11, 20),
             "schedule_time": epoch(17, 11, 20), "status": 140, "is_pinned": False}
PINNED_OLD = {"desc": "Váy Nữ #vay", "create_time": epoch(9, 6, 10, 8), "post_time": epoch(9, 6, 10, 8),
              "status": 102, "is_pinned": True}
POSTED = {"desc": "Giày Thể Thao Nữ #giaydepnu", "create_time": epoch(17, 9, 5), "post_time": epoch(17, 9, 5),
          "status": 102, "is_pinned": False}


def test_reads_the_embedded_post_list():
    items = items_from_html(page([SCHEDULED, PINNED_OLD, POSTED]))
    assert [i["desc"] for i in items] == ["0807 (1)", "Váy Nữ #vay", "Giày Thể Thao Nữ #giaydepnu"]


def test_latest_time_is_the_max_not_the_first_row():
    # Pinned posts sit above newer ones; scheduled posts sit above everything.
    assert latest_time(items_from_html(page([PINNED_OLD, POSTED]))) == datetime(2026, 10, 17, 9, 5)
    assert latest_time(items_from_html(page([SCHEDULED, PINNED_OLD, POSTED]))) == datetime(2026, 10, 17, 11, 20)
    assert latest_time([]) is None
    assert item_time({"post_time": "0", "create_time": epoch(17, 8)}) == datetime(2026, 10, 17, 8)
    assert item_time({"schedule_time": None, "post_time": epoch(17, 8)}) == datetime(2026, 10, 17, 8)


def test_missing_or_broken_list_is_an_error_not_a_guess():
    with pytest.raises(ContentPageError):
        items_from_html("<html><body>Log in to TikTok</body></html>")
    with pytest.raises(ContentPageError):
        items_from_html('<script type="application/json" id="__Creator_Center_Context__">{not json</script>')
    with pytest.raises(ContentPageError):
        items_from_html('<script type="application/json" id="__Creator_Center_Context__">{"a": 1}</script>')


def test_finds_the_post_just_made_even_when_tiktok_changes_punctuation():
    title = "[JOLY 01] Dép sục+Tặng 1 bộ charm ngẫu nhiên"
    ours = {"desc": "[JOLY 01] Dép sục Tặng 1 bộ charm ngẫu nhiên #giaydepnu ", "create_time": epoch(17, 10, 31),
            "post_time": epoch(18, 19), "schedule_time": epoch(18, 19), "status": 140}
    clicked = datetime(2026, 10, 17, 10, 32)  # created a minute before the recorded click: clock skew is allowed
    assert find_new_post([POSTED, ours], title, clicked, datetime(2026, 10, 18, 19)) is ours
    assert find_new_post([POSTED, ours], title, clicked, datetime(2026, 10, 18, 21)) is None  # another slot
    assert find_new_post([POSTED, ours], title, datetime(2026, 10, 17, 11), None) is None  # older than the click
    now_post = {**ours, "schedule_time": None, "post_time": epoch(17, 10, 31), "status": 102}
    assert find_new_post([now_post], title, clicked, None) is now_post
    assert find_new_post([POSTED], title, clicked, None) is None


def test_empty_title_matches_nothing():
    item = {"desc": "bài bất kỳ", "create_time": str(int(datetime(2026, 10, 18, 10).timestamp()))}
    assert find_new_post([item], "  +!  ", datetime(2026, 10, 18, 9), None) is None


def test_a_post_whose_first_hashtag_landed_before_the_title_is_still_found():
    # The real 2026-10-17 post: the tool must recognise it, or "Thử lại" would post it a second time.
    title = "Giày bốt oxford MIMI kiểu dáng trẻ trung Nữ Shoes Women Loafer"
    mimi = {"desc": "#giayluoinuGiày bốt oxford MIMI kiểu dáng trẻ trung Nữ Shoes Women Loafer #giayluoi #goclamdep",
            "create_time": epoch(17, 12, 34), "post_time": epoch(17, 12, 34), "status": 102}
    assert find_new_post([POSTED, mimi], title, datetime(2026, 10, 17, 12, 34), None) is mimi
