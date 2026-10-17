"""The tiktok_post step with a fake TikTok Studio and a fake Bot API."""

from datetime import datetime, timedelta

import pytest

from app.config import TelegramConfig
from app.job_models import JobState, SourceInfo, TelegramMessageRef, TelegramOrigin, TikTokPostState
from app.steps import tiktok_post_step
from app.steps.step_types import StepFailure
from app.steps.tiktok_post_step import other_scheduled, run_tiktok_post
from app.telegram.telegram_api import TelegramApiError
from app.telegram.telegram_post import FAILED_TEXT, OFFER_TEXT
from app.tiktok.post_plan import slot_label

URL = "https://shop.tiktok.com/vn/pdp/1737383451447231991"
TITLE = "[JOLY 01] Dép sục+Tặng 1 bộ charm"


class FakeStudio:
    def __init__(self):
        self.items, self.found, self.fail = [], True, None
        self.posted, self.clicks = [], 0

    def latest(self, when: datetime):
        self.items = [{"desc": "bài cũ", "post_time": str(int(when.timestamp()))}]

    def content_items(self):
        return self.items

    def post(self, plan, before_click, dry_run=False):
        self.posted.append(plan)
        if self.fail:
            raise StepFailure(self.fail)
        before_click()
        self.clicks += 1

    def find_post(self, title, since, schedule_at):
        return self.found


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
