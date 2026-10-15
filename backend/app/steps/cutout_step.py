"""Step 1: find the product with rembg and crop it out (cutout.png for review)."""

import json
import threading

from PIL import Image

from ..media.image_io import compose, load_rgb, padded_box
from .step_types import JobContext, StepFailure

MIN_PRODUCT_AREA = 0.02
_sessions: dict = {}
_session_lock = threading.Lock()


def _session(model: str):
    with _session_lock:
        if model not in _sessions:
            from rembg import new_session  # heavy import, only when the step runs

            _sessions[model] = new_session(model)
        return _sessions[model]


def run_cutout(ctx: JobContext) -> None:
    cfg = ctx.config.image
    models = cfg.cutout_models
    model = models[ctx.job.cutout_model_index % len(models)]
    ctx.report(0.05, f"Đọc ảnh, tải mô hình {model}")
    img = load_rgb(ctx.path(ctx.job.input_file))

    from rembg import remove

    ctx.report(0.3, f"Tách nền bằng {model}")
    mask = remove(img, session=_session(model), only_mask=True).convert("L")
    solid = mask.point(lambda v: 255 if v > 16 else 0)
    bbox = solid.getbbox()
    if bbox is None:
        raise StepFailure("Không tìm thấy sản phẩm trong ảnh. Thử mô hình khác hoặc thay ảnh.")
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (img.width * img.height)
    if area < MIN_PRODUCT_AREA:
        raise StepFailure("Vùng sản phẩm quá nhỏ (dưới 2% ảnh). Thử mô hình khác hoặc thay ảnh.")

    box = padded_box(bbox, cfg.padding)
    mask.save(ctx.path("mask.png"))
    ctx.path("crop.json").write_text(json.dumps({"box": box, "model": model}), encoding="utf-8")

    # crop() beyond the image fills with black RGB and 0 mask, so padding becomes background.
    cutout = compose(img.crop(box), mask.crop(box), cfg.background)
    cutout.save(ctx.path("cutout.png"))
    ctx.log(f"cutout: model={model} bbox={bbox} box={box}")
    ctx.report(1, "Xong")


def load_crop(ctx: JobContext) -> tuple[Image.Image, Image.Image]:
    """Return (rgb_crop, mask_crop) produced by the cutout step."""
    crop_file = ctx.path("crop.json")
    if not crop_file.exists():
        raise StepFailure("Thiếu kết quả tách nền, chạy lại bước tách nền.")
    box = tuple(json.loads(crop_file.read_text(encoding="utf-8"))["box"])
    img = load_rgb(ctx.path(ctx.job.input_file))
    with Image.open(ctx.path("mask.png")) as mask:
        return img.crop(box), mask.convert("L").crop(box)
