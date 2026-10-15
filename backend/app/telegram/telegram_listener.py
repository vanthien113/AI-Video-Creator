"""Long-poll the Telegram Bot API in a background thread (no public URL or open port needed)."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

import httpx

from .telegram_api import TelegramApi
from .telegram_messages import handle_message

logging.getLogger("httpx").setLevel(logging.WARNING)  # INFO logs would print the URL with the token


class TelegramListener:
    def __init__(self, api: TelegramApi, token: str, allowed_ids: list[int],
                 on_link: Callable[[str, int, int], bool], offset_file: Path):
        """`on_link(url, chat_id, message_id)` queues a job; False means the link was a duplicate."""
        self.api, self.token, self.allowed = api, token, set(allowed_ids)
        self.on_link, self.offset_file = on_link, offset_file
        self.state, self.message = "starting", ""
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="telegram-listener", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {"state": self.state, "message": self.message}

    # ---- polling ----------------------------------------------------------
    def _read_offset(self) -> int | None:
        try:
            return int(self.offset_file.read_text().strip())
        except (OSError, ValueError):
            return None

    def _skip_backlog(self) -> None:
        """First run: Telegram keeps up to 24h of messages; start fresh instead of replaying them."""
        latest = self.api.get_updates(-1, timeout=0)
        self.offset_file.write_text(str(latest[-1]["update_id"] + 1 if latest else 0))

    def poll_once(self) -> None:
        offset = self._read_offset()
        if offset is None:
            self._skip_backlog()
            return
        for update in self.api.get_updates(offset):
            try:
                self._handle(update)
            except Exception as exc:  # one bad update must never block the ones after it
                self.message = self._scrub(f"Bỏ qua 1 tin lỗi: {exc}")
            finally:
                # Persist after each update so a restart never processes a link twice.
                self.offset_file.write_text(str(update["update_id"] + 1))

    def _handle(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return
        chat_id, message_id = message["chat"]["id"], message.get("message_id")
        reply = handle_message(message, self.allowed, lambda url: self.on_link(url, chat_id, message_id))
        if reply:
            try:
                self.api.send_message(chat_id, reply)
            except Exception:
                pass  # the link is already queued; a lost "Đã nhận" is harmless

    def _loop(self) -> None:
        backoff = 1
        while not self._stop.is_set():
            try:
                self.poll_once()
                self.state, self.message, backoff = "listening", "", 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    self.state, self.message = "error", "Token bot Telegram sai (401). Kiểm tra TELEGRAM_BOT_TOKEN trong .env."
                    return
                self._backoff_error(exc, backoff)
                backoff = min(backoff * 2, 60)
            except Exception as exc:  # network blips: keep retrying with backoff
                self._backoff_error(exc, backoff)
                backoff = min(backoff * 2, 60)

    def _scrub(self, text: str) -> str:
        # httpx errors include the request URL, which contains the bot token: never show it.
        return text.replace(self.token, "***")[:300]

    def _backoff_error(self, exc: Exception, delay: float) -> None:
        self.state, self.message = "error", self._scrub(str(exc))
        self._stop.wait(delay)  # returns early when the app shuts down
