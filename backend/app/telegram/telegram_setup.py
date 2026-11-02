"""Start the Telegram listener from config and report its status to the UI."""

import time

from ..config import AppConfig
from ..job_models import TelegramMessageRef, TelegramOrigin
from ..link_job_actions import LinkJobActions
from .telegram_api import TelegramApi, TelegramApiError
from .telegram_listener import TelegramListener
from .telegram_pick import PickHandler
from .telegram_post import PostHandler

OFFSET_FILE = ".telegram-offset"
NEW_TOPIC_NAME = "⏳ Link TikTok mới"  # renamed to the product as soon as the job reads it
COPY_WAIT_SEC = 1.0


def open_topic(api, chat_id: int) -> int | None:
    """A topic of its own for a new link; the job's status message becomes its first message. None when the
    bot has topics off (enabled in @BotFather): the job then replies under the link message as before."""
    try:
        return api.create_forum_topic(chat_id, NEW_TOPIC_NAME)
    except TelegramApiError:
        return None


def link_handler(actions: LinkJobActions, api, topics: bool = True):
    """The listener's on_link: False for a link already queued (no empty topic for it)."""
    def on_link(url: str, chat_id: int, message_id: int) -> bool:
        if actions.open_link_job(url):
            return False
        thread_id = open_topic(api, chat_id) if topics else None
        origin = TelegramOrigin(chat_id=chat_id, message_id=message_id, thread_id=thread_id)
        return actions.create_from_link(url, origin) is not None

    return on_link


def channel_copy_handler(store, channel_id: int):
    """The listener's on_channel_copy: Telegram copies each post of the channel into its discussion group, and
    replies to that copy are the post's comments. A bot cannot look the copy up, so it is caught as it arrives."""
    def attach(post_id: int, comments: TelegramMessageRef) -> bool:
        for job in store.list():
            post = job.status_message
            if job.telegram and post and (post.chat_id, post.message_id) == (channel_id, post_id):
                store.update(job.id, lambda j: setattr(j.telegram, "comments", comments))
                return True
        return False

    def on_copy(from_channel: int, post_id: int, chat_id: int, message_id: int) -> None:
        if from_channel != channel_id:
            return
        comments = TelegramMessageRef(chat_id=chat_id, message_id=message_id)
        deadline = time.monotonic() + COPY_WAIT_SEC
        # The copy can come in a moment before the status notifier has saved the post's id.
        while not attach(post_id, comments) and time.monotonic() < deadline:
            time.sleep(0.1)

    return on_copy


def route_taps(pick, post):
    """Photo picker buttons carry "p:"/"g:", the post buttons "t:"."""
    def handle(callback: dict) -> str | None:
        return (post if (callback.get("data") or "").startswith("t:") else pick).handle(callback)

    return handle


def start_telegram(config: AppConfig, actions: LinkJobActions) -> TelegramListener | None:
    tg = config.telegram
    if not tg.enabled or not tg.bot_token:
        return None
    api, channel = TelegramApi(tg.bot_token), tg.channel_id
    listener = TelegramListener(
        api, tg.bot_token, tg.user_ids,
        on_link=link_handler(actions, api, topics=not channel),
        offset_file=config.paths.jobs_dir / OFFSET_FILE,
        on_callback=route_taps(PickHandler(actions, api, config), PostHandler(actions, api)),
        on_channel_copy=channel_copy_handler(actions.store, channel) if channel else None,
        private_only=bool(channel),  # links come from the private chat; the group holds the comments
    )
    listener.start()
    return listener


def telegram_status(config: AppConfig, listener: TelegramListener | None) -> dict:
    tg = config.telegram
    if not tg.enabled:
        return {"state": "off", "message": "Telegram đang tắt trong config.yaml."}
    if not tg.bot_token:
        return {"state": "no_token", "message": "Chưa có TELEGRAM_BOT_TOKEN trong file .env."}
    status = listener.status() if listener else {"state": "starting", "message": ""}
    if status["state"] == "listening" and not tg.user_ids:
        return {"state": "no_user", "message": "Nhắn /start cho bot để lấy ID, rồi điền vào TELEGRAM_ALLOWED_USER_IDS trong file .env."}
    return status
