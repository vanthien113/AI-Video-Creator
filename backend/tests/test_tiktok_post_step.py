"""The tiktok_post step with a fake TikTok Studio and a fake Bot API."""

import contextlib
from datetime import datetime, timedelta

import pytest

from app.config import TelegramConfig
from app.job_models import JobState, JobStatus, SourceInfo, TelegramMessageRef, TelegramOrigin, TikTokPostState
from app.steps import tiktok_post_step
from app.steps.step_types import StepFailure
from app.steps.tiktok_post_step import BrowserStudio, other_scheduled, run_tiktok_post
from app.telegram.telegram_api import TelegramApiError
from app.telegram.telegram_post import FAILED_TEXT, OFFER_TEXT
from app.tiktok.post_plan import slot_label

URL = "https://shop.tiktok.com/vn/pdp/1737383451447231991"
TITLE = "[JOLY 01] Dép sục+Tặng 1 bộ charm"


class FakeStudio:
    def __init__(self):
        self.items, self.found, self.fail = [], True, None
        self.posted, self.clicks, self.boom, self.last_error = [], 0, None, None
        self.results, self.find_calls = [], []  # results: answers of the next find_post calls, then `found`

    def latest(self, when: datetime):
        self.items = [{"desc": "bài cũ", "post_time": str(int(when.timestamp()))}]

    def content_items(self):
        return self.items

    def post(self, plan, before_click, dry_run=False):
        self.posted.append(plan)
        if self.fail:
            raise StepFailure(self.fail)
        before_click()
        if self.boom:
            raise self.boom
        self.clicks += 1

    def find_post(self, title, since, schedule_at, tries=6):
        self.find_calls.append((since, schedule_at, tries))
        return self.results.pop(0) if self.results else self.found


class FakeApi:
    def __init__(self):
        self.sent, self.edits, self.fail = [], [], False

    def send_message(self, chat_id, text, reply_to=None, reply_markup=None):
        if self.fail:
            raise TelegramApiError("Bad Gateway")
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "markup": reply_markup})
        return 400 + len(self.sent)

    def edit_text(self, chat_id, message_id, text):
        self.edits.append((message_id, text))


@pytest.fixture
def rig(make_context, make_config, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    exported = tmp_path / "dep-suc_2k60.mp4"
    exported.write_bytes(b"video")
    studio, api = FakeStudio(), FakeApi()
    monkeypatch.setattr(tiktok_post_step, "open_studio", lambda ctx: studio)
    monkeypatch.setattr(tiktok_post_step, "make_api", lambda token: api)

    def build(mode="now", offered=True, **job_fields):
        post = TikTokPostState(mode=mode)
        if offered:
            post.offer_token, post.offer_message = "abcd1234", TelegramMessageRef(chat_id=111, message_id=99)
        fields = dict(source=SourceInfo(url=URL, title=TITLE), hashtags=["#depsuc", "#giaydepnu"],
                      telegram=TelegramOrigin(chat_id=111, message_id=42), export_path=str(exported), post=post)
        fields.update(job_fields)
        job = JobState(id="t", name="dep-suc", input_file="input.jpg", created_at="t", **fields)
        return make_context(job=job, config=make_config(telegram=TelegramConfig(allowed_user_ids=[111])))

    return build, studio, api, exported


def test_post_now_clicks_once_confirms_then_reports(rig):
    build, studio, api, exported = rig
    ctx = build("now")
    run_tiktok_post(ctx)
    (plan,) = studio.posted
    assert plan.video == exported and plan.title == TITLE and plan.hashtags == ["#depsuc", "#giaydepnu"]
    assert plan.product_id == "1737383451447231991" and plan.schedule_at is None
    post = ctx.job.post
    assert post.submitted_at and post.done_at and post.notified and studio.clicks == 1
    assert api.edits == [(99, f"✅ Đã đăng lên TikTok lúc {datetime.fromisoformat(post.done_at):%H:%M}")]
    (msg,) = api.sent
    assert msg["text"] == f"✅ Đã đăng lên TikTok: {TITLE}" and msg["reply_to"] == 42 and msg["chat_id"] == 111


def test_schedule_takes_the_slot_after_the_latest_post(rig):
    build, studio, api, _ = rig
    ctx = build("schedule")
    latest = (datetime.now() + timedelta(days=2)).replace(hour=21, minute=30, second=0, microsecond=0)
    studio.latest(latest)
    run_tiktok_post(ctx)
    want = latest.replace(hour=23, minute=0)
    assert studio.posted[0].schedule_at == want
    assert ctx.job.post.scheduled_for == want.isoformat(timespec="seconds")
    assert api.sent[0]["text"] == f"🗓 Đã lên lịch đăng TikTok lúc {slot_label(want)}: {TITLE}"
    assert api.edits[-1] == (99, f"🗓 Đã lên lịch đăng TikTok: {slot_label(want)}")


def test_slots_this_tool_already_scheduled_count_too(rig):
    build, studio, _, _ = rig
    ctx = build("schedule")
    taken = (datetime.now() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    other_dir = ctx.config.paths.jobs_dir / "20261017-090000-other"
    other_dir.mkdir(parents=True)
    other = JobState(id="other", name="x", input_file="", created_at="t",
                     post=TikTokPostState(mode="schedule", scheduled_for=taken.isoformat(), submitted_at="t"))
    (other_dir / "state.json").write_text(other.model_dump_json(), encoding="utf-8")
    assert other_scheduled(ctx) == [taken]
    run_tiktok_post(ctx)
    assert studio.posted[0].schedule_at == taken.replace(hour=11)


def test_too_far_ahead_stops_before_uploading(rig):
    build, studio, api, _ = rig
    ctx = build("schedule")
    studio.latest(datetime.now() + timedelta(days=31))
    with pytest.raises(StepFailure, match="30 ngày"):
        run_tiktok_post(ctx)
    assert studio.posted == [] and api.edits[-1] == (99, FAILED_TEXT)


def test_failure_before_the_click_can_simply_be_retried(rig):
    build, studio, api, _ = rig
    ctx = build("now")
    studio.fail = "Không tìm thấy sản phẩm 1737383451447231991 khi Add link."
    with pytest.raises(StepFailure, match="Không tìm thấy sản phẩm"):
        run_tiktok_post(ctx)
    assert ctx.job.post.submitted_at is None and api.edits[-1] == (99, FAILED_TEXT)
    studio.fail = None
    run_tiktok_post(ctx)
    assert ctx.job.post.done_at and studio.clicks == 1


def test_not_seen_after_the_click_never_clicks_again(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.found = False
    with pytest.raises(StepFailure, match="Tool đã bấm Post"):
        run_tiktok_post(ctx)
    assert ctx.job.post.submitted_at and not ctx.job.post.done_at
    studio.found = True
    with pytest.raises(StepFailure, match="Tool đã bấm Post"):
        run_tiktok_post(ctx)  # without the user's Thử lại (which clears submitted_at) it stays put
    assert studio.clicks == 1


def test_telegram_error_after_posting_only_resends_the_message(rig):
    build, studio, api, _ = rig
    ctx = build("now")
    api.fail = True
    with pytest.raises(StepFailure, match="nhắn Telegram lỗi"):
        run_tiktok_post(ctx)
    assert ctx.job.post.done_at and not ctx.job.post.notified
    assert all(text != FAILED_TEXT for _, text in api.edits)  # the post did go out
    api.fail = False
    run_tiktok_post(ctx)
    assert studio.clicks == 1 and len(api.sent) == 1 and ctx.job.post.notified


def test_nobody_asked_only_offers_the_buttons_once(rig):
    build, studio, api, _ = rig
    ctx = build(None, offered=False)
    run_tiktok_post(ctx)
    (msg,) = api.sent
    assert msg["text"] == OFFER_TEXT and msg["reply_to"] == 42 and msg["markup"]["inline_keyboard"]
    run_tiktok_post(ctx)
    assert len(api.sent) == 1 and studio.posted == []


def test_no_buttons_while_posting_is_off(rig):
    build, studio, api, _ = rig
    ctx = build(None, offered=False)
    ctx.config.tiktok.post_enabled = False
    run_tiktok_post(ctx)
    assert api.sent == [] and studio.posted == []


def test_offer_failure_never_fails_the_job(rig):
    build, studio, api, _ = rig
    ctx = build(None, offered=False)
    api.fail = True
    run_tiktok_post(ctx)  # no exception: the tool's buttons still work
    assert ctx.job.post.offer_message is None and studio.posted == []


def test_missing_video_fails_before_any_browser_work(rig):
    build, studio, _, exported = rig
    exported.unlink()
    with pytest.raises(StepFailure, match="video đã xuất"):
        run_tiktok_post(build("now"))
    assert studio.posted == []


def test_find_post_keeps_reading_after_a_failed_read(rig, monkeypatch):
    build, _, _, _ = rig
    ctx = build("now")
    monkeypatch.setattr(tiktok_post_step, "CONFIRM_WAIT_SEC", 0)
    studio = BrowserStudio(ctx)
    since = datetime.now() - timedelta(minutes=1)
    reads = []

    def flaky():
        reads.append(1)
        if len(reads) == 1:
            raise StepFailure("đọc lỗi", screenshot="errors/a.png")
        return [{"desc": TITLE, "create_time": str(int(datetime.now().timestamp()))}]

    studio.content_items = flaky
    assert studio.find_post(TITLE, since, None) is True
    assert len(reads) == 2

    def always_fails():
        raise StepFailure("đọc lỗi", screenshot="errors/a.png")

    studio.content_items = always_fails
    assert studio.find_post(TITLE, since, None) is False
    assert studio.last_error.screenshot == "errors/a.png"


class FakePage:
    def __init__(self, url):
        self.url, self.closed = url, False

    def close(self):
        self.closed = True


def test_tab_stays_open_while_tiktok_shows_the_form(rig, monkeypatch):
    build, _, _, _ = rig
    ctx = build("now")
    page_holder = {}

    @contextlib.contextmanager
    def fake_context(port):
        yield object()

    def fake_new_tab(context):
        page_holder["page"] = FakePage(url=page_holder["url"])
        return page_holder["page"]

    monkeypatch.setattr(tiktok_post_step, "browser_context", fake_context)
    monkeypatch.setattr(tiktok_post_step, "new_tab", fake_new_tab)
    monkeypatch.setattr(tiktok_post_step, "post_video", lambda *args, **kwargs: None)
    studio = BrowserStudio(ctx)

    page_holder["url"] = "https://www.tiktok.com/tiktokstudio/upload?from=creator"
    studio.post(None, lambda: None)
    assert page_holder["page"].closed is False

    page_holder["url"] = "https://www.tiktok.com/tiktokstudio/content"
    studio.post(None, lambda: None)
    assert page_holder["page"].closed is True

    page_holder["url"] = "https://www.tiktok.com/tiktokstudio/content"
    studio.post(None, lambda: None, dry_run=True)
    assert page_holder["page"].closed is False


def test_unconfirmed_failure_carries_the_last_read_screenshot(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.found = False
    studio.last_error = StepFailure("đọc lỗi", screenshot="errors/y.png")
    with pytest.raises(StepFailure, match="Tool đã bấm Post") as info:
        run_tiktok_post(ctx)
    assert info.value.screenshot == "errors/y.png"


def test_failure_after_the_click_says_the_click_happened(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.boom = StepFailure("boom", screenshot="errors/x.png")
    studio.found = False
    with pytest.raises(StepFailure, match="Tool đã bấm Post") as info:
        run_tiktok_post(ctx)
    assert info.value.screenshot == "errors/x.png"
    assert ctx.job.post.submitted_at and not ctx.job.post.done_at


def test_cancelled_job_is_not_clicked(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    ctx.is_cancelled = lambda: True
    with pytest.raises(StepFailure, match="huỷ"):
        run_tiktok_post(ctx)
    assert studio.clicks == 0 and ctx.job.post.submitted_at is None


def test_error_after_the_click_still_checks_the_content_page(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.boom = RuntimeError("Target closed")
    run_tiktok_post(ctx)  # found on Content: the post went out
    assert studio.find_calls and ctx.job.post.done_at and studio.clicks == 0


def test_unexpected_error_after_the_click_unfound_says_the_click_happened(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.boom, studio.found = RuntimeError("Target closed"), False
    with pytest.raises(StepFailure, match="Tool đã bấm Post"):
        run_tiktok_post(ctx)
    assert ctx.job.post.submitted_at and not ctx.job.post.done_at


def test_job_cancelled_in_the_store_is_not_clicked(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    ctx.job.status = JobStatus.cancelled  # not through ctx.is_cancelled
    with pytest.raises(StepFailure, match="huỷ"):
        run_tiktok_post(ctx)
    assert studio.clicks == 0 and ctx.job.post.submitted_at is None


def test_find_post_survives_an_unexpected_read_error(rig, monkeypatch):
    build, _, _, _ = rig
    ctx = build("now")
    monkeypatch.setattr(tiktok_post_step, "CONFIRM_WAIT_SEC", 0)
    studio = BrowserStudio(ctx)
    reads = []

    def broken():
        reads.append(1)
        raise ValueError("bad json")

    studio.content_items = broken
    assert studio.find_post(TITLE, datetime.now(), None, tries=2) is False
    assert len(reads) == 2 and isinstance(studio.last_error, StepFailure)


def test_error_opening_the_tab_becomes_a_step_failure(rig, monkeypatch):
    build, _, _, _ = rig
    ctx = build("now")

    @contextlib.contextmanager
    def fake_context(port):
        yield object()

    def boom(context):
        raise RuntimeError("Target closed")

    monkeypatch.setattr(tiktok_post_step, "browser_context", fake_context)
    monkeypatch.setattr(tiktok_post_step, "new_tab", boom)
    with pytest.raises(StepFailure, match="Không mở được tab TikTok Studio"):
        BrowserStudio(ctx)._in_tab(lambda page: None)


def test_failed_content_read_closes_its_tab(rig, monkeypatch):
    build, _, _, _ = rig
    ctx = build("now")
    page = FakePage("https://www.tiktok.com/tiktokstudio/content")

    @contextlib.contextmanager
    def fake_context(port):
        yield object()

    monkeypatch.setattr(tiktok_post_step, "browser_context", fake_context)
    monkeypatch.setattr(tiktok_post_step, "new_tab", lambda context: page)
    monkeypatch.setattr(tiktok_post_step, "capture_page_error", lambda p, d: None)

    def broken(p, url):
        raise tiktok_post_step.ContentPageError("không đọc được")

    monkeypatch.setattr(tiktok_post_step, "read_items", broken)
    with pytest.raises(StepFailure):
        BrowserStudio(ctx).content_items()
    assert page.closed is True


def test_unexpected_error_still_marks_the_offer_failed(rig, monkeypatch):
    build, studio, api, _ = rig
    ctx = build("now")
    monkeypatch.setattr(tiktok_post_step, "make_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        run_tiktok_post(ctx)
    assert api.edits[-1] == (99, FAILED_TEXT)


def test_recheck_finds_the_earlier_post_and_never_posts(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    ctx.job.post.recheck_since = "2026-10-17T10:31:00"
    studio.found = True
    run_tiktok_post(ctx)
    post = ctx.job.post
    assert studio.posted == [] and studio.clicks == 0 and post.done_at and post.recheck_since is None
    assert post.submitted_at == "2026-10-17T10:31:00" and studio.find_calls[0][2] == 1


def test_recheck_not_found_posts_normally(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    ctx.job.post.recheck_since = "2026-10-17T10:31:00"
    studio.results = [False]  # the recheck; the confirmation after the new click then finds it
    run_tiktok_post(ctx)
    assert studio.clicks == 1 and ctx.job.post.done_at and ctx.job.post.recheck_since is None
    assert ctx.job.post.submitted_at != "2026-10-17T10:31:00"
