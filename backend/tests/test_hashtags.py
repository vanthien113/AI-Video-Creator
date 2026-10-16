"""3 hashtags for the product, from Google's AI Mode (Claude as a fallback), sent after the title on Telegram."""

import pytest

from app.job_models import JobState, SourceInfo, TelegramOrigin
from app.sources import google_hashtags
from app.sources.google_hashtags import parse_hashtags, search_query
from app.steps import hashtags_step, send_telegram_step
from app.steps.hashtags_step import run_hashtags
from app.steps.send_telegram_step import run_send_telegram

from .conftest import make_test_clip
from .test_send_telegram import FakeApi

TITLE = "(DEAL ĐỘC QUYỀN HÀ LINH ) Giày Búp Bê Nơ Mix (Chất liệu PVC) Đế Siêu Nhẹ, Chống Trơn Hot 2026- Topsneaker"

# What AI Mode returned on 2026-10-16: the first line of each top-level list item, then free text.
ITEMS = ["#giaycaogotnu (hoặc #giaycaogot)", "Lý do: Đây là hashtag cốt lõi…", "#xuhuongtiktok (hoặc #xuhuong)",
         "#caogotmuinhon"]


def test_takes_the_lead_hashtag_of_each_list_item():
    assert parse_hashtags(ITEMS, "free text #khac #nua") == ["#giaycaogotnu", "#xuhuongtiktok", "#caogotmuinhon"]


def test_falls_back_to_hashtags_in_the_text_when_there_is_no_list():
    assert parse_hashtags([], "Dùng #giaybupbe, #thoitrangnu và #outfit nhé; #giaybupbe") == [
        "#giaybupbe", "#thoitrangnu", "#outfit"]
    assert parse_hashtags([], "không có gì") == []


def test_query_drops_shop_promo_brackets_and_keeps_it_short():
    query = search_query(TITLE)
    assert "DEAL" not in query and "Giày Búp Bê Nơ Mix" in query and "Việt Nam" in query
    assert len(query) < 160


@pytest.fixture
def job_ctx(make_context):
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title=TITLE))
    return make_context(job=job)


def test_step_saves_google_hashtags(job_ctx, monkeypatch):
    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title: ["#a", "#b", "#c"])
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: pytest.fail("Google worked"))
    run_hashtags(job_ctx)
    assert job_ctx.job.hashtags == ["#a", "#b", "#c"] and job_ctx.job.hashtags_source == "google"


def test_step_falls_back_to_claude_then_to_nothing_without_failing(job_ctx, monkeypatch):
    def broken(ctx, title):
        raise RuntimeError("captcha")

    monkeypatch.setattr(hashtags_step, "from_google", broken)
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: ["#x", "#y", "#z"])
    run_hashtags(job_ctx)
    assert job_ctx.job.hashtags == ["#x", "#y", "#z"] and job_ctx.job.hashtags_source == "claude"

    monkeypatch.setattr(hashtags_step, "from_claude", broken)
    run_hashtags(job_ctx)  # must not raise: hashtags are a nice-to-have
    assert job_ctx.job.hashtags == []


def test_no_title_no_search(make_context, monkeypatch):
    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title: pytest.fail("nothing to search for"))
    run_hashtags(make_context())


def test_title_message_carries_the_hashtags(make_context, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:T")
    api = FakeApi()
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: api)
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title="Giày"),
                   telegram=TelegramOrigin(chat_id=1, message_id=2, preview_sent=True, file_sent=True),
                   hashtags=["#giaycaogot", "#thoitrangnu", "#xuhuong"])
    ctx = make_context(job=job)
    make_test_clip(ctx.path("final-4k60.mp4"), width=360, height=640, seconds=1)
    run_send_telegram(ctx)
    assert api.calls[-1][1]["text"] == "Giày\n#giaycaogot #thoitrangnu #xuhuong"


def test_google_module_has_no_side_effects_on_import():
    assert google_hashtags.AI_MODE_URL.startswith("https://www.google.com/search")
