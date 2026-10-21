"""Before the Telegram reply: a Shopee link for the product, found from the main photo (shopee.enabled).

Google Lens lists Shopee products that look like the photo; up to shopee.max_candidates of them are read
in Google's order, stopping at the TikTok shop's own listing, else the most sold is kept. A bot check (or a
page that will not load) stops the reading: the best of the pages read wins, and when none opened, Lens's
first result goes out marked as unchecked. Never fails the job.
"""

import time
from contextlib import contextmanager

from ..flow.cdp_connection import browser_context, new_tab
from ..job_models import JobState, ShopeeListing
from ..sources.shopee_search import lens_shopee_links, pick_listing, product_urls, read_listing, same_shop
from .step_types import JobContext

PAUSE_SEC = 2  # between Shopee pages: a burst of page loads is what trips Shopee's bot check


class BrowserShopee:
    """Google Lens and the Shopee pages, one after another in a background tab of the tool's Chrome."""

    def __init__(self, page):
        self.page, self.reads = page, 0

    def links(self, image) -> list[str]:
        return lens_shopee_links(self.page, image)

    def listing(self, url: str) -> ShopeeListing:
        if self.reads:
            time.sleep(PAUSE_SEC)
        self.reads += 1
        return read_listing(self.page, url)


@contextmanager
def open_browser(ctx: JobContext):  # replaced in tests
    with browser_context(ctx.config.flow.cdp_port) as context:
        page = new_tab(context)  # background tab: Chrome stays behind the user's work
        try:
            yield BrowserShopee(page)
        finally:
            page.close()


def find_listing(ctx: JobContext, browser, image, tiktok_shop: str) -> ShopeeListing | None:
    ctx.report(0.2, "Tìm trên Google Lens")
    urls = product_urls(browser.links(image), ctx.config.shopee.max_candidates)
    ctx.log(f"shopee: {len(urls)} sản phẩm từ Google Lens")
    read: list[ShopeeListing] = []
    for n, url in enumerate(urls, 1):
        ctx.report(0.3 + 0.6 * n / len(urls), f"Đọc shop Shopee {n}/{len(urls)}")
        try:
            listing = browser.listing(url)
        except Exception as exc:  # a bot check or a page that will not load: read no further
            ctx.log(f"shopee: không mở được {url} ({type(exc).__name__}: {exc})")
            break
        ctx.log(f"shopee: {listing.shop!r} đã bán {listing.sold} · {listing.rating:.1f}★ {url}")
        read.append(listing)
        if same_shop(tiktok_shop, listing.shop):
            break
    if read:
        return pick_listing(read, tiktok_shop)
    return ShopeeListing(url=urls[0], checked=False) if urls else None


def run_shopee(ctx: JobContext) -> None:
    source = ctx.job.source
    image = ctx.path(ctx.job.input_file) if ctx.job.input_file else None
    if not ctx.config.shopee.enabled or source is None or image is None or not image.exists():
        return
    try:
        with open_browser(ctx) as browser:
            found = find_listing(ctx, browser, image, source.shop)
    except Exception as exc:  # Google failed: the link is a nice-to-have, never fail the job over it
        ctx.log(f"shopee: lỗi ({type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}); không gửi link")
        found = None

    def save(j: JobState) -> None:
        j.shopee = found

    ctx.update_job(save)
    ctx.report(1, "Không có link Shopee" if not found else f"Shopee: {found.shop}" if found.checked
               else "Shopee: kết quả Google đầu tiên (chưa kiểm tra)")
