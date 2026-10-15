"""Real-tool integration tests: Real-ESRGAN/rembg on an image, RIFE + ffmpeg on a clip."""

import json

import pytest
from PIL import Image, ImageDraw

from app.config import ImageConfig, VideoConfig
from app.media.command_runner import REALESRGAN_BIN, RIFE_BIN
from app.media.video_probe import probe_video
from app.steps.enhance_video_step import run_enhance
from app.steps.upscale_step import run_upscale

from .conftest import make_test_clip

needs_rife = pytest.mark.skipif(not RIFE_BIN.exists(), reason="bin/rife missing")
needs_esrgan = pytest.mark.skipif(not REALESRGAN_BIN.exists(), reason="bin/realesrgan missing")


@needs_rife
@pytest.mark.parametrize("width,height,expected", [(640, 360, (3840, 2160)), (360, 640, (2160, 3840))])
def test_enhance_makes_4k60_with_audio(make_context, make_config, width, height, expected):
    ctx = make_context(config=make_config(video=VideoConfig(min_free_gb=0.5)))
    make_test_clip(ctx.path("flow-raw.mp4"), width=width, height=height)

    run_enhance(ctx)

    info = probe_video(ctx.path("final-4k60.mp4"))
    assert (info.width, info.height) == expected
    assert round(info.fps) == 60
    assert info.has_audio
    assert abs(info.duration - 2) < 0.2
    assert not ctx.path("tmp").exists()


@needs_esrgan
@pytest.mark.parametrize("background", ["white", "transparent"])
def test_upscale_fits_long_edge_and_background(make_context, make_config, background):
    ctx = make_context(config=make_config(image=ImageConfig(long_edge=1024, background=background)))
    img = Image.new("RGB", (300, 200), (30, 120, 200))
    ImageDraw.Draw(img).ellipse((100, 50, 200, 150), fill=(250, 200, 10))
    img.save(ctx.path("input.png"))
    mask = Image.new("L", (300, 200), 0)
    ImageDraw.Draw(mask).ellipse((100, 50, 200, 150), fill=255)
    mask.save(ctx.path("mask.png"))
    ctx.path("crop.json").write_text(json.dumps({"box": [90, 40, 210, 160]}))

    run_upscale(ctx)

    with Image.open(ctx.path("product-2k.png")) as out:
        assert max(out.size) == 1024
        assert out.mode == ("RGBA" if background == "transparent" else "RGB")
        corner = out.getpixel((2, 2))
        assert corner == ((255, 255, 255) if background == "white" else corner[:3] + (0,))
