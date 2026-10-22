"""Last step: upload the exported video to TikTok Studio, Save draft (never Post), then tell the user on Telegram.

The draft is recorded as saved before the Telegram note goes out, so "Thử lại" after a Telegram
error never creates a second draft.
"""

from pathlib import Path

from ..flow.cdp_connection import BrowserNotRunning, browser_context, capture_page_error, new_tab
from ..job_models import JobState, now_iso
from ..telegram.telegram_api import TelegramApi, TelegramApiError
from ..telegram.telegram_notify import notify_target
from ..tiktok.post_plan import post_title
from ..tiktok.studio_upload import StudioError, save_draft
from .step_types import JobContext, StepFailure


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


def draft_description(job: JobState) -> str:
    return post_title(job)


def save_draft_in_browser(ctx: JobContext, video: Path, description: str) -> None:  # replaced in tests
    try:
        with browser_context(ctx.config.flow.cdp_port) as context:
            page = new_tab(context)  # own tab: never disturb the Flow tab
            try:
                save_draft(page, ctx.config.tiktok, video, description, ctx.report, ctx.log)
            except StudioError as exc:
                raise StepFailure(str(exc), screenshot=capture_page_error(page, ctx.path("errors"))) from exc
            except Exception as exc:
                shot = capture_page_error(page, ctx.path("errors"))
                raise StepFailure(f"Thao tác trên TikTok Studio lỗi: {str(exc).splitlines()[0]}", screenshot=shot) from exc
            page.close()  # only on success: a failed tab stays open so the user can look at it
    except BrowserNotRunning as exc:
        raise StepFailure(str(exc)) from exc


def run_tiktok_draft(ctx: JobContext) -> None:
    if not ctx.config.tiktok.save_draft:
        return
    job = ctx.job
    exported = Path(job.export_path) if job.export_path else None
    video = exported if exported and exported.exists() else ctx.path("final-4k60.mp4")
    if not video.exists():
        raise StepFailure("Không thấy video đã xuất, chạy lại bước xuất file.")

    if not job.tiktok.saved_at:
        save_draft_in_browser(ctx, video, draft_description(job))
        ctx.update_job(lambda j: setattr(j.tiktok, "saved_at", now_iso()))
        ctx.log(f"tiktok_draft: đã lưu nháp {video.name}")

    target = notify_target(ctx.job, ctx.config.telegram)
    token = ctx.config.telegram.bot_token
    if ctx.job.tiktok.notified or not target or not token:
        ctx.report(1, "Đã lưu nháp TikTok")
        return
    chat_id, reply_to = target
    text = (f"✅ Đã lưu nháp TikTok: {draft_description(ctx.job)}\n📁 {video.name}\n"
            "Mở TikTok Studio → Bản nháp để xem lại rồi đăng.")
    try:
        make_api(token).send_message(chat_id, text, reply_to=reply_to)
    except TelegramApiError as exc:
        raise StepFailure(f"Đã lưu nháp TikTok nhưng nhắn Telegram lỗi: {exc}. Bấm 'Thử lại' để nhắn lại.") from exc
    ctx.update_job(lambda j: setattr(j.tiktok, "notified", True))
    ctx.report(1, "Đã lưu nháp TikTok và báo Telegram")
