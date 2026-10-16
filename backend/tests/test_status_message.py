"""One Telegram status message per job, edited in place as the job moves between steps (never re-sent)."""

from app.config import TelegramConfig
from app.job_models import JobError, JobState, JobStatus, SourceInfo, TelegramOrigin
from app.steps.step_types import StepFailure
from app.telegram.telegram_notify import StatusNotifier, status_text

from .test_pipeline_runner import drain, new_job, rig  # noqa: F401  (fixture re-export)

OWNER = 111222333


class FakeApi:
    def __init__(self):
        self.sent, self.edits = [], []

    def send_message(self, chat_id, text, reply_to=None):
        self.sent.append((chat_id, text, reply_to))
        return 500 + len(self.sent)

    def edit_text(self, chat_id, message_id, text):
        self.edits.append((message_id, text))


def job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t",
                    source=SourceInfo(url="u", title="Giày cao gót"), **kw)


def test_status_text_is_the_product_and_one_short_line():
    assert status_text(job(status=JobStatus.running, current_step="flow_generate")) == "🎬 Giày cao gót\n⏳ Đang: Flow sinh"
    assert status_text(job(status=JobStatus.awaiting_review, gate="pick_image")).endswith("🖼 Chờ chọn ảnh")
    assert status_text(job(status=JobStatus.awaiting_review, gate="prompt")).endswith("⏸ Chờ duyệt: Prompt")
    assert status_text(job(status=JobStatus.done)).endswith("✅ Xong")
    failed = job(status=JobStatus.failed, error=JobError(step="enhance", reason="x"))
    assert status_text(failed).endswith("❌ Lỗi ở bước Nâng 60fps")
    assert status_text(job(status=JobStatus.cancelled)).endswith("⏹ Đã huỷ")


def test_one_message_edited_per_step_and_nothing_for_unchanged_text(rig, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:T")
    store, runner, _, _, _ = rig
    api = FakeApi()
    runner.config.telegram = TelegramConfig(allowed_user_ids=[OWNER])
    notifier = StatusNotifier(runner.config, store, api_factory=lambda token: api, background=False)
    runner.on_change = notifier
    j = new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    drain(store, runner)
    notifier.flush()

    assert len(api.sent) == 1 and api.sent[0][0] == OWNER       # a single message for the whole job
    assert store.get(j.id).status_message.message_id == 501
    texts = [t for _, t in api.edits]
    assert texts[-1].endswith("✅ Xong") and "⏳ Đang: Tách nền" in api.sent[0][1]
    assert len(texts) == len(set(texts))                         # never the same text twice


def test_bot_jobs_get_the_status_under_the_link(rig, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:T")
    store, runner, actions, _, behaviour = rig
    api = FakeApi()
    notifier = StatusNotifier(runner.config, store, api_factory=lambda token: api, background=False)
    runner.on_change = notifier
    behaviour["upscale"] = StepFailure("hỏng")
    j = new_job(store, {"cutout": True})
    store.update(j.id, lambda s: setattr(s, "telegram", TelegramOrigin(chat_id=5, message_id=9)))
    drain(store, runner)
    notifier.flush()
    assert api.sent[0][0] == 5 and api.sent[0][2] == 9
    assert api.edits[-1][1].endswith("❌ Lỗi ở bước Upscale")


def test_quiet_without_a_token_or_a_target(rig, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    store, runner, _, _, _ = rig
    api = FakeApi()
    notifier = StatusNotifier(runner.config, store, api_factory=lambda token: api, background=False)
    runner.on_change = notifier
    new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    drain(store, runner)
    notifier.flush()
    assert api.sent == [] and api.edits == []
