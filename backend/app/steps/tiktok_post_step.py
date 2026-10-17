"""Last step: post the exported video on TikTok now, or at the next free slot, once the user pressed Đăng ngay /
Lên lịch (tool or Telegram). For jobs nobody asked to post it only sends those two buttons to Telegram.

submitted_at is saved right before the Post/Schedule click and done_at only once the post shows on TikTok
Studio's Content page, so neither "Thử lại" nor a restart ever clicks a second time on its own.
"""

import time
from datetime import datetime
from pathlib import Path

from ..flow.cdp_connection import BrowserNotRunning, browser_context, capture_page_error, new_tab
from ..job_models import JobState, now_iso
from ..telegram.telegram_api import TelegramApi, TelegramApiError
from ..telegram.telegram_notify import notify_target
from ..telegram.telegram_post import FAILED_TEXT, done_text, edit_offer, result_message, send_offer
from ..tiktok.post_plan import MAX_DAYS_AHEAD, job_product_id, next_slot, post_title, slot_label, too_far
from ..tiktok.studio_content import ContentPageError, find_new_post, latest_time, read_items
from ..tiktok.studio_post import PostPlan, post_video
from ..tiktok.studio_upload import StudioError
from .step_types import JobContext, StepFailure

CONFIRM_TRIES, CONFIRM_WAIT_SEC = 6, 20  # up to 2 minutes for a new post to show on the Content page


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


class BrowserStudio:
    """TikTok Studio in background tabs of the tool's Chrome. A tab that fails stays open for the user to see."""

    def __init__(self, ctx: JobContext):
        self.ctx = ctx

    def content_items(self) -> list[dict]:
        return self._in_tab(lambda page: read_items(page, self.ctx.config.tiktok.content_url))

    def post(self, plan: PostPlan, before_click, dry_run: bool = False) -> None:
        self._in_tab(lambda page: post_video(page, self.ctx.config.tiktok, plan, self.ctx.report, self.ctx.log,
                                             before_click, dry_run=dry_run), keep_open=dry_run)

    def find_post(self, title: str, since: datetime, schedule_at: datetime | None) -> bool:
        for attempt in range(CONFIRM_TRIES):
            if find_new_post(self.content_items(), title, since, schedule_at):
                return True
            if attempt + 1 < CONFIRM_TRIES:
                time.sleep(CONFIRM_WAIT_SEC)
        return False

    def _in_tab(self, work, keep_open: bool = False):
        try:
            with browser_context(self.ctx.config.flow.cdp_port) as context:
                page = new_tab(context)  # background tab: Chrome stays behind the user's work
                try:
                    result = work(page)
                except (StudioError, ContentPageError) as exc:
                    raise StepFailure(str(exc), screenshot=capture_page_error(page, self.ctx.path("errors"))) from exc
                except Exception as exc:
                    shot = capture_page_error(page, self.ctx.path("errors"))
                    reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                    raise StepFailure(f"Thao tác trên TikTok Studio lỗi: {reason}", screenshot=shot) from exc
                if not keep_open:
                    page.close()  # only on success: a failed tab stays open so the user can look at it
                return result
        except BrowserNotRunning as exc:
            raise StepFailure(str(exc)) from exc


def open_studio(ctx: JobContext) -> BrowserStudio:  # replaced in tests
    return BrowserStudio(ctx)


def run_tiktok_post(ctx: JobContext) -> None:
    job = ctx.job
    if job.post.mode is None:
        offer_buttons(ctx)
        return
    try:
        if not job.post.done_at:
            job = post_now_or_later(ctx)
        job = tell_telegram(ctx, job)
    except StepFailure:
        latest = ctx.update_job(lambda j: None)
        if not latest.post.done_at:  # a failed Telegram message after posting is not a failed post
            mark_offer(ctx, latest, FAILED_TEXT)
        raise
    ctx.report(1, done_text(job))


def post_now_or_later(ctx: JobContext) -> JobState:
    job = ctx.job
    if job.post.submitted_at:
        raise StepFailure(unconfirmed(job))
    studio = open_studio(ctx)
    plan = make_plan(ctx, studio)
    if plan.schedule_at:
        ctx.update_job(lambda j: setattr(j.post, "scheduled_for", plan.schedule_at.isoformat(timespec="seconds")))
    clicked: dict[str, JobState] = {}

    def before_click() -> None:
        clicked["job"] = ctx.update_job(lambda j: setattr(j.post, "submitted_at", now_iso()))

    try:
        studio.post(plan, before_click)
    except StepFailure as exc:
        if "job" in clicked:  # failed after the click: say so, never suggest a plain retry
            raise StepFailure(unconfirmed(clicked["job"]), screenshot=exc.screenshot) from exc
        raise
    if "job" not in clicked:
        raise StepFailure("Tool chưa bấm Post/Schedule (thao tác dừng giữa chừng). Bấm Thử lại.")
    submitted = clicked["job"]
    ctx.report(0.95, "Kiểm tra bài trên TikTok Studio")
    try:
        found = studio.find_post(plan.title, datetime.fromisoformat(submitted.post.submitted_at), plan.schedule_at)
    except StepFailure:
        found = False
    if not found:
        raise StepFailure(unconfirmed(submitted))
    job = ctx.update_job(lambda j: setattr(j.post, "done_at", now_iso()))
    ctx.log(f"tiktok_post: {done_text(job)}")
    return job


def make_plan(ctx: JobContext, studio, now: datetime | None = None) -> PostPlan:
    """What to post and, for Lên lịch, the slot after the latest post on TikTok and in this tool."""
    job = ctx.job
    product_id = job_product_id(job)
    if not product_id:
        raise StepFailure("Không biết ID sản phẩm của job này; chạy lại bước Đọc TikTok.")
    plan = PostPlan(video=exported_video(ctx), title=post_title(job), hashtags=list(job.hashtags),
                    product_id=product_id)
    if job.post.mode == "schedule":
        ctx.report(0.05, "Đọc lịch đăng trên TikTok Studio")
        now = now or datetime.now()
        latest = latest_time(studio.content_items())
        cfg = ctx.config.tiktok
        plan.schedule_at = next_slot(now, cfg.schedule_slots, cfg.schedule_lead_min, [latest, *other_scheduled(ctx)])
        ctx.log(f"tiktok_post: bài muộn nhất {latest or 'không có'}, chọn {plan.schedule_at}")
        if too_far(plan.schedule_at, now):
            raise StepFailure(f"Khung giờ kế tiếp là {slot_label(plan.schedule_at)}, quá {MAX_DAYS_AHEAD} ngày "
                              "TikTok cho lên lịch trước. Bớt bài đã lên lịch trên TikTok Studio rồi bấm Thử lại.")
    return plan


def exported_video(ctx: JobContext) -> Path:
    exported = Path(ctx.job.export_path) if ctx.job.export_path else None
    video = exported if exported and exported.exists() else ctx.path("final-4k60.mp4")
    if not video.exists():
        raise StepFailure("Không thấy video đã xuất, chạy lại bước xuất file.")
    return video


def other_scheduled(ctx: JobContext) -> list[datetime]:
    """Slots this tool already scheduled for other jobs: TikTok's list may not show a fresh one yet."""
    taken = []
    for state in ctx.config.paths.jobs_dir.glob("*/state.json"):
        if state.parent.resolve() == ctx.job_dir.resolve():
            continue
        try:
            other = JobState.model_validate_json(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if other.post.mode == "schedule" and other.post.submitted_at and other.post.scheduled_for:
            taken.append(datetime.fromisoformat(other.post.scheduled_for))
    return taken


def unconfirmed(job: JobState) -> str:
    label = "Schedule" if job.post.mode == "schedule" else "Post"
    clicked = datetime.fromisoformat(job.post.submitted_at)
    return (f"Tool đã bấm {label} lúc {clicked:%H:%M %d/%m} nhưng chưa thấy bài trên TikTok Studio. "
            "Kiểm tra TikTok Studio; nếu chưa có bài thì bấm Thử lại.")


def tell_telegram(ctx: JobContext, job: JobState) -> JobState:
    """The button message shows the result and a new message goes under the link; only the latter can fail."""
    token = ctx.config.telegram.bot_token
    target = notify_target(job, ctx.config.telegram)
    if job.post.notified or not token or not target:
        return job
    api = make_api(token)
    edit_offer(job, api, done_text(job))
    chat_id, reply_to = target
    try:
        api.send_message(chat_id, result_message(job), reply_to=reply_to)
    except TelegramApiError as exc:
        verb = "lên lịch" if job.post.mode == "schedule" else "đăng"
        raise StepFailure(f"Đã {verb} TikTok nhưng nhắn Telegram lỗi: {exc}. Bấm 'Thử lại' để nhắn lại.") from exc
    return ctx.update_job(lambda j: setattr(j.post, "notified", True))


def offer_buttons(ctx: JobContext) -> None:
    token = ctx.config.telegram.bot_token
    if not token or not ctx.job.telegram:
        return
    try:
        send_offer(ctx.job, make_api(token), ctx.update_job)
    except (TelegramApiError, OSError) as exc:
        ctx.log(f"tiktok_post: không gửi được nút Đăng ngay / Lên lịch lên Telegram ({exc}); dùng nút trên tool")


def mark_offer(ctx: JobContext, job: JobState, text: str) -> None:
    token = ctx.config.telegram.bot_token
    if token:
        edit_offer(job, make_api(token), text)
