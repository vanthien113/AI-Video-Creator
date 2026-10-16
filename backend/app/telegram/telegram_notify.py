"""Telegram notices outside the normal replies: where to send them, the "a job failed" notice, and the one
status message per job that is edited as the job moves between steps."""

import threading
from collections.abc import Callable
from pathlib import Path

from ..config import AppConfig, TelegramConfig
from ..job_models import PICK_GATE, JobState, JobStatus, TelegramMessageRef
from .telegram_api import TelegramApi, TelegramApiError

STEP_NAMES = {
    "fetch_source": "Đọc TikTok", "cutout": "Tách nền", "upscale": "Upscale", "prompt": "Prompt",
    "flow_generate": "Flow sinh", "flow_download": "Tải video", "enhance": "Nâng 60fps", "export": "Xuất file", "hashtags": "Hashtag",
    "send_telegram": "Gửi Telegram", "tiktok_draft": "Lưu nháp TikTok",
}


GATE_NAMES = {"cutout": "Ảnh tách nền", "prompt": "Prompt", "flow_video": "Video Flow"}


def notify_target(job: JobState, telegram: TelegramConfig) -> tuple[int, int | None] | None:
    """Reply under the link message for bot jobs; otherwise message the first allowed user."""
    if job.telegram:
        return job.telegram.chat_id, job.telegram.message_id
    return (telegram.user_ids[0], None) if telegram.user_ids else None


def failure_text(job: JobState) -> str:
    step = STEP_NAMES.get(job.error.step, job.error.step)
    title = (job.source.title if job.source else "") or job.name
    return (f"❌ Lỗi ở bước {step}: {job.error.reason}\n📦 {title}\n"
            "Mở AI Video Creator để xem chi tiết, sửa rồi bấm Thử lại.")


def send_failure(telegram: TelegramConfig, job: JobState, job_dir: Path, api) -> None:
    target = notify_target(job, telegram)
    if not target or not job.error:
        return
    chat_id, reply_to = target
    shot = job_dir / job.error.screenshot if job.error.screenshot else None
    if shot and shot.exists():
        api.send_photo(chat_id, shot, failure_text(job), reply_to=reply_to)
    else:
        api.send_message(chat_id, failure_text(job), reply_to=reply_to)


def failure_notifier(config: AppConfig, job_dir: Callable[[str], Path]) -> Callable[[JobState], None]:
    """For PipelineRunner.on_failure: sends in its own thread so a slow or broken Telegram never holds up jobs."""
    def notify(job: JobState) -> None:
        token = config.telegram.bot_token
        if not token:
            return

        def send() -> None:
            try:
                send_failure(config.telegram, job, job_dir(job.id), TelegramApi(token))
            except Exception:
                pass  # the failure is already on the job and in the UI

        threading.Thread(target=send, name="telegram-failure", daemon=True).start()

    return notify


# ---- one status message per job, edited in place ---------------------------------

def status_text(job: JobState) -> str:
    title = (job.source.title if job.source else "") or job.name
    if job.status == JobStatus.done:
        line = "✅ Xong"
    elif job.status == JobStatus.failed:
        line = f"❌ Lỗi ở bước {STEP_NAMES.get(job.error.step, job.error.step) if job.error else ''}".rstrip()
    elif job.status == JobStatus.cancelled:
        line = "⏹ Đã huỷ"
    elif job.status == JobStatus.awaiting_review:
        line = "🖼 Chờ chọn ảnh" if job.gate == PICK_GATE else f"⏸ Chờ duyệt: {GATE_NAMES.get(job.gate, job.gate)}"
    else:
        line = f"⏳ Đang: {STEP_NAMES.get(job.current_step, job.current_step)}"
    return f"🎬 {title}\n{line}"


class StatusNotifier:
    """PipelineRunner.on_change: keeps one message per job up to date. Only a change of text is sent;
    in the background a burst of changes collapses into the latest one, so nothing floods the chat."""

    def __init__(self, config: AppConfig, store, api_factory=TelegramApi, background: bool = True):
        self.config, self.store, self.api_factory, self.background = config, store, api_factory, background
        self._lock = threading.Lock()
        self._last: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        self._wake = threading.Event()
        self._api = None
        if background:
            threading.Thread(target=self._loop, name="telegram-status", daemon=True).start()

    def __call__(self, job: JobState) -> None:
        text = status_text(job)
        with self._lock:
            if self._last.get(job.id) == text:
                return
            self._last[job.id] = text
            self._pending[job.id] = text
        if self.background:
            self._wake.set()
        else:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for job_id, text in pending.items():
            try:
                self._deliver(job_id, text)
            except Exception:
                pass  # Telegram down: the next change tries again

    def _loop(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            self.flush()

    def _deliver(self, job_id: str, text: str) -> None:
        token = self.config.telegram.bot_token
        job = self.store.get(job_id)
        target = notify_target(job, self.config.telegram)
        if not token or not target:
            return
        self._api = self._api or self.api_factory(token)
        ref = job.status_message
        if ref:
            try:
                self._api.edit_text(ref.chat_id, ref.message_id, text)
                return
            except TelegramApiError as exc:
                if "not modified" in str(exc):
                    return
                # the message was deleted: start a new one below
        chat_id, reply_to = target
        message_id = self._api.send_message(chat_id, text, reply_to=reply_to)
        if message_id is None:
            return
        self.store.update(job_id, lambda j: setattr(j, "status_message", TelegramMessageRef(chat_id=chat_id,
                                                                                           message_id=message_id)))
