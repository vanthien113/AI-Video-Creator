"""A failed job is reported on Telegram right away: under the link message, or to the owner for web jobs."""

from PIL import Image

from app.config import TelegramConfig
from app.job_models import JobError, JobState, JobStatus, SourceInfo, TelegramOrigin
from app.steps.step_types import StepFailure
from app.telegram.telegram_notify import failure_text, send_failure

from .test_pipeline_runner import drain, new_job, rig  # noqa: F401  (fixture re-export)

OWNER = 111222333


class FakeApi:
    def __init__(self):
        self.photos, self.messages = [], []

    def send_photo(self, chat_id, path, caption, reply_to=None, reply_markup=None):
        assert path.exists()
        self.photos.append({"chat_id": chat_id, "caption": caption, "reply_to": reply_to})

    def send_message(self, chat_id, text, reply_to=None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_to": reply_to})


def failed_job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t", status=JobStatus.failed,
                    source=SourceInfo(url="u", title="Giày búp bê"),
                    error=JobError(step="flow_generate", reason="Flow báo sinh video thất bại.", **kw.pop("error", {})), **kw)


def test_runner_reports_each_failure_once_and_never_successes(rig):
    store, runner, actions, _, behaviour = rig
    seen = []
    runner.on_failure = seen.append
    ok = new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    drain(store, runner)
    assert seen == [] and store.get(ok.id).status == JobStatus.done

    behaviour["upscale"] = StepFailure("hỏng")
    bad = new_job(store, {"cutout": True})
    drain(store, runner)
    assert [(j.id, j.error.step, j.error.reason) for j in seen] == [(bad.id, "upscale", "hỏng")]


def test_text_names_the_step_reason_and_product():
    text = failure_text(failed_job())
    assert text.startswith("❌ Lỗi ở bước Flow sinh: Flow báo sinh video thất bại.")
    assert "Giày búp bê" in text and "Thử lại" in text


def test_screenshot_goes_with_the_notice_under_the_link(tmp_path):
    (tmp_path / "errors").mkdir()
    Image.new("RGB", (40, 30), "red").save(tmp_path / "errors" / "shot.png")
    job = failed_job(error={"screenshot": "errors/shot.png"}, telegram=TelegramOrigin(chat_id=5, message_id=9))
    api = FakeApi()
    send_failure(TelegramConfig(allowed_user_ids=[OWNER]), job, tmp_path, api)
    assert api.messages == [] and api.photos[0]["chat_id"] == 5 and api.photos[0]["reply_to"] == 9
    assert "Flow sinh" in api.photos[0]["caption"]


def test_web_jobs_tell_the_owner_and_nobody_means_silence(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    api = FakeApi()
    send_failure(TelegramConfig(allowed_user_ids=[OWNER]), failed_job(), tmp_path, api)
    assert api.messages[0]["chat_id"] == OWNER and api.messages[0]["reply_to"] is None
    api2 = FakeApi()
    send_failure(TelegramConfig(), failed_job(), tmp_path, api2)
    assert api2.messages == [] and api2.photos == []
