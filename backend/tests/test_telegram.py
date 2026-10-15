"""Telegram: link extraction, sender allow-list, offset persistence, token redaction."""

import httpx
import pytest

from app.telegram.telegram_listener import TelegramListener
from app.telegram.telegram_messages import extract_tiktok_links, handle_message

ME = 111


def msg(text, user=ME):
    return {"message_id": 7, "text": text, "from": {"id": user}, "chat": {"id": user}}


def test_extract_links_from_share_text():
    text = ("Xem sản phẩm này trên TikTok Shop! https://vt.tiktok.com/ZSabc123/, "
            "và https://shop.tiktok.com/vn/pdp/1737628275640009880?_t=ZS-9A. Còn https://example.com/x thì bỏ.")
    assert extract_tiktok_links(text) == [
        "https://vt.tiktok.com/ZSabc123/",
        "https://shop.tiktok.com/vn/pdp/1737628275640009880?_t=ZS-9A",
    ]
    assert extract_tiktok_links("https://vt.tiktok.com/A/ https://vt.tiktok.com/A/") == ["https://vt.tiktok.com/A/"]


def test_strangers_get_their_id_only_on_start():
    created = []
    assert "222" in handle_message(msg("/start", user=222), {ME}, created.append)
    assert handle_message(msg("https://vt.tiktok.com/A/", user=222), {ME}, created.append) is None
    assert created == []


def test_allowed_user_links_create_jobs():
    seen = []

    def on_link(url):
        seen.append(url)
        return url.endswith("A/")  # second link is a duplicate

    reply = handle_message(msg("https://vt.tiktok.com/A/ https://vt.tiktok.com/B/"), {ME}, on_link)
    assert seen == ["https://vt.tiktok.com/A/", "https://vt.tiktok.com/B/"]
    assert "Đã nhận" in reply and "1 link đã có" in reply
    assert "Không thấy link" in handle_message(msg("chào"), {ME}, on_link)


class FakeApi:
    def __init__(self, batches):
        self.batches, self.offsets, self.sent = list(batches), [], []

    def get_updates(self, offset, timeout=30):
        self.offsets.append(offset)
        return self.batches.pop(0) if self.batches else []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_offset_survives_restart(tmp_path):
    offset_file = tmp_path / "offset"
    offset_file.write_text("0")
    updates = [{"update_id": 41, "message": msg("https://vt.tiktok.com/A/")}]
    api = FakeApi([updates])
    links = []
    TelegramListener(api, "tok", [ME], lambda u, c, m: links.append((u, c, m)) or True, offset_file).poll_once()
    assert links == [("https://vt.tiktok.com/A/", ME, 7)] and api.sent and offset_file.read_text() == "42"

    api2 = FakeApi([])
    TelegramListener(api2, "tok", [ME], lambda u, c, m: True, offset_file).poll_once()
    assert api2.offsets == [42]  # restart resumes after the processed update


def test_first_run_skips_backlog_instead_of_replaying(tmp_path):
    offset_file = tmp_path / "offset"
    links = []
    api = FakeApi([[{"update_id": 90, "message": msg("https://vt.tiktok.com/OLD/")}]])
    TelegramListener(api, "tok", [ME], lambda u, c, m: links.append((u, c, m)) or True, offset_file).poll_once()
    assert api.offsets == [-1] and offset_file.read_text() == "91" and links == []


def test_one_bad_update_does_not_block_the_rest(tmp_path):
    offset_file = tmp_path / "offset"
    offset_file.write_text("0")
    created = []

    def on_link(url, chat_id, message_id):
        if url.endswith("BAD/"):
            raise RuntimeError("disk full")
        created.append(url)
        return True

    class FlakySend(FakeApi):
        def send_message(self, chat_id, text):
            raise ConnectionError("telegram down")

    api = FlakySend([[{"update_id": 1, "message": msg("https://vt.tiktok.com/BAD/")},
                      {"update_id": 2, "message": msg("https://vt.tiktok.com/GOOD/")}]])
    listener = TelegramListener(api, "tok", [ME], on_link, offset_file)
    listener.poll_once()
    assert created == ["https://vt.tiktok.com/GOOD/"]  # processed despite the bad one and the failed reply
    assert offset_file.read_text() == "3"


def test_errors_never_expose_the_token(tmp_path, monkeypatch):
    token = "123:SECRET"
    listener = TelegramListener(FakeApi([]), token, [ME], lambda u, c, m: True, tmp_path / "o")
    listener._backoff_error(httpx.ConnectError(f"failed https://api.telegram.org/bot{token}/getUpdates"), 0)
    assert token not in listener.message and "***" in listener.message


def test_bad_token_stops_listener(tmp_path):
    request = httpx.Request("GET", "https://api.telegram.org/botX/getUpdates")
    error = httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))

    class Unauthorized(FakeApi):
        def get_updates(self, offset, timeout=30):
            raise error

    listener = TelegramListener(Unauthorized([]), "X", [ME], lambda u, c, m: True, tmp_path / "o")
    listener._loop()  # returns instead of retrying forever
    assert listener.state == "error" and "401" in listener.message


@pytest.mark.parametrize("text", ["/start", "/start@my_bot"])
def test_start_for_allowed_user(text):
    assert "Sẵn sàng" in handle_message(msg(text), {ME}, lambda u: True)
