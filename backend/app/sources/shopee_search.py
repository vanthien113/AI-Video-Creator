"""Find the product on Shopee from its photo: Google Lens, then Shopee's own product data.

Observed 2026-10-21 in the tool's Chrome: posting the photo to Lens's upload endpoint opens a results page
with an "Thêm vào nội dung tìm kiếm" box; adding "tìm trên shopee" lists ~14 shopee.vn products, most
similar first. Each Shopee product page loads /api/v4/pdp/get_pc, whose JSON carries the shop name
(data.shop_detailed.name), the sold count as shown ("10k+", data.product_review.sold_count_display) and the
stars (data.item.item_rating.rating_star). A bot check sends the page to shopee.vn/verify/...
"""

import re
import time
import unicodedata
from pathlib import Path

from ..job_models import ShopeeListing

LENS_HOME = "https://lens.google.com/"
LENS_UPLOAD = "https://lens.google.com/v3/upload?hl=vi"
REFINE = "tìm trên shopee"
PRODUCT = re.compile(r"shopee\.vn/(?:product/(\d+)/(\d+)|[^?#]*-i\.(\d+)\.(\d+))")
SOLD = re.compile(r"([\d.,]+)\s*(k|tr|m)?", re.I)
GENERIC = {"shop", "store", "official", "officialstore", "offical", "mall", "vn", "vietnam"}


class ShopeeBlocked(Exception):
    """Shopee asked for a bot check: stop reading, send no link."""


def product_url(link: str) -> str | None:
    """https://shopee.vn/product/<shop>/<item> for a product link (slug or /product/ form), else None."""
    m = PRODUCT.search(link)
    if not m:
        return None
    shop, item = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return f"https://shopee.vn/product/{shop}/{item}"


def product_urls(links: list[str], limit: int) -> list[str]:
    """Distinct product links in Google's order, at most `limit`."""
    urls = [u for u in (product_url(link) for link in links) if u]
    return list(dict.fromkeys(urls))[:limit]


def parse_sold(display: str | None) -> int:
    """'10k+' -> 10000, '1,2k' -> 1200, '1,5tr' -> 1500000, '' -> 0."""
    m = SOLD.search(display or "")
    if not m:
        return 0
    unit = {"k": 1_000, "tr": 1_000_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    number = m.group(1).replace(",", ".")
    if unit == 1:
        number = number.replace(".", "")  # "1.234" sold is a thousands separator
    try:
        return int(float(number) * unit)
    except ValueError:
        return 0


def listing_from_pdp(data: dict, url: str) -> ShopeeListing:
    body = data.get("data") or {}
    item, review, shop = body.get("item") or {}, body.get("product_review") or {}, body.get("shop_detailed") or {}
    return ShopeeListing(
        url=url, shop=(shop.get("name") or "").strip(),
        sold=parse_sold(review.get("sold_count_display") or review.get("historical_sold_display")),
        rating=float((item.get("item_rating") or {}).get("rating_star") or 0))


def shop_key(name: str) -> str:
    plain = unicodedata.normalize("NFD", name.lower().replace("đ", "d"))
    words = re.findall(r"[a-z0-9]+", "".join(ch for ch in plain if unicodedata.category(ch) != "Mn"))
    return "".join(w for w in words if w not in GENERIC)


def same_shop(tiktok_shop: str, shopee_shop: str) -> bool:
    """Same name once case, accents, spaces and words like "shop"/"official" are gone; or one contains the other."""
    a, b = shop_key(tiktok_shop), shop_key(shopee_shop)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def pick_listing(listings: list[ShopeeListing], tiktok_shop: str) -> ShopeeListing | None:
    """The TikTok shop's own listing, else the most sold (more stars breaks a tie)."""
    for listing in listings:
        if same_shop(tiktok_shop, listing.shop):
            return listing
    return max(listings, key=lambda l: (l.sold, l.rating), default=None)


def lens_shopee_links(page, image: Path, timeout: float = 30) -> list[str]:
    """Links to shopee.vn on the Lens results for `image`, refined with "tìm trên shopee"."""
    page.goto(LENS_HOME, wait_until="domcontentloaded", timeout=30000)
    page.evaluate("""action => {
        const form = document.createElement('form');
        form.method = 'POST'; form.enctype = 'multipart/form-data'; form.action = action;
        const input = document.createElement('input');
        input.type = 'file'; input.name = 'encoded_image'; input.id = 'avc_lens_file';
        form.appendChild(input); document.body.appendChild(form);
    }""", LENS_UPLOAD)
    page.set_input_files("#avc_lens_file", str(image))
    with page.expect_navigation(timeout=30000):
        page.evaluate("() => document.getElementById('avc_lens_file').form.submit()")
    box = page.locator("textarea[name=q]").first
    box.wait_for(timeout=20000)
    box.click()
    page.keyboard.insert_text(REFINE)
    page.keyboard.press("Enter")
    deadline, last, stable = time.time() + timeout, "", 0
    while time.time() < deadline:  # the results stream in: wait until the page stops changing
        page.wait_for_timeout(700)
        if "/sorry/" in page.url:
            raise RuntimeError("Google yêu cầu xác minh (captcha)")
        text = page.inner_text("body")
        stable = stable + 1 if text == last and REFINE in page.url + text else 0
        last = text
        if stable >= 3:
            break
    return page.evaluate("() => [...document.querySelectorAll('a[href*=\"shopee.vn\"]')].map(a => a.href)")


def read_listing(page, url: str) -> ShopeeListing:
    """Shop name, sold count and stars from the product page's own data; ShopeeBlocked on a bot check."""
    try:
        with page.expect_response(lambda r: "/api/v4/pdp/get_pc" in r.url, timeout=30000) as response:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        data = response.value.json()
    except Exception:
        if "/verify/" in page.url:
            raise ShopeeBlocked("Shopee yêu cầu xác minh chống bot") from None
        raise
    if "/verify/" in page.url:
        raise ShopeeBlocked("Shopee yêu cầu xác minh chống bot")
    return listing_from_pdp(data, url)
