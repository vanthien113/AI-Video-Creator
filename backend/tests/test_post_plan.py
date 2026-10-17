"""What gets posted on TikTok and when: product ID, title, the next free schedule slot (pure helpers)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.config import TikTokConfig
from app.job_models import STEPS, JobState, SourceInfo, TikTokPostState
from app.tiktok.post_plan import (MAX_DAYS_AHEAD, job_product_id, next_slot, post_title, product_id_from_url,
                                  slot_label, too_far)

SLOTS = [7, 9, 11, 13, 15, 17, 19, 21, 23]
NOW = datetime(2026, 10, 17, 10, 0)  # Saturday


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute)


def job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t", **kw)


def test_next_slot_examples_from_the_spec():
    assert next_slot(NOW, SLOTS, 20, [at(17, 8, 30)]) == at(17, 11)
    assert next_slot(NOW, SLOTS, 20, [at(17, 10, 50)]) == at(17, 11)
    assert next_slot(NOW, SLOTS, 20, [at(17, 11)]) == at(17, 13)  # strictly after the latest post
    assert next_slot(NOW, SLOTS, 20, [at(17, 21, 30)]) == at(17, 23)
    assert next_slot(NOW, SLOTS, 20, [at(17, 23)]) == at(18, 7)  # no slot left that day
    assert next_slot(NOW, SLOTS, 20, []) == at(17, 11)
    assert next_slot(at(17, 10, 45), SLOTS, 20, []) == at(17, 13)  # 11:00 is closer than 20 minutes


def test_next_slot_takes_the_latest_of_everything_and_skips_missing_values():
    assert next_slot(NOW, SLOTS, 20, [None, at(17, 13), at(17, 17)]) == at(17, 19)
    assert next_slot(at(17, 23, 50), SLOTS, 20, []) == at(18, 7)
    assert next_slot(NOW, [19, 7], 20, [at(17, 20)]) == at(18, 7)  # config order does not matter


def test_next_slot_rolls_over_month_and_year():
    assert next_slot(datetime(2026, 10, 31, 23, 30), SLOTS, 20, []) == datetime(2026, 11, 1, 7)
    assert next_slot(datetime(2026, 12, 31, 22), SLOTS, 20, [datetime(2026, 12, 31, 23)]) == datetime(2027, 1, 1, 7)


def test_too_far_matches_tiktoks_30_day_calendar():
    assert MAX_DAYS_AHEAD == 30
    assert not too_far(datetime(2026, 11, 16, 23), NOW)  # 17/10 + 30 days = 16/11, still offered
    assert too_far(datetime(2026, 11, 17, 7), NOW)


def test_slot_label_is_vietnamese():
    assert slot_label(at(18, 19)) == "19:00 Chủ nhật 18/10"
    assert slot_label(at(17, 7)) == "07:00 thứ Bảy 17/10"
    assert slot_label(at(19, 9)) == "09:00 thứ Hai 19/10"
    assert slot_label(at(18, 19), weekday=False) == "19:00 18/10"


def test_product_id_from_links():
    assert product_id_from_url("https://shop.tiktok.com/vn/pdp/1737477284468917824?_t=ZS-9AcOmdV11T0") \
        == "1737477284468917824"
    assert product_id_from_url("https://shop.tiktok.com/vn/pdp/giay-mary-jane/1737477284468917824") \
        == "1737477284468917824"
    assert product_id_from_url("https://shop.tiktok.com/view/product/1729384756102938475") == "1729384756102938475"
    assert product_id_from_url("https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA") == ""
    assert product_id_from_url("") == ""


def test_job_product_id_prefers_the_saved_id_then_the_link():
    short = SourceInfo(url="https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA", product_id="1737383451447231991")
    assert job_product_id(job(source=short)) == "1737383451447231991"
    pdp = SourceInfo(url="https://shop.tiktok.com/vn/pdp/1735751598590428933?_t=x")
    assert job_product_id(job(source=pdp)) == "1735751598590428933"
    assert job_product_id(job(source=SourceInfo(url="https://vt.tiktok.com/x"))) == ""
    assert job_product_id(job()) == ""


def test_jobs_saved_before_posting_existed_still_load():
    old = {"id": "t", "name": "giay", "input_file": "input.jpg", "created_at": "t",
           "source": {"url": "https://shop.tiktok.com/vn/pdp/1735751598590428933", "title": "Giày"}}
    loaded = JobState.model_validate(old)
    assert loaded.post == TikTokPostState() and loaded.post.mode is None
    assert loaded.source.product_id == "" and job_product_id(loaded) == "1735751598590428933"


def test_post_title_and_step_order():
    assert post_title(job(source=SourceInfo(url="u", title="  Giày Mary Jane  "))) == "Giày Mary Jane"
    assert post_title(job()) == "giay"
    assert STEPS[-2:] == ["tiktok_draft", "tiktok_post"]


def test_tiktok_config_defaults_and_checks():
    cfg = TikTokConfig()
    assert cfg.schedule_slots == SLOTS and cfg.schedule_lead_min == 20
    assert cfg.post_url == "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
    assert cfg.content_url == "https://www.tiktok.com/tiktokstudio/content"
    assert TikTokConfig(schedule_slots=[21, 7, 7]).schedule_slots == [7, 21]
    with pytest.raises(ValidationError):
        TikTokConfig(schedule_slots=[25])
    with pytest.raises(ValidationError):
        TikTokConfig(schedule_lead_min=5)
