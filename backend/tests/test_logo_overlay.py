"""Our logo over Flow's ✦ mark (bottom right). Measured on five 720×1280 Flow downloads on 2026-10-16:
the mark is 48×48 px at x 576–623, y 1136–1183."""

import subprocess

import pytest
from PIL import Image

from app.config import ROOT, LogoConfig, VideoConfig
from app.media.command_runner import RIFE_BIN
from app.media.ffmpeg_commands import encode_command, logo_box
from app.steps.enhance_video_step import run_enhance

from .conftest import make_test_clip

FLOW_MARK = (576, 1136, 624, 1184)  # left, top, right, bottom (exclusive) on 720×1280


@pytest.mark.parametrize("size,scale", [((720, 1280), 1), ((1440, 2560), 2), ((2160, 3840), 3)])
def test_default_logo_covers_the_flow_mark_at_every_output_size(size, scale):
    x, y, side = logo_box(LogoConfig(), size)
    left, top, right, bottom = (v * scale for v in FLOW_MARK)
    assert x <= left and y <= top and x + side >= right and y + side >= bottom
    assert side % 2 == 0 and side <= 1.4 * (right - left)  # covers it without swallowing the corner


def test_encode_overlays_the_logo_only_when_asked(tmp_path):
    logo = tmp_path / "logo.png"
    plain = encode_command(tmp_path, tmp_path / "a.mp4", True, 60, (1440, 2560), "24M", tmp_path / "o.mp4")
    assert "-filter_complex" not in plain

    with_audio = encode_command(tmp_path, tmp_path / "a.mp4", True, 60, (1440, 2560), "24M", tmp_path / "o.mp4",
                                logo=(logo, 1139, 2259, 120))
    graph = with_audio[with_audio.index("-filter_complex") + 1]
    assert "[2:v]scale=120:120" in graph and "overlay=1139:2259" in graph  # inputs: frames, audio, logo
    assert str(logo) in with_audio and with_audio[with_audio.index("-map") + 1] == "[v]"

    silent = encode_command(tmp_path, tmp_path / "a.mp4", False, 60, (1440, 2560), "24M", tmp_path / "o.mp4",
                            logo=(logo, 1139, 2259, 120))
    assert "[1:v]scale=120:120" in silent[silent.index("-filter_complex") + 1]


def test_logo_file_is_relative_to_the_project():
    assert LogoConfig(file="assets/logo.png").file == ROOT / "assets" / "logo.png"


@pytest.mark.skipif(not RIFE_BIN.exists(), reason="bin/rife missing")
def test_enhanced_video_carries_the_logo(make_context, make_config, tmp_path):
    png = tmp_path / "logo.png"  # a stand-in: the real logo is the user's own file and stays out of git
    Image.new("RGBA", (64, 64), (0, 0, 0, 255)).save(png)
    logo = LogoConfig(enabled=True, file=png)
    ctx = make_context(config=make_config(video=VideoConfig(long_edge=1280, min_free_gb=0.5), logo=logo))
    make_test_clip(ctx.path("flow-raw.mp4"), width=360, height=640, seconds=1)
    run_enhance(ctx)

    frame = ctx.path("frame.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ctx.path("final-4k60.mp4")), "-frames:v", "1", str(frame)],
                   check=True)
    with Image.open(frame) as img:
        x, y, side = logo_box(logo, img.size)
        # The stand-in logo is plain black; testsrc2 is bright and colourful there.
        r, g, b = img.convert("RGB").getpixel((x + int(side * 0.2), y + int(side * 0.7)))
    assert max(r, g, b) < 40
