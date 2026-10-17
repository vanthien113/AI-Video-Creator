"""Đăng ngay / Lên lịch on Telegram: a message of its own with two buttons, sent once the job is about to be
done, then edited as the post moves on. Button data is "t:<token>:n" (now) or "t:<token>:s" (schedule),
under Telegram's 64 bytes."""

import secrets
from collections.abc import Callable
from datetime import datetime

from ..job_actions import InvalidAction
from ..job_models import JobState, TelegramMessageRef
from ..tiktok.post_plan import job_product_id, post_title, slot_label
from .telegram_api import TelegramApiError

MODES = {"n": "now", "s": "schedule"}
MODE_NAMES = {"now": "Đăng ngay", "schedule": "Lên lịch"}
OFFER_TEXT = "📤 Đăng video này lên TikTok?"
FAILED_TEXT = "❌ Đăng lỗi, mở AI Video Creator để thử lại."
STALE_TEXT = "Nút này đã cũ, dùng tin mới nhất hoặc nút trên tool."


def keyboard(token: str) -> dict:
    return {"inline_keyboard": [[{"text": "📤 Đăng ngay", "callback_data": f"t:{token}:n"},
                                 {"text": "🗓 Lên lịch", "callback_data": f"t:{token}:s"}]]}


def parse(data: str) -> tuple[str, str] | None:
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[0] == "t" and parts[1] and parts[2] in MODES:
        return parts[1], MODES[parts[2]]
    return None


def waiting_text(mode: str) -> str:
    return f"⏳ Đã nhận: {MODE_NAMES[mode]}. Đang chờ lượt…"


def done_text(job: JobState) -> str:
    """The button message once TikTok has the post."""
    post = job.post
    if post.mode == "schedule" and post.scheduled_for:
        return f"🗓 Đã lên lịch đăng TikTok: {slot_label(datetime.fromisoformat(post.scheduled_for))}"
    return f"✅ Đã đăng lên TikTok lúc {datetime.fromisoformat(post.done_at):%H:%M}"


def result_message(job: JobState) -> str:
    """The new message under the link."""
    post = job.post
    if post.mode == "schedule" and post.scheduled_for:
        when = slot_label(datetime.fromisoformat(post.scheduled_for))
        return f"🗓 Đã lên lịch đăng TikTok lúc {when}: {post_title(job)}"
    return f"✅ Đã đăng lên TikTok: {post_title(job)}"


def state_text(job: JobState) -> str:
    """The button message for a job already asked to post, from either side."""
    return done_text(job) if job.post.done_at else waiting_text(job.post.mode)


def send_offer(job: JobState, api, update_job: Callable) -> JobState:
    """Bot jobs with a product ID get the two buttons under their link message, once."""
    origin = job.telegram
    if not origin or job.post.offer_message or job.post.mode or not job_product_id(job):
        return job
    token = secrets.token_hex(4)
    message_id = api.send_message(origin.chat_id, OFFER_TEXT, reply_to=origin.message_id, reply_markup=keyboard(token))

    def remember(j: JobState) -> None:
        j.post.offer_token = token
        if message_id:
            j.post.offer_message = TelegramMessageRef(chat_id=origin.chat_id, message_id=message_id)

    return update_job(remember)


def edit_offer(job: JobState, api, text: str) -> None:
    """New text, no buttons (editMessageText without reply_markup drops them). Best effort."""
    ref = job.post.offer_message
    if not ref:
        return
    try:
        api.edit_text(ref.chat_id, ref.message_id, text)
    except TelegramApiError:
        pass  # deleted message or "not modified": the post itself is what matters


class PostHandler:
    """Turns a tap on Đăng ngay / Lên lịch into request_post; returns the toast text."""

    def __init__(self, actions, api):
        self.actions, self.api = actions, api

    def handle(self, callback: dict) -> str:
        parsed = parse(callback.get("data", ""))
        message = callback.get("message") or {}
        chat_id, message_id = (message.get("chat") or {}).get("id"), message.get("message_id")
        if not parsed or chat_id is None:
            return ""
        token, mode = parsed
        job = next((j for j in self.actions.store.list() if j.post.offer_token == token), None)
        if job is None:
            self._edit(chat_id, message_id, STALE_TEXT)
            return STALE_TEXT
        try:
            self.actions.request_post(job.id, mode)
        except InvalidAction as exc:
            if job.post.mode:  # already asked here or in the tool: show where it stands, drop the buttons
                self._edit(chat_id, message_id, state_text(job))
            return str(exc)[:190]
        self._edit(chat_id, message_id, waiting_text(mode))
        return f"{MODE_NAMES[mode]}!"

    def _edit(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self.api.edit_text(chat_id, message_id, text)
        except TelegramApiError:
            pass
