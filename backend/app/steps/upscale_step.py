"""Step 2: upscale the cropped product with Real-ESRGAN and fit the long edge to 2K."""

import shutil

from PIL import Image

from ..media.command_runner import REALESRGAN_BIN, REALESRGAN_MODELS, require_tool, run_tool
from ..media.image_io import compose
from .cutout_step import load_crop
from .step_types import JobContext

MODEL = "realesrgan-x4plus"


def fit_long_edge(size: tuple[int, int], long_edge: int) -> tuple[int, int]:
    width, height = size
    scale = long_edge / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def run_upscale(ctx: JobContext) -> None:
    target = ctx.config.image.long_edge
    rgb, mask = load_crop(ctx)
    ctx.report(0.05, "Chuẩn bị upscale")

    if max(rgb.size) < target:
        binary = require_tool(REALESRGAN_BIN)
        work = ctx.path("tmp-upscale")
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()
        src, dst = work / "in.png", work / "out.png"
        rgb.save(src)
        ctx.report(0.2, f"Real-ESRGAN x4 ({rgb.width}×{rgb.height})")
        run_tool(
            [binary, "-i", str(src), "-o", str(dst), "-n", MODEL, "-s", "4", "-m", str(REALESRGAN_MODELS)],
            timeout=900, should_stop=ctx.is_cancelled, label="Real-ESRGAN",
        )
        with Image.open(dst) as up:
            rgb = up.convert("RGB")
        shutil.rmtree(work, ignore_errors=True)
    else:
        ctx.log(f"upscale: crop {rgb.size} already ≥ {target}px, resize only")

    ctx.report(0.85, f"Chỉnh cạnh dài về {target}px")
    size = fit_long_edge(rgb.size, target)
    rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    mask = mask.resize(size, Image.Resampling.LANCZOS)
    compose(rgb, mask, ctx.config.image.background).save(ctx.path("product-2k.png"))
    ctx.log(f"upscale: product-2k.png {size}")
    ctx.report(1, "Xong")
