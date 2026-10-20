"""Step 7: copy the final video into the export folder with a readable, unique name (none set: nothing to do)."""

import shutil
from datetime import datetime
from pathlib import Path

from .enhance_video_step import output_label
from .step_types import JobContext, StepFailure


def unique_path(folder: Path, base: str, suffix: str) -> Path:
    candidate, n = folder / f"{base}{suffix}", 2
    while candidate.exists():
        candidate, n = folder / f"{base}-{n}{suffix}", n + 1
    return candidate


def run_export(ctx: JobContext) -> None:
    src = ctx.path("final-4k60.mp4")
    if not src.exists():
        raise StepFailure("Thiếu final-4k60.mp4, chạy lại bước nâng cấp video.")
    folder = ctx.config.paths.export_dir
    if folder is None:  # the job folder's own copy is the video
        ctx.log(f"export: không chép ra ngoài, video nằm ở {src}")
        ctx.report(1, "Xong")
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        video = ctx.config.video
        size_name = output_label(video, src).lower()
        dest = unique_path(folder, f"{ctx.job.name}_{datetime.now():%Y%m%d-%H%M}_{size_name}{video.fps}", ".mp4")
        shutil.copy2(src, dest)
    except OSError as exc:
        raise StepFailure(f"Không ghi được vào thư mục xuất {folder}: {exc}") from exc
    ctx.update_job(lambda j: setattr(j, "export_path", str(dest)))
    ctx.log(f"export: {dest}")
    ctx.report(1, "Xong")
