"""Đăng ngay / Lên lịch buttons on Telegram and the status line while posting (fake Bot API)."""

import json

import httpx
import pytest

from app.job_models import JobState, JobStatus, SourceInfo, TelegramMessageRef, TelegramOrigin, TikTokPostState
from app.telegram.telegram_api import TelegramApi
from app.telegram.telegram_notify import status_text
from app.telegram.telegram_post import (FAILED_TEXT, OFFER_TEXT, PostHandler, done_text, keyboard, parse,
                                        result_message, send_offer, waiting_text)
from app.telegram.telegram_setup import route_taps

from .test_link_jobs import URL
from .test_pipeline_runner import new_job, rig  # noqa: F401  (fixture re-export)
from .test_tiktok_post_actions import done_link_job

CHAT, LINK_MSG, OFFER_MSG = 111222333, 7, 99


class FakeApi:
    def __init__(self):
        self.sent, self.edits = [], []

    def send_message(self, chat_id, text, reply_to=None, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "markup": reply_markup})
        return 300 + len(self.sent)

    def edit_text(self, chat_id, message_id, text):
        self.edits.append((chat_id, message_id, text))


def tap(data):
    return {"id": "cb", "from": {"id": CHAT}, "data": data, "message": {"message_id": OFFER_MSG, "chat": {"id": CHAT}}}


def job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t",
                    source=SourceInfo(url=URL, title="Giày búp bê"), **kw)


def updater(target: JobState):
    def update(fn):
        fn(target)
        return target
    return update


# ---- pure parts ---------------------------------------------------------------

def test_buttons_and_their_data():
    row = keyboard("abcd1234")["inline_keyboard"][0]
    assert [b["text"] for b in row] == ["📤 Đăng ngay", "🗓 Lên lịch"]
    assert all(len(b["callback_data"].encode()) <= 64 for b in row)
    assert parse("t:abcd1234:n") == ("abcd1234", "now") and parse("t:abcd1234:s") == ("abcd1234", "schedule")
    assert parse("t:abcd1234:x") is None and parse("p:abcd1234:1") is None and parse("") is None


def test_texts_for_each_state():
    scheduled = job(post=TikTokPostState(mode="schedule", scheduled_for="2026-10-18T19:00:00",
                                         done_at="2026-10-17T10:32:00"))
    assert done_text(scheduled) == "🗓 Đã lên lịch đăng TikTok: 19:00 Chủ nhật 18/10"
    assert result_message(scheduled) == "🗓 Đã lên lịch đăng TikTok lúc 19:00 Chủ nhật 18/10: Giày búp bê"
    posted = job(post=TikTokPostState(mode="now", done_at="2026-10-17T10:32:00"))
    assert done_text(posted) == "✅ Đã đăng lên TikTok lúc 10:32"
    assert result_message(posted) == "✅ Đã đăng lên TikTok: Giày búp bê"
    assert waiting_text("schedule") == "⏳ Đã nhận: Lên lịch. Đang chờ lượt…"


def test_offer_goes_once_under_the_link_and_only_for_bot_jobs_with_a_product_id():
    api = FakeApi()
    bot = job(telegram=TelegramOrigin(chat_id=CHAT, message_id=LINK_MSG))
    send_offer(bot, api, updater(bot))
    (sent,) = api.sent
    assert sent["text"] == OFFER_TEXT and sent["chat_id"] == CHAT and sent["reply_to"] == LINK_MSG
    assert sent["markup"] == keyboard(bot.post.offer_token) and bot.post.offer_message.message_id == 301
    send_offer(bot, api, updater(bot))  # a retry does not send a second one
    tool_only = job()
    send_offer(tool_only, api, updater(tool_only))  # pasted in the tool: buttons are in the tool
    short = JobState(id="s", name="s", input_file="", created_at="t", source=SourceInfo(url="https://vt.tiktok.com/x"),
                     telegram=TelegramOrigin(chat_id=CHAT, message_id=LINK_MSG))
    send_offer(short, api, updater(short))  # no product ID: nothing to Add link with
    assert len(api.sent) == 1


def test_send_message_can_carry_buttons():
    seen = []
    api = TelegramApi("1:T", httpx.Client(transport=httpx.MockTransport(
        lambda r: seen.append(r) or httpx.Response(200, json={"ok": True, "result": {"message_id": 77}}))))
    assert api.send_message(5, "hi", reply_to=9, reply_markup=keyboard("abcd1234")) == 77
    body = json.loads(seen[0].content)
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "t:abcd1234:n"
    api.send_message(5, "plain")
    assert "reply_markup" not in json.loads(seen[1].content)


# ---- taps, with a real job store ---------------------------------------------------

@pytest.fixture
def offered(rig):
    store, runner, actions, _, _ = rig
    job_id = done_link_job(store, runner)

    def give_offer(j):
        j.post.offer_token = "abcd1234"
        j.post.offer_message = TelegramMessageRef(chat_id=CHAT, message_id=OFFER_MSG)

    store.update(job_id, give_offer)
    api = FakeApi()
    return store, actions, api, job_id, PostHandler(actions, api)


def test_tap_queues_the_post_and_drops_the_buttons(offered):
    store, _, api, job_id, handler = offered
    assert handler.handle(tap("t:abcd1234:s")) == "Lên lịch!"
    queued = store.get(job_id)
    assert queued.post.mode == "schedule" and queued.status == JobStatus.queued
    assert api.edits[-1] == (CHAT, OFFER_MSG, "⏳ Đã nhận: Lên lịch. Đang chờ lượt…")


def test_second_tap_or_tool_first_only_explains(offered):
    store, actions, api, job_id, handler = offered
    actions.request_post(job_id, "now")  # pressed in the tool first
    assert "đã được yêu cầu" in handler.handle(tap("t:abcd1234:s"))
    assert store.get(job_id).post.mode == "now"
    assert api.edits[-1][2] == "⏳ Đã nhận: Đăng ngay. Đang chờ lượt…"


def test_tap_before_the_job_is_done_keeps_the_buttons(rig):
    store, _, actions, _, _ = rig
    waiting = new_job(store)
    store.update(waiting.id, lambda j: (setattr(j, "source", SourceInfo(url=URL)),
                                        setattr(j.post, "offer_token", "ffff0000")))
    api = FakeApi()
    assert "đã xong" in PostHandler(actions, api).handle(tap("t:ffff0000:n"))
    assert api.edits == []


def test_stale_button_after_the_video_was_remade_posts_nothing(offered):
    store, actions, api, job_id, handler = offered
    actions.retry(job_id, "export")  # new video: post state (and its token) reset
    assert "đã cũ" in handler.handle(tap("t:abcd1234:n"))
    assert store.get(job_id).post.mode is None
    assert "đã cũ" in api.edits[-1][2]


def test_taps_are_routed_by_prefix():
    class Handler:
        def __init__(self, name):
            self.name = name

        def handle(self, callback):
            return self.name

    route = route_taps(Handler("pick"), Handler("post"))
    assert route({"data": "t:x:n"}) == "post"
    assert route({"data": "p:x:1"}) == "pick" and route({"data": "g:x"}) == "pick" and route({}) == "pick"


def test_status_message_while_posting():
    j = job(status=JobStatus.running, current_step="tiktok_post")
    assert status_text(j).endswith("✅ Xong")  # nobody pressed a button: nothing to do there
    j.post.mode = "now"
    assert status_text(j).endswith("⏳ Đang: Đăng TikTok")
    j.post.mode = "schedule"
    assert status_text(j).endswith("⏳ Đang: Lên lịch TikTok")
    j.status, j.post.scheduled_for, j.post.done_at = JobStatus.done, "2026-10-18T19:00:00", "2026-10-17T10:32:00"
    assert status_text(j).endswith("🗓 Đã lên lịch TikTok 19:00 18/10")
    j.post.mode = "now"
    assert status_text(j).endswith("✅ Đã đăng TikTok")
    assert FAILED_TEXT.startswith("❌")
