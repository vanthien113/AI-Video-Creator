"""3 hashtags for the product: 10 candidates from Google's AI Mode (Claude as fallback), each checked on TikTok,
the first 3 that really exist and are used are sent after the title on Telegram."""

import pytest

from app.job_models import JobState, SourceInfo, TelegramOrigin
from app.sources import google_hashtags
from app.sources.google_hashtags import parse_hashtags, search_query
from app.sources.tiktok_hashtags import pick_real
from app.steps import hashtags_step, send_telegram_step
from app.steps.hashtags_step import run_hashtags
from app.steps.send_telegram_step import run_send_telegram

from .conftest import make_test_clip
from .test_send_telegram import FakeApi

TITLE = "(DEAL ĐỘC QUYỀN HÀ LINH ) Giày Búp Bê Nơ Mix (Chất liệu PVC) Đế Siêu Nhẹ, Chống Trơn Hot 2026- Topsneaker"

# What AI Mode returned on 2026-10-16: the first line of each top-level list item, then free text.
ITEMS = ["#giaycaogotnu (hoặc #giaycaogot)", "Lý do: Đây là hashtag cốt lõi…", "#xuhuongtiktok (hoặc #xuhuong)",
         "#caogotmuinhon"]

# TikTok's answers measured on 2026-10-16 (videos): real and big, real but unused, made up.
TIKTOK = {"#giaycaogot": 1_231_010, "#sandalnu2026": 10, "#depsandallonumuikin": None}


def test_takes_the_lead_hashtag_of_each_list_item():
    assert parse_hashtags(ITEMS, "free text #khac #nua", count=3) == ["#giaycaogotnu", "#xuhuongtiktok", "#caogotmuinhon"]


def test_falls_back_to_hashtags_in_the_text_when_there_is_no_list():
    assert parse_hashtags([], "Dùng #giaybupbe, #thoitrangnu và #outfit nhé; #giaybupbe") == [
        "#giaybupbe", "#thoitrangnu", "#outfit"]
    assert parse_hashtags([], "không có gì") == []


def test_query_asks_for_10_by_product_type_not_the_whole_shop_title():
    # The full title made Google glue its words into tags nobody uses (#depsandallonumuikin).
    query = search_query(TITLE)
    assert query.startswith("10 hashtag tiktok") and "Việt Nam" in query
    assert "Giày Búp Bê Nơ Mix" in query and "DEAL" not in query and "Topsneaker" not in query


def test_keeps_the_first_three_that_really_exist_in_googles_order():
    checked = []

    def check(tag):
        checked.append(tag)
        return {"#a": 50_000, "#fake": None, "#tiny": 10, "#b": 2_000, "#c": 9_000_000, "#d": 5_000}.get(tag)

    tags, verified = pick_real(["#a", "#fake", "#tiny", "#b", "#c", "#d"], check)
    assert tags == ["#a", "#b", "#c"] and verified
    assert "#d" not in checked  # stops once it has 3


def test_unreachable_tiktok_keeps_candidates_but_says_so():
    def blocked(tag):
        raise RuntimeError("network blocked")

    assert pick_real(["#a", "#b", "#c", "#d"], blocked) == (["#a", "#b", "#c"], False)


@pytest.fixture
def job_ctx(make_context):
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title=TITLE))
    return make_context(job=job)


def test_step_checks_google_candidates_on_tiktok(job_ctx, monkeypatch):
    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title, kind="": list(TIKTOK) + ["#giaybupbe", "#thoitrangnu"])
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: pytest.fail("Google worked"))
    monkeypatch.setattr(hashtags_step, "tiktok_checker",
                        lambda ctx: lambda tag: {**TIKTOK, "#giaybupbe": 80_000, "#thoitrangnu": 3_000_000}.get(tag))
    run_hashtags(job_ctx)
    assert job_ctx.job.hashtags == ["#giaycaogot", "#giaybupbe", "#thoitrangnu"]
    assert job_ctx.job.hashtags_source == "google"


def test_step_falls_back_to_claude_then_to_nothing_without_failing(job_ctx, monkeypatch):
    def broken(ctx, title, kind=""):
        raise RuntimeError("captcha")

    monkeypatch.setattr(hashtags_step, "tiktok_checker", lambda ctx: lambda tag: 5_000)
    monkeypatch.setattr(hashtags_step, "from_google", broken)
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: ["#x", "#y", "#z", "#w"])
    run_hashtags(job_ctx)
    assert job_ctx.job.hashtags == ["#x", "#y", "#z"] and job_ctx.job.hashtags_source == "claude"

    monkeypatch.setattr(hashtags_step, "from_claude", broken)
    run_hashtags(job_ctx)  # must not raise: hashtags are a nice-to-have
    assert job_ctx.job.hashtags == []


def test_unverified_hashtags_are_marked(job_ctx, monkeypatch):
    def blocked(tag):
        raise RuntimeError("network blocked")

    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title, kind="": ["#a", "#b", "#c"])
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: pytest.fail("Google worked"))
    monkeypatch.setattr(hashtags_step, "tiktok_checker", lambda ctx: blocked)
    run_hashtags(job_ctx)
    assert job_ctx.job.hashtags == ["#a", "#b", "#c"] and not job_ctx.job.hashtags_verified


def test_no_title_no_search(make_context, monkeypatch):
    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title, kind="": pytest.fail("nothing to search for"))
    run_hashtags(make_context())


@pytest.mark.parametrize("verified,line", [(True, "#giaycaogot #thoitrangnu #xuhuong"),
                                           (False, "#giaycaogot #thoitrangnu #xuhuong (chưa xác minh)")])
def test_title_message_carries_the_hashtags(make_context, monkeypatch, verified, line):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:T")
    api = FakeApi()
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: api)
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title="Giày"),
                   telegram=TelegramOrigin(chat_id=1, message_id=2, preview_sent=True, file_sent=True),
                   hashtags=["#giaycaogot", "#thoitrangnu", "#xuhuong"], hashtags_verified=verified)
    ctx = make_context(job=job)
    make_test_clip(ctx.path("final-4k60.mp4"), width=360, height=640, seconds=1)
    run_send_telegram(ctx)
    assert api.calls[-1][1]["text"] == f"Giày\n{line}"


def test_google_module_has_no_side_effects_on_import():
    assert google_hashtags.AI_MODE_URL.startswith("https://www.google.com/search")


def test_google_is_asked_about_the_main_product_type_when_claude_named_it():
    # "Dép sandal lỗ nữ mới 2026 - …" should be asked as "dép sandal nữ".
    assert search_query("Dép sandal lỗ nữ mới 2026 - Thiết kế mũi kín", product_type="dép sandal nữ") == \
        "10 hashtag tiktok phổ biến, đang được dùng nhiều ở Việt Nam cho dép sandal nữ"


def test_claude_names_the_product_type_alongside_the_prompt():
    import json as _json

    from app.steps.prompt_parsing import parse_claude_output
    from app.steps.prompt_step import build_instruction

    assert "product_type" in build_instruction("rules", "", "", "", "")
    reply = {"prompt": "p", "summary": "s", "product_type": " Dép sandal nữ "}
    stdout = _json.dumps({"type": "result", "result": _json.dumps(reply, ensure_ascii=False)})
    assert parse_claude_output(stdout)["product_type"] == "dép sandal nữ"
    old = _json.dumps({"type": "result", "result": _json.dumps({"prompt": "p", "summary": "s"})})
    assert parse_claude_output(old)["product_type"] == ""


def test_step_uses_the_product_type_from_the_prompt(job_ctx, monkeypatch):
    import json as _json

    job_ctx.path("prompt.json").write_text(_json.dumps({"prompt": "p", "summary": "s", "product_type": "giày búp bê nữ"},
                                                       ensure_ascii=False), encoding="utf-8")
    asked = []
    monkeypatch.setattr(hashtags_step, "from_google", lambda ctx, title, product_type="": asked.append(product_type) or [])
    monkeypatch.setattr(hashtags_step, "from_claude", lambda ctx, title: [])
    run_hashtags(job_ctx)
    assert asked == ["giày búp bê nữ"]
