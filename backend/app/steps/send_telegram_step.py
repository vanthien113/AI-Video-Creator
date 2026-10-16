"""Reply in Telegram with a 1080p preview, the full-size file (video.long_edge) if small enough, then the bare
product title (a message of its own, so it is easy to copy).

Only jobs that came from Telegram do anything here. Each part is marked as sent once delivered,
so "Thử lại" after a network error never posts the same video twice.
"""

from pathlib import Path

from ..job_models import JobState
from ..media.command_runner import require_tool, run_tool
from ..media.ffmpeg_commands import preview_command, target_size
from ..media.video_probe import probe_video
from ..telegram.telegram_api import MAX_UPLOAD_BYTES, TelegramApi, TelegramApiError
from .step_types import JobContext, StepFailure

PREVIEW_LONG_EDGE = 1920


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


def build_caption(job: JobState) -> str:
    title = (job.source.title if job.source else "") or job.name
    lines = [f"✅ Video xong: {title}"]
    if job.source:
        lines.append(f"🔗 {job.source.url}")
    if job.export_path:
        lines.append(f"📁 {Path(job.export_path).name}")
    return "\n".join(lines)


def run_send_telegram(ctx: JobContext) -> None:
    origin = ctx.job.telegram
    if origin is None:
        return  # job was not created from Telegram
    token = ctx.config.telegram.bot_token
    if not token:
        raise StepFailure("Chưa có TELEGRAM_BOT_TOKEN nên không gửi được video về Telegram.")
    final = ctx.path("final-4k60.mp4")
    if not final.exists():
        raise StepFailure("Thiếu final-4k60.mp4, chạy lại bước nâng cấp video.")
    api = make_api(token)

    try:
        if not origin.preview_sent:
            ctx.report(0.1, "Tạo bản xem trước 1080p")
            preview = ctx.path("preview-1080p.mp4")
            info = probe_video(final)
            size = target_size(info.width, info.height, PREVIEW_LONG_EDGE)
            require_tool("ffmpeg")
            run_tool(preview_command(final, preview, size), timeout=600, should_stop=ctx.is_cancelled,
                     label="ffmpeg (bản 1080p)")
            if preview.stat().st_size > MAX_UPLOAD_BYTES:
                raise StepFailure("Bản xem trước 1080p vẫn quá 50MB, không gửi được qua Telegram.")
            ctx.report(0.5, "Gửi video 1080p lên Telegram")
            api.send_video(origin.chat_id, preview, build_caption(ctx.job), reply_to=origin.message_id,
                           width=size[0], height=size[1], duration=round(info.duration))
            ctx.update_job(lambda j: setattr(j.telegram, "preview_sent", True))

        if not origin.file_sent:
            size_name = ctx.config.video.label
            megabytes = final.stat().st_size / 1_000_000
            if final.stat().st_size <= MAX_UPLOAD_BYTES:
                ctx.report(0.75, f"Gửi file {size_name} ({megabytes:.0f}MB)")
                document = Path(ctx.job.export_path) if ctx.job.export_path else final
                api.send_document(origin.chat_id, document if document.exists() else final,
                                  f"File {size_name} {ctx.config.video.fps}fps gốc", reply_to=origin.message_id)
            else:
                where = ctx.job.export_path or str(final)
                api.send_message(origin.chat_id, f"File {size_name} nặng {megabytes:.0f}MB, vượt giới hạn 50MB của "
                                                 f"Telegram — nằm trên Mac tại:\n{where}", reply_to=origin.message_id)
            ctx.update_job(lambda j: setattr(j.telegram, "file_sent", True))

        title = ctx.job.source.title if ctx.job.source else ""
        if title and not origin.title_sent:
            text = "\n".join([title, " ".join(ctx.job.hashtags)]) if ctx.job.hashtags else title
            api.send_message(origin.chat_id, text, reply_to=origin.message_id)  # title + hashtags only: easy to copy
            ctx.update_job(lambda j: setattr(j.telegram, "title_sent", True))
    except TelegramApiError as exc:
        raise StepFailure(f"Gửi Telegram lỗi: {exc}. Video đã xuất trên Mac; bấm 'Thử lại' để gửi lại.") from exc
    ctx.report(1, "Đã gửi về Telegram")
