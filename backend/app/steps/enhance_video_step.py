"""Step 6: RIFE frame interpolation to 60fps, then lanczos upscale to video.long_edge with HEVC encoding."""

import shutil

from ..media.command_runner import RIFE_BIN, RIFE_MODELS_DIR, require_tool, run_tool
from ..media.ffmpeg_commands import (
    encode_command, extract_frames_command, rife_command, target_frame_count, target_size,
)
from ..media.video_probe import probe_video
from .step_types import JobContext, StepFailure

# Share of the progress bar given to each phase.
EXTRACT, INTERPOLATE, ENCODE = 0.1, 0.6, 0.3


def run_enhance(ctx: JobContext) -> None:
    cfg = ctx.config.video
    src, out = ctx.path("flow-raw.mp4"), ctx.path("final-4k60.mp4")
    if not src.exists():
        raise StepFailure("Thiếu flow-raw.mp4, chạy lại bước tải video.")
    free_gb = shutil.disk_usage(ctx.job_dir).free / 1024**3
    if free_gb < cfg.min_free_gb:
        raise StepFailure(f"Ổ đĩa chỉ còn {free_gb:.1f}GB, cần ít nhất {cfg.min_free_gb}GB.")
    try:
        info = probe_video(src)
    except ValueError as exc:
        raise StepFailure(f"Không đọc được flow-raw.mp4: {exc}") from exc

    rife = require_tool(RIFE_BIN)
    model_dir = RIFE_MODELS_DIR / cfg.rife_model
    if not model_dir.is_dir():
        raise StepFailure(f"Thiếu mô hình RIFE {cfg.rife_model} trong bin/rife.")
    frame_count = target_frame_count(info.duration, cfg.fps)
    size = target_size(info.width, info.height, cfg.long_edge)
    ctx.log(f"enhance: {info} → {frame_count} frames @ {cfg.fps}fps, {size}")

    tmp = ctx.path("tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    frames_in, frames_out = tmp / "in", tmp / "out"
    frames_in.mkdir(parents=True)
    frames_out.mkdir()
    try:
        ctx.report(0.02, "Tách khung hình")
        run_tool(extract_frames_command(src, frames_in), timeout=600, label="ffmpeg (tách khung)")

        def rife_progress() -> None:
            done = sum(1 for _ in frames_out.iterdir())
            ctx.report(EXTRACT + INTERPOLATE * done / frame_count, f"RIFE nội suy {done}/{frame_count} khung")

        run_tool(rife_command(rife, model_dir, frames_in, frames_out, frame_count),
                 timeout=3600, poll=rife_progress, should_stop=ctx.is_cancelled, label="RIFE")

        produced = sum(1 for _ in frames_out.iterdir())
        if produced == 0:
            raise StepFailure("RIFE không tạo ra khung hình nào.")

        def encode_progress(line: str) -> None:
            value = line.split("=", 1)[1] if line.startswith("frame=") else ""
            if value.isdigit():
                done = int(value)
                ctx.report(EXTRACT + INTERPOLATE + ENCODE * done / produced,
                           f"Mã hoá {size[0]}×{size[1]} {done}/{produced}")

        run_tool(encode_command(frames_out, src, info.has_audio, cfg.fps, size, cfg.bitrate, out),
                 timeout=3600, on_line=encode_progress, should_stop=ctx.is_cancelled, label=f"ffmpeg (mã hoá {cfg.label})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    result = probe_video(out)
    ctx.log(f"enhance: final {result}")
    ctx.report(1, "Xong")
