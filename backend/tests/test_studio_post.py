"""Pure parts of the TikTok Studio post form, and the selectors file it relies on (no browser)."""

import re
from datetime import datetime
from pathlib import Path

import pytest

from app.config import TikTokConfig
from app.tiktok import studio_post
from app.tiktok.studio_post import (PostPlan, button_label, clean_product_name, invalid_chars, pick_suggestion,
                                    post_video, wait_submitted)
from app.tiktok.studio_upload import StudioError, load_selectors

INVALID = re.compile(r"invalid characters?:\s*(.+)", re.I)


def test_invalid_characters_are_read_from_tiktoks_message():
    assert invalid_chars("Product name\nRemove invalid characters: +\n30/30", INVALID) == ["+"]
    assert invalid_chars("Remove invalid characters: + & +", INVALID) == ["+", "&"]
    assert invalid_chars("Product name\n30/30", INVALID) == []


def test_product_name_is_cleaned_and_kept_short():
    assert clean_product_name("[JOLY 01] Dép sục+Tặng 1 bộ ch", ["+"]) == "[JOLY 01] Dép sục Tặng 1 bộ ch"
    assert len(clean_product_name("a&" * 40, ["&"])) <= 30
    assert clean_product_name("+++", ["+"]) == "Sản phẩm"


def test_selectors_file_has_every_key_the_post_uses():
    sel, texts = load_selectors()
    for key in ["file_input", "upload_status", "description_editor", "show_more", "ai_label_confirm",
                "save_draft_button", "post_button", "add_link_button", "anchor_container", "link_dialog",
                "product_dialog", "product_search", "product_rows", "product_id_cell", "product_radio",
                "product_name_input", "dialog_next", "dialog_add", "dialog_cancel", "schedule_container",
                "when_option", "when_input", "calendar", "calendar_month", "calendar_year", "calendar_arrow",
                "calendar_day", "hashtag_topics", "hashtag_selected", "hashtag_done", "any_dialog", "schedule_inputs",
                "time_options"]:
        assert sel.spec(key)
    assert {"login_page", "upload_done", "ai_label_row", "draft_saved", "invalid_chars"} <= set(texts)
    assert len(sel.data["calendar_months"]) == 12
    confirm = sel.data["confirm_post_buttons"]
    assert confirm["now"] and confirm["schedule"]
    assert not [b for b in confirm["schedule"] if b["name"].startswith("Post")]
    assert texts["upload_done"].search("Uploaded（30.44MB）")
    assert button_label(sel, schedule=False) == "Post" and button_label(sel, schedule=True) == "Schedule"


# ---- picking a hashtag from TikTok's suggestion list (fake list + keyboard) ----------

class Listing:
    def __init__(self, topics):
        self.topics, self.selected = topics, 0


class FakeKeys:
    def __init__(self, listing):
        self.listing, self.pressed = listing, []

    def press(self, key):
        self.pressed.append(key)
        if key == "ArrowDown":
            self.listing.selected = min(self.listing.selected + 1, len(self.listing.topics) - 1)


class FakeLocator:
    def __init__(self, texts):
        self.texts = texts

    def all_inner_texts(self):
        return self.texts()

    def count(self):
        return len(self.texts())

    @property
    def first(self):
        return self

    def inner_text(self):
        return self.texts()[0]


class FakeSel:
    def __init__(self, listing):
        self.listing = listing

    def locate(self, scope, key, value=None):
        if key == "hashtag_topics":
            return FakeLocator(lambda: list(self.listing.topics))
        if key == "hashtag_selected":
            return FakeLocator(lambda: [self.listing.topics[self.listing.selected]] if self.listing.topics else [])
        raise KeyError(key)


class FakePage:
    def __init__(self, listing):
        self.keyboard = FakeKeys(listing)

    def wait_for_timeout(self, ms):
        pass


def test_hashtag_is_picked_from_the_suggestions_with_the_arrow_keys():
    listing = Listing(["#giaybupbe", "#giaybupbenu", "#giaybupbebegai"])
    page = FakePage(listing)
    assert pick_suggestion(page, FakeSel(listing), "#giaybupbenu", wait_sec=0.05)
    assert page.keyboard.pressed == ["ArrowDown", "Enter"]


def test_first_suggestion_needs_no_arrow_and_case_does_not_matter():
    listing = Listing(["#GiayBupBe", "#giaybupbenu"])
    page = FakePage(listing)
    assert pick_suggestion(page, FakeSel(listing), "#giaybupbe", wait_sec=0.05)
    assert page.keyboard.pressed == ["Enter"]


def test_missing_hashtag_stays_text_and_enter_is_never_pressed():
    listing = Listing(["#giaybupbenu"])  # Enter here would turn "#giaybupbe" into another tag
    page = FakePage(listing)
    assert not pick_suggestion(page, FakeSel(listing), "#giaybupbe", wait_sec=0.05)
    assert "Enter" not in page.keyboard.pressed
    empty = Listing([])
    page = FakePage(empty)
    assert not pick_suggestion(page, FakeSel(empty), "#giaybupbe", wait_sec=0.05)
    assert page.keyboard.pressed == []


# ---- confirm dialogs after Post / Schedule (fake page, no browser) -------------------------

UPLOAD = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
CONTENT = "https://www.tiktok.com/tiktokstudio/content"


class Btn:
    def __init__(self, name, in_dialog, visible=True):
        self.name, self.in_dialog, self.visible = name, in_dialog, visible


class Matches:
    def __init__(self, page, buttons):
        self.page, self.buttons = page, buttons

    def count(self):
        return len(self.buttons)

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.buttons[0].visible

    def click(self, timeout=None):
        button = self.buttons[0]
        self.page.clicked.append((button.name, button.in_dialog))
        self.page.url = CONTENT  # a confirmed post leaves the upload form


class Scope:
    """The page, or only its dialogs; get_by_role finds buttons by name inside it."""

    def __init__(self, page, dialogs_only):
        self.page, self.dialogs_only = page, dialogs_only

    def get_by_role(self, role, name=None, exact=False):
        if role == "dialog":
            return Scope(self.page, dialogs_only=True)
        found = [b for b in self.page.buttons if b.name == name and (b.in_dialog or not self.dialogs_only)]
        return Matches(self.page, found)


class SubmitPage:
    def __init__(self, url, buttons):
        self.url, self.buttons, self.clicked = url, buttons, []

    def get_by_role(self, role, name=None, exact=False):
        return Scope(self, dialogs_only=False).get_by_role(role, name=name, exact=exact)

    def wait_for_timeout(self, ms):
        pass


def test_wait_submitted_returns_at_once_once_the_form_is_gone():
    page = SubmitPage(CONTENT, [Btn("Post now", in_dialog=True)])
    wait_submitted(page, load_selectors()[0], [].append, schedule=False, timeout=0.05)
    assert page.clicked == []


def test_schedule_mode_never_presses_post_now_even_in_a_dialog():
    page = SubmitPage(UPLOAD, [Btn("Post now", in_dialog=True)])
    wait_submitted(page, load_selectors()[0], [].append, schedule=True, timeout=0.05)
    assert page.clicked == []


def test_schedule_mode_presses_schedule_anyway_in_a_dialog():
    page = SubmitPage(UPLOAD, [Btn("Post now", in_dialog=True), Btn("Schedule anyway", in_dialog=True)])
    wait_submitted(page, load_selectors()[0], [].append, schedule=True)
    assert page.clicked == [("Schedule anyway", True)]


def test_now_mode_presses_post_now_only_inside_a_dialog():
    page = SubmitPage(UPLOAD, [Btn("Post now", in_dialog=False), Btn("Post now", in_dialog=True)])
    wait_submitted(page, load_selectors()[0], [].append, schedule=False)
    assert page.clicked == [("Post now", True)]


# ---- click order of post_video (helpers replaced by recorders) ----------------------------

class ReadyButton:
    def __init__(self, events):
        self.events = events

    def click(self):
        self.events.append("click")


def _run_post(monkeypatch, events, dry_run=False, schedule_at=None, check_error=None):
    calls = {}

    def record(name, result=None):
        def fn(*args, **kwargs):
            events.append(name)
            calls[name] = args
            return result
        return fn

    def check_ready(*args, **kwargs):
        events.append("check_ready")
        if check_error:
            raise check_error
        return ReadyButton(events)

    for name, fake in {
        "open_upload_form": record("open_upload_form"),
        "upload_video": record("upload_video"),
        "fill_description": record("fill_description"),
        "add_hashtags": record("add_hashtags", 0),
        "add_product_link": record("add_product_link", "Dép"),
        "turn_on_ai_label": record("turn_on_ai_label"),
        "choose_when": record("choose_when"),
        "choose_schedule": record("choose_schedule"),
        "check_ready": check_ready,
        "wait_submitted": record("wait_submitted"),
    }.items():
        monkeypatch.setattr(studio_post, name, fake)

    plan = PostPlan(video=Path("clip.mp4"), title="Giày mới", hashtags=[], product_id="123",
                    schedule_at=schedule_at)
    post_video(None, TikTokConfig(), plan, lambda *a: None, lambda msg: None,
               lambda: events.append("before_click"), dry_run=dry_run)
    return calls


def test_dry_run_never_clicks_post(monkeypatch):
    events = []
    _run_post(monkeypatch, events, dry_run=True)
    assert events[-1] == "check_ready"
    assert "before_click" not in events and "click" not in events and "wait_submitted" not in events


def test_post_now_runs_before_click_then_click_then_wait(monkeypatch):
    events = []
    calls = _run_post(monkeypatch, events)
    assert events == ["open_upload_form", "upload_video", "fill_description", "add_hashtags",
                      "add_product_link", "turn_on_ai_label", "choose_when", "check_ready",
                      "before_click", "click", "wait_submitted"]
    assert calls["wait_submitted"][3] is False


def test_schedule_run_passes_schedule_mode_to_the_wait(monkeypatch):
    events = []
    calls = _run_post(monkeypatch, events, schedule_at=datetime(2026, 10, 18, 15, 0))
    assert "choose_schedule" in events and "choose_when" not in events
    assert events[-3:] == ["before_click", "click", "wait_submitted"]
    assert calls["wait_submitted"][3] is True


def test_failed_check_never_clicks(monkeypatch):
    events = []
    with pytest.raises(StudioError):
        _run_post(monkeypatch, events, check_error=StudioError("không đúng"))
    assert "before_click" not in events and "click" not in events
