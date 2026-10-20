"""Reply in Telegram with the finished video itself (nothing re-encoded), or a note saying where it is on the
Mac if it is over the 50MB bot limit, then the bare product title (a message of its own, so it is easy to copy).

Only jobs that came from Telegram do anything here. Each part is marked as sent once delivered,
so "Thử lại" after a network error never posts the same video twice.
"""

from pathlib import Path

from ..job_models import JobState
from ..media.video_probe import probe_video
from ..telegram.telegram_api import MAX_UPLOAD_BYTES, TelegramApi, TelegramApiError
from .enhance_video_step import output_label
from .step_types import JobContext, StepFailure


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


def build_caption(job: JobState) -> str:
    """Only the product link: the title and hashtags follow in a message of their own."""
    return job.source.url if job.source else ""


def upload_file(ctx: JobContext, final: Path) -> Path:
    """The exported copy (its name says what it is), or the job's own file if the export is gone."""
    exported = Path(ctx.job.export_path) if ctx.job.export_path else final
    return exported if exported.exists() else final


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
    size_name = output_label(ctx.config.video, final)
    fits = final.stat().st_size <= MAX_UPLOAD_BYTES
    file_sent = origin.file_sent  # ctx.job is not refreshed by update_job

    try:
        if not origin.preview_sent and fits:  # the finished file itself plays in the chat, no second copy
            ctx.report(0.3, f"Gửi video {size_name} lên Telegram")
            info = probe_video(final)
            api.send_video(origin.chat_id, upload_file(ctx, final), build_caption(ctx.job), reply_to=origin.message_id,
                           width=info.width, height=info.height, duration=round(info.duration))

            def sent(j: JobState) -> None:
                j.telegram.preview_sent = j.telegram.file_sent = True

            ctx.update_job(sent)
            file_sent = True

        if not file_sent:
            megabytes = final.stat().st_size / 1_000_000
            if fits:  # a job whose preview video went out before this run
                ctx.report(0.75, f"Gửi file {size_name} ({megabytes:.0f}MB)")
                api.send_document(origin.chat_id, upload_file(ctx, final),
                                  f"File {size_name} {ctx.config.video.fps}fps gốc", reply_to=origin.message_id)
            else:
                where = ctx.job.export_path or str(final)
                api.send_message(origin.chat_id, f"File {size_name} nặng {megabytes:.0f}MB, vượt giới hạn 50MB của "
                                                 f"Telegram — nằm trên Mac tại:\n{where}", reply_to=origin.message_id)
            ctx.update_job(lambda j: setattr(j.telegram, "file_sent", True))

        title = ctx.job.source.title if ctx.job.source else ""
        if title and not origin.title_sent:
            tags = " ".join(ctx.job.hashtags) + ("" if ctx.job.hashtags_verified else " (chưa xác minh)")
            text = f"{title}\n{tags}" if ctx.job.hashtags else title
            api.send_message(origin.chat_id, text, reply_to=origin.message_id)  # title + hashtags only: easy to copy
            ctx.update_job(lambda j: setattr(j.telegram, "title_sent", True))
    except TelegramApiError as exc:
        raise StepFailure(f"Gửi Telegram lỗi: {exc}. Video đã xuất trên Mac; bấm 'Thử lại' để gửi lại.") from exc
    ctx.report(1, "Đã gửi về Telegram")
