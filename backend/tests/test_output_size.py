"""The output size is a setting: file names and messages follow video.long_edge (or the Flow size when
video.upscale is off) instead of saying "4K"."""

import pytest

from app.config import VideoConfig
from app.job_models import JobState, SourceInfo, TelegramOrigin
from app.steps import send_telegram_step
from app.steps.export_step import run_export

from .conftest import make_test_clip
from .test_send_telegram import FakeApi


@pytest.mark.parametrize("long_edge,label", [(3840, "4K"), (2560, "2K"), (1920, "1080p"), (1600, "1600p")])
def test_label(long_edge, label):
    assert VideoConfig(long_edge=long_edge).label == label


def test_export_name_says_2k60(make_context, make_config):
    ctx = make_context(config=make_config(video=VideoConfig(long_edge=2560)))
    ctx.path("final-4k60.mp4").write_bytes(b"video")
    run_export(ctx)
    assert ctx.job.export_path.endswith("_2k60.mp4")


def test_export_name_without_upscale_says_the_flow_size(make_context, make_config):
    ctx = make_context(config=make_config(video=VideoConfig(upscale=False, long_edge=2560)))
    make_test_clip(ctx.path("final-4k60.mp4"), width=720, height=1280, seconds=1)
    run_export(ctx)
    assert ctx.job.export_path.endswith("_720p60.mp4")


def test_telegram_names_the_real_size(make_context, make_config, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    api = FakeApi()
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: api)
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title="Giày"),
                   telegram=TelegramOrigin(chat_id=1, message_id=2, preview_sent=True))
    ctx = make_context(job=job, config=make_config(video=VideoConfig(long_edge=2560)))
    make_test_clip(ctx.path("final-4k60.mp4"), width=360, height=640, seconds=1)
    monkeypatch.setattr(send_telegram_step, "MAX_UPLOAD_BYTES", 10)  # too big: a note instead of the file
    send_telegram_step.run_send_telegram(ctx)
    note = api.calls[0][1]["text"]
    assert note.startswith("File 2K") and "4K" not in note


def test_telegram_without_upscale_names_the_flow_size(make_context, make_config, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    api = FakeApi()
    monkeypatch.setattr(send_telegram_step, "make_api", lambda token: api)
    job = JobState(id="t", name="giay", input_file="input.jpg", created_at="t", source=SourceInfo(url="u", title="Giày"),
                   telegram=TelegramOrigin(chat_id=1, message_id=2, preview_sent=True))
    ctx = make_context(job=job, config=make_config(video=VideoConfig(upscale=False, long_edge=2560)))
    make_test_clip(ctx.path("final-4k60.mp4"), width=1080, height=1920, seconds=1)
    monkeypatch.setattr(send_telegram_step, "MAX_UPLOAD_BYTES", 10)
    send_telegram_step.run_send_telegram(ctx)
    assert api.calls[0][1]["text"].startswith("File 1080p") and "2K" not in api.calls[0][1]["text"]
