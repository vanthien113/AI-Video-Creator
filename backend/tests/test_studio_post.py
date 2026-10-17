"""Pure parts of the TikTok Studio post form, and the selectors file it relies on (no browser)."""

import re

from app.tiktok.studio_post import button_label, clean_product_name, invalid_chars, pick_suggestion
from app.tiktok.studio_upload import load_selectors

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
                "calendar_day", "hashtag_topics", "hashtag_selected", "hashtag_done"]:
        assert sel.spec(key)
    assert {"login_page", "upload_done", "ai_label_row", "draft_saved", "invalid_chars"} <= set(texts)
    assert sel.data["confirm_post_buttons"]
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
