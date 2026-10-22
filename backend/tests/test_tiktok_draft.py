"""Saving the exported video as a TikTok Studio draft, then telling the user on Telegram (fake browser + Bot API)."""

import pytest

from app.config import TelegramConfig, TikTokConfig
from app.job_models import JobState, SourceInfo, TelegramOrigin
from app.steps import tiktok_draft_step
from app.steps.step_types import StepFailure
from app.steps.tiktok_draft_step import draft_description, notify_target, run_tiktok_draft
from app.telegram.telegram_api import TelegramApiError

TITLE = "Giày Búp Bê Nơ Mix (Chất liệu PVC) Đế Siêu Nhẹ, Chống Trơn"


class FakeApi:
    def __init__(self, fail=False):
        self.messages, self.fail = [], fail

    def send_message(self, chat_id, text, reply_to=None):
        if self.fail:
            raise TelegramApiError("Bad Gateway")
        self.messages.append({"chat_id": chat_id, "text": text, "reply_to": reply_to})


def job(**kw) -> JobState:
    return JobState(id="t", name="giay-bup-be", input_file="input.jpg", created_at="t",
                    source=SourceInfo(url="https://shop.tiktok.com/vn/pdp/1", title=TITLE), **kw)


@pytest.fixture
def rig(make_context, make_config, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    exported = tmp_path / "giay_4k60.mp4"
    exported.write_bytes(b"video")
    saved, api = [], FakeApi()
    monkeypatch.setattr(tiktok_draft_step, "save_draft_in_browser",
                        lambda ctx, video, description: saved.append((video, description)))
    monkeypatch.setattr(tiktok_draft_step, "make_api", lambda token: api)

    def build(the_job=None, **config):
        the_job = the_job or job()
        the_job.export_path = str(exported)
        cfg = make_config(telegram=TelegramConfig(allowed_user_ids=[111222333]), **config)
        return make_context(job=the_job, config=cfg)

    return build, saved, api, exported


def test_description_is_the_product_title_from_the_link():
    assert draft_description(job()) == TITLE
    assert draft_description(JobState(id="t", name="son-moi", input_file="a.png", created_at="t")) == "son-moi"


def test_description_is_claude_caption_when_there_is_one():
    assert draft_description(job(caption="Búp bê nơ mà nhẹ tênh 🎀")) == "Búp bê nơ mà nhẹ tênh 🎀"


def test_notify_replies_to_the_link_message_or_messages_the_owner(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    owner = TelegramConfig(allowed_user_ids=[111222333])
    assert notify_target(job(telegram=TelegramOrigin(chat_id=111, message_id=42)), owner) == (111, 42)
    assert notify_target(job(), owner) == (111222333, None)
    assert notify_target(job(), TelegramConfig()) is None


def test_saves_draft_with_title_then_notifies(rig):
    build, saved, api, exported = rig
    ctx = build()
    run_tiktok_draft(ctx)
    assert saved == [(exported, TITLE)]
    assert ctx.job.tiktok.saved_at and ctx.job.tiktok.notified
    (msg,) = api.messages
    assert msg["chat_id"] == 111222333 and "nháp" in msg["text"] and TITLE in msg["text"]


def test_retry_after_telegram_error_does_not_save_a_second_draft(rig):
    build, saved, api, _ = rig
    ctx = build()
    api.fail = True
    with pytest.raises(StepFailure):
        run_tiktok_draft(ctx)
    api.fail = False
    run_tiktok_draft(ctx)
    assert len(saved) == 1 and len(api.messages) == 1


def test_disabled_in_config_does_nothing(rig):
    build, saved, api, _ = rig
    run_tiktok_draft(build(tiktok=TikTokConfig(save_draft=False)))
    assert saved == [] and api.messages == []


def test_missing_video_fails_clearly(rig):
    build, saved, _, exported = rig
    exported.unlink()
    with pytest.raises(StepFailure):
        run_tiktok_draft(build())
    assert saved == []


def test_allowed_ids_come_from_config_and_env(monkeypatch):
    # IDs can live in .env (kept out of git) instead of config.yaml.
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "222, 333")
    assert TelegramConfig(allowed_user_ids=[111, 222]).user_ids == [111, 222, 333]
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS")
    assert TelegramConfig().user_ids == []
