"""Telegram notices outside the normal replies: where to send them, the "a job failed" notice, and the one
status message per job that is edited as the job moves between steps."""

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..config import AppConfig, TelegramConfig
from ..job_models import PICK_GATE, JobState, JobStatus, TelegramMessageRef
from ..tiktok.post_plan import slot_label
from .telegram_api import TelegramApi, TelegramApiError

STEP_NAMES = {
    "fetch_source": "Đọc TikTok", "cutout": "Tách nền", "upscale": "Upscale", "prompt": "Prompt",
    "flow_generate": "Flow sinh", "flow_download": "Tải video", "enhance": "Nâng 60fps", "export": "Xuất file", "hashtags": "Hashtag", "shopee": "Tìm Shopee",
    "send_telegram": "Gửi Telegram", "tiktok_draft": "Lưu nháp TikTok", "tiktok_post": "Đăng TikTok",
}


GATE_NAMES = {"cutout": "Ảnh tách nền", "prompt": "Prompt", "flow_video": "Video Flow"}
TOPIC_TITLE_MAX = 100


def notify_target(job: JobState, telegram: TelegramConfig) -> tuple[int, dict] | None:
    """(chat id, send kwargs): a bot job's topic or link message; otherwise the first allowed user."""
    if job.telegram:
        return job.telegram.target()
    return (telegram.user_ids[0], {}) if telegram.user_ids else None


def job_title(job: JobState) -> str:
    return (job.source.title if job.source else "") or job.name


def failure_text(job: JobState) -> str:
    step = STEP_NAMES.get(job.error.step, job.error.step)
    return (f"❌ Lỗi ở bước {step}: {job.error.reason}\n📦 {job_title(job)}\n"
            "Mở AI Video Creator để xem chi tiết, sửa rồi bấm Thử lại.")


def send_failure(telegram: TelegramConfig, job: JobState, job_dir: Path, api) -> None:
    target = notify_target(job, telegram)
    if not target or not job.error:
        return
    chat_id, place = target
    shot = job_dir / job.error.screenshot if job.error.screenshot else None
    if shot and shot.exists():
        api.send_photo(chat_id, shot, failure_text(job), **place)
    else:
        api.send_message(chat_id, failure_text(job), **place)


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
    # The link above the title: in a topic or a channel post the user's own link message is out of sight.
    link = f"🔗 {job.source.url}\n" if job.source and job.source.url else ""
    return f"{link}🎬 {job_title(job)}\n{status_line(job)}"


def topic_name(job: JobState) -> str:
    """The topic list mirrors the status message: its icon, then the product (topic names max 128)."""
    title = job_title(job)
    if len(title) > TOPIC_TITLE_MAX:
        title = title[:TOPIC_TITLE_MAX - 1] + "…"
    return f"{status_line(job).split(' ', 1)[0]} {title}"


def status_line(job: JobState) -> str:
    if job.status == JobStatus.done:
        line = _posted(job) or "✅ Xong"
    elif job.status == JobStatus.failed:
        line = f"❌ Lỗi ở bước {STEP_NAMES.get(job.error.step, job.error.step) if job.error else ''}".rstrip()
    elif job.status == JobStatus.cancelled:
        line = "⏹ Đã huỷ"
    elif job.status == JobStatus.awaiting_review:
        line = "🖼 Chờ chọn ảnh" if job.gate == PICK_GATE else f"⏸ Chờ duyệt: {GATE_NAMES.get(job.gate, job.gate)}"
    elif job.current_step == "tiktok_post" and not job.post.mode:
        line = "✅ Xong"  # nobody pressed a post button: the step has nothing to do
    elif job.current_step == "tiktok_post" and job.post.mode == "schedule":
        line = "⏳ Đang: Lên lịch TikTok"
    else:
        line = f"⏳ Đang: {STEP_NAMES.get(job.current_step, job.current_step)}"
    return line


def _posted(job: JobState) -> str:
    post = job.post
    if not post.done_at:
        return ""
    if post.mode == "schedule" and post.scheduled_for:
        return f"🗓 Đã lên lịch TikTok {slot_label(datetime.fromisoformat(post.scheduled_for), weekday=False)}"
    return "✅ Đã đăng TikTok"


class StatusNotifier:
    """PipelineRunner.on_change: keeps one message per job up to date. Only a change of text is sent;
    in the background a burst of changes collapses into the latest one, so nothing floods the chat."""

    def __init__(self, config: AppConfig, store, api_factory=TelegramApi, background: bool = True):
        self.config, self.store, self.api_factory, self.background = config, store, api_factory, background
        self._lock = threading.Lock()
        self._last: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        self._topics: dict[str, str] = {}  # topic name last set per job
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
        target = self._status_target(job)
        if not token or not target:
            return
        self._api = self._api or self.api_factory(token)
        self._send_status(job, target, text)
        self._rename_topic(job)

    def _status_target(self, job: JobState) -> tuple[int, dict] | None:
        channel = self.config.telegram.channel_id
        if channel and job.telegram:
            return channel, {}  # the job's post: the listener links it to its comments
        return notify_target(job, self.config.telegram)

    def _send_status(self, job: JobState, target: tuple[int, dict], text: str) -> None:
        ref = job.status_message
        if ref:
            try:
                self._api.edit_text(ref.chat_id, ref.message_id, text)
                return
            except TelegramApiError as exc:
                if "not found" not in str(exc):
                    return  # "not modified", or a network blip: no second post; the next change edits again
                # the message was deleted: start a new one below
        chat_id, place = target
        message_id = self._api.send_message(chat_id, text, **place)
        if message_id is None:
            return
        self.store.update(job.id, lambda j: setattr(j, "status_message", TelegramMessageRef(chat_id=chat_id,
                                                                                           message_id=message_id)))

    def _rename_topic(self, job: JobState) -> None:
        origin, name = job.telegram, topic_name(job)
        if not origin or not origin.thread_id or self._topics.get(job.id) == name:
            return
        try:
            self._api.edit_forum_topic(origin.chat_id, origin.thread_id, name)
        except TelegramApiError as exc:
            if "modified" not in str(exc).lower():  # TOPIC_NOT_MODIFIED: already this name
                return  # the next change tries again
        self._topics[job.id] = name
