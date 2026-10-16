"""Thin client for the Telegram Bot API calls this tool uses."""

import json
from pathlib import Path

import httpx

POLL_TIMEOUT_SEC = 30
UPLOAD_TIMEOUT_SEC = 300
MAX_UPLOAD_BYTES = 50_000_000  # Bot API limit for files sent by bots


class TelegramApiError(Exception):
    """A failed call; the message never contains the bot token."""


class TelegramApi:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.http = client or httpx.Client(timeout=POLL_TIMEOUT_SEC + 15)

    def get_updates(self, offset: int, timeout: int = POLL_TIMEOUT_SEC) -> list[dict]:
        response = self.http.get(f"{self.base}/getUpdates", params={
            "offset": offset, "timeout": timeout, "allowed_updates": '["message", "callback_query"]'})
        response.raise_for_status()
        return response.json().get("result", [])

    def send_message(self, chat_id: int, text: str, reply_to: int | None = None) -> int | None:
        body = self._call("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True,
                                          **self._reply(reply_to)}, as_json=True)
        return (body.get("result") or {}).get("message_id")

    def edit_text(self, chat_id: int, message_id: int, text: str) -> None:
        self._call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text,
                                       "disable_web_page_preview": True}, as_json=True)

    def send_video(self, chat_id: int, path: Path, caption: str, reply_to: int | None = None,
                   width: int = 0, height: int = 0, duration: int = 0) -> None:
        data = {"chat_id": chat_id, "caption": caption[:1024], "supports_streaming": "true",
                "width": width, "height": height, "duration": duration, **self._reply(reply_to)}
        self._upload("sendVideo", "video", path, "video/mp4", data)

    def send_document(self, chat_id: int, path: Path, caption: str, reply_to: int | None = None) -> None:
        data = {"chat_id": chat_id, "caption": caption[:1024], **self._reply(reply_to)}
        self._upload("sendDocument", "document", path, "video/mp4", data)

    def send_photo(self, chat_id: int, path: Path, caption: str, reply_to: int | None = None,
                   reply_markup: dict | None = None) -> int:
        """Returns the message id, so the buttons under the photo can be edited later."""
        data = {"chat_id": chat_id, "caption": caption[:1024], **self._reply(reply_to)}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return self._upload("sendPhoto", "photo", path, mime, data)["result"]["message_id"]

    def edit_reply_markup(self, chat_id: int, message_id: int, reply_markup: dict) -> None:
        self._call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                              "reply_markup": reply_markup}, as_json=True)

    def edit_caption(self, chat_id: int, message_id: int, caption: str) -> None:
        """New caption; the buttons are dropped because no reply_markup is sent."""
        self._call("editMessageCaption", {"chat_id": chat_id, "message_id": message_id, "caption": caption[:1024]},
                   as_json=True)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        """Stops the spinner on the tapped button; `text` shows as a short toast."""
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]}, as_json=True)

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _reply(reply_to: int | None) -> dict:
        if not reply_to:
            return {}
        # Still send if the original message was deleted.
        return {"reply_parameters": json.dumps({"message_id": reply_to, "allow_sending_without_reply": True})}

    def _upload(self, method: str, field: str, path: Path, mime: str, data: dict) -> dict:
        with open(path, "rb") as fh:
            return self._call(method, {k: str(v) for k, v in data.items()}, files={field: (path.name, fh, mime)},
                       timeout=UPLOAD_TIMEOUT_SEC)

    def _call(self, method: str, data: dict, files: dict | None = None, as_json: bool = False,
              timeout: float | None = None) -> dict:
        try:
            if as_json:
                response = self.http.post(f"{self.base}/{method}", json=data, timeout=timeout or httpx.USE_CLIENT_DEFAULT)
            else:
                response = self.http.post(f"{self.base}/{method}", data=data, files=files,
                                          timeout=timeout or httpx.USE_CLIENT_DEFAULT)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramApiError(self.scrub(f"{method}: {exc}")) from exc
        if not body.get("ok"):
            raise TelegramApiError(self.scrub(f"{method}: {body.get('description', response.status_code)}"))
        return body

    def scrub(self, text: str) -> str:
        # httpx errors include the request URL, which contains the bot token: never show it.
        return text.replace(self.token, "***")[:300]
