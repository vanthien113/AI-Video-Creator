"""Step 0 (link jobs only): read the TikTok Shop page and save candidate product images."""

import shutil
from dataclasses import replace

from ..flow.cdp_connection import BrowserNotRunning, browser_context, capture_page_error, new_tab
from ..job_models import JobState
from ..job_store import slugify
from ..mac_notification import notify
from ..sources.product_page_reader import SourceError, download_images, read_product_page
from ..telegram.telegram_api import TelegramApi, TelegramApiError
from ..telegram.telegram_pick import send_picker
from .step_types import JobContext, StepFailure

MAX_PRODUCT_INFO = 800


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


def run_fetch_product(ctx: JobContext) -> None:
    source = ctx.job.source
    if source is None:
        raise StepFailure("Job này không có link sản phẩm.")
    from playwright.sync_api import Error as PlaywrightError

    candidates_dir = ctx.path("candidates")

    def forget_old(j: JobState) -> None:
        j.source.candidates = []  # never point at files we are about to delete

    ctx.update_job(forget_old)
    shutil.rmtree(candidates_dir, ignore_errors=True)
    try:
        with browser_context(ctx.config.flow.cdp_port) as context:
            page = new_tab(context)  # own tab: never disturb the Flow tab
            try:
                ctx.report(0.1, "Mở trang sản phẩm TikTok")
                product = read_product_page(page, source.url)
                ctx.log(f"fetch: {product.url} title={product.title!r} images={len(product.image_urls)}")
                ctx.report(0.6, f"Tải {len(product.image_urls)} ảnh sản phẩm")
                names = download_images(page.request, product.image_urls, candidates_dir, should_stop=ctx.is_cancelled)
            except (SourceError, PlaywrightError) as exc:
                shot = capture_page_error(page, ctx.path("errors"))
                message = str(exc) if isinstance(exc, SourceError) else f"Đọc trang lỗi: {str(exc).splitlines()[0]}"
                raise StepFailure(message, screenshot=shot) from exc
            finally:
                try:
                    page.close()
                except PlaywrightError:
                    pass  # Chrome went away mid-fetch: keep the real error, not the cleanup one
    except BrowserNotRunning as exc:
        raise StepFailure(str(exc)) from exc
    if not names:
        raise StepFailure("Không tải được ảnh sản phẩm nào từ trang. Thử lại, hoặc bấm 'Dùng ảnh của tôi'.")

    def save(j: JobState) -> None:
        j.source.title, j.source.description, j.source.candidates = product.title, product.description, names
        j.product_info = "\n".join(p for p in (product.title, product.description) if p)[:MAX_PRODUCT_INFO]
        if product.title:
            j.name = slugify(product.title)

    job = ctx.update_job(save)
    notify("AI Video Creator", f"Chờ chọn ảnh: {product.title or 'sản phẩm TikTok'}")
    token = ctx.config.telegram.bot_token
    if job.telegram and token:
        try:
            send_picker(replace(ctx, job=job), make_api(token))
        except (TelegramApiError, OSError) as exc:
            ctx.log(f"fetch: không gửi được ảnh chọn lên Telegram ({exc}); chọn trên giao diện")
    ctx.report(1, f"Đã lấy {len(names)} ảnh")
