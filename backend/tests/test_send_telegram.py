"""Sending the finished video back to Telegram: real clip, fake Bot API."""

import json

import httpx
import pytest

from app.job_models import JobState, ShopeeListing, SourceInfo, TelegramOrigin
from app.steps import send_telegram_step
from app.steps.send_telegram_step import run_send_telegram
from app.steps.step_types import StepFailure
from app.telegram.telegram_api import TelegramApi, TelegramApiError

from .conftest import make_test_clip

URL = "https://shop.tiktok.com/vn/pdp/1737628275640009880"


class FakeApi:
    def __init__(self, fail_on: str | None = None):
        self.calls, self.fail_on = [], fail_on

    def _record(self, kind, **kw):
        if kind == self.fail_on:
            raise TelegramApiError(f"{kind}: Bad Gateway")
        self.calls.append((kind, kw))

    def send_video(self, chat_id, path, caption, reply_to=None, **kw):
        assert path.exists() and path.stat().st_size > 0
        self._record("video", chat_id=chat_id, caption=caption, reply_to=reply_to, name=path.name, **kw)

    def send_document(self, chat_id, path, caption, reply_to=None):
        self._record("document", chat_id=chat_id, reply_to=reply_to, name=path.name)

    def send_message(self, chat_id, text, reply_to=None):
        self._record("message", chat_id=chat_id, text=text, reply_to=reply_to)


@pytest.fixture
def telegram_job(make_context, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    exported = tmp_path / "son-kem_20261015-1700_4k60.mp4"
    job = JobState(id="t", name="son-kem", input_file="input.jpg", created_at="t",
                   source=SourceInfo(url=URL, title="Son Kem Lì Velvet"), export_path=str(exported),
                   telegram=TelegramOrigin(chat_id=111, message_id=42))
    ctx = make_context(job=job)
    make_test_clip(ctx.path("final-4k60.mp4"), width=360, height=640, seconds=1)
    exported.write_bytes(ctx.path("final-4k60.mp4").read_bytes())
    api = FakeApi()
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: api)
    return ctx, api


def test_sends_the_exported_video_itself_then_bare_title_as_replies(telegram_job):
    ctx, api = telegram_job
    run_send_telegram(ctx)
    (kind1, video), (kind2, title) = api.calls
    assert kind1 == "video" and video["chat_id"] == 111 and video["reply_to"] == 42
    assert video["name"] == "son-kem_20261015-1700_4k60.mp4"  # the exported file, not a re-encoded copy
    assert video["width"] == 360 and video["height"] == 640
    assert video["caption"] == URL  # the link only
    assert kind2 == "message" and title["text"] == "Son Kem Lì Velvet" and title["reply_to"] == 42  # copy-ready
    assert ctx.job.telegram.preview_sent and ctx.job.telegram.file_sent and ctx.job.telegram.title_sent
    assert not ctx.path("preview-1080p.mp4").exists()


def test_shopee_link_is_one_short_tappable_line(telegram_job):
    ctx, api = telegram_job
    ctx.job.shopee = ShopeeListing(url="https://shopee.vn/product/1/2?a=1&b=2", shop="Xuka <shop>")
    run_send_telegram(ctx)
    video = api.calls[0][1]
    assert video["parse_mode"] == "HTML"
    assert video["caption"] == f'{URL}\n<a href="https://shopee.vn/product/1/2?a=1&amp;b=2">🛒 Shopee: Xuka &lt;shop&gt;</a>'


def test_an_unchecked_shopee_result_is_marked(telegram_job):
    ctx, api = telegram_job
    ctx.job.shopee = ShopeeListing(url="https://shopee.vn/product/1/2", checked=False)
    run_send_telegram(ctx)
    assert api.calls[0][1]["caption"].endswith('<a href="https://shopee.vn/product/1/2">🛒 Shopee ⚠️ chưa kiểm tra shop</a>')


def test_copy_message_is_claude_caption_then_hashtags(telegram_job):
    ctx, api = telegram_job
    ctx.job.caption, ctx.job.hashtags, ctx.job.hashtags_verified = "Son lì mà mềm môi 💄", ["#son", "#sonli"], True
    run_send_telegram(ctx)
    assert api.calls[-1][1]["text"] == "Son lì mà mềm môi 💄\n#son #sonli"  # not the shop's "Son Kem Lì Velvet"


def test_no_title_message_without_a_product_title(telegram_job):
    ctx, api = telegram_job
    ctx.job.source = None
    run_send_telegram(ctx)
    assert [kind for kind, _ in api.calls] == ["video"]


def test_big_file_is_replaced_by_a_note(telegram_job, monkeypatch):
    ctx, api = telegram_job
    monkeypatch.setattr(send_telegram_step, "MAX_UPLOAD_BYTES", 10)
    run_send_telegram(ctx)
    (kind, note), _title = api.calls  # no video: nothing is re-encoded to make it fit
    assert kind == "message" and "vượt giới hạn 50MB" in note["text"] and note["reply_to"] == 42


def test_job_whose_preview_already_went_out_still_gets_the_file(telegram_job):
    ctx, api = telegram_job
    ctx.job.telegram.preview_sent = True
    run_send_telegram(ctx)
    assert [kind for kind, _ in api.calls] == ["document", "message"]


def test_retry_after_failure_sends_only_what_is_missing(telegram_job, monkeypatch):
    ctx, api = telegram_job
    api.fail_on = "message"
    with pytest.raises(StepFailure, match="Thử lại"):
        run_send_telegram(ctx)
    assert ctx.job.telegram.preview_sent and ctx.job.telegram.file_sent and not ctx.job.telegram.title_sent

    api.fail_on = None
    api.calls.clear()
    run_send_telegram(ctx)
    assert [kind for kind, _ in api.calls] == ["message"]  # no second video

    api.calls.clear()
    run_send_telegram(ctx)
    assert api.calls == []  # everything delivered: a further retry sends nothing


def test_jobs_not_from_telegram_do_nothing(make_context, monkeypatch):
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: pytest.fail("must not call Telegram"))
    run_send_telegram(make_context())


def test_api_sends_reply_and_never_leaks_token(tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/sendDocument"):
            return httpx.Response(400, json={"ok": False, "description": "Request Entity Too Large"})
        return httpx.Response(200, json={"ok": True, "result": {}})

    token = "999:SECRET"
    api = TelegramApi(token, httpx.Client(transport=httpx.MockTransport(handler)))
    clip = tmp_path / "v.mp4"
    clip.write_bytes(b"video")
    api.send_message(5, "hi", reply_to=9)
    assert json.loads(json.loads(seen[0].content)["reply_parameters"])["message_id"] == 9
    api.send_video(5, clip, "cap", reply_to=9)
    assert b'name="reply_parameters"' in seen[1].content and b'name="video"; filename="v.mp4"' in seen[1].content
    assert b'name="parse_mode"' not in seen[1].content  # plain text unless asked
    api.send_video(5, clip, "<b>cap</b>", parse_mode="HTML")
    assert b'name="parse_mode"\r\n\r\nHTML' in seen[2].content
    with pytest.raises(TelegramApiError) as err:
        api.send_document(5, clip, "cap")
    assert "Too Large" in str(err.value) and token not in str(err.value)
