"""Start the Telegram listener from config and report its status to the UI."""

from ..config import AppConfig
from ..job_models import TelegramOrigin
from ..link_job_actions import LinkJobActions
from .telegram_api import TelegramApi
from .telegram_listener import TelegramListener
from .telegram_pick import PickHandler
from .telegram_post import PostHandler

OFFSET_FILE = ".telegram-offset"


def route_taps(pick, post):
    """Photo picker buttons carry "p:"/"g:", the post buttons "t:"."""
    def handle(callback: dict) -> str | None:
        return (post if (callback.get("data") or "").startswith("t:") else pick).handle(callback)

    return handle


def start_telegram(config: AppConfig, actions: LinkJobActions) -> TelegramListener | None:
    tg = config.telegram
    if not tg.enabled or not tg.bot_token:
        return None
    api = TelegramApi(tg.bot_token)
    listener = TelegramListener(
        api, tg.bot_token, tg.user_ids,
        on_link=lambda url, chat_id, message_id: actions.create_from_link(
            url, TelegramOrigin(chat_id=chat_id, message_id=message_id)) is not None,
        offset_file=config.paths.jobs_dir / OFFSET_FILE,
        on_callback=route_taps(PickHandler(actions, api, config), PostHandler(actions, api)),
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
