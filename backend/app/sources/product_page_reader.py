"""Read a TikTok Shop product page in the tool's Chrome: title, description and product images.

Deliberately selector-free: it relies on Open Graph meta tags and on image size, so a TikTok
redesign is less likely to break it. Check a live page with `python -m app.sources.check_product_page <url>`.
"""

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

COLLECT_JS = """() => ({
  url: location.href,
  title: (document.querySelector('meta[property="og:title"]') || {}).content || document.title || '',
  description: (document.querySelector('meta[property="og:description"]')
                || document.querySelector('meta[name="description"]') || {}).content || '',
  ogImages: [...document.querySelectorAll('meta[property="og:image"]')].map(m => m.content).filter(Boolean),
  images: [...document.images].map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight})),
  text: document.body ? document.body.innerText.slice(0, 3000) : ''
})"""

BLOCKED_PAGE = re.compile(r"captcha|verify to continue|slide to complete|xác minh|log in to continue|đăng nhập để", re.I)
FIREWALL_PAGE = re.compile(r"application control|web filter|violates your internet usage policy|fortigate|access denied", re.I)
NETWORK_BLOCKED = ("Mạng hiện tại đang chặn TikTok (tường lửa, thường là mạng công ty). "
                   "Dùng mạng cho phép TikTok, hoặc bấm 'Dùng ảnh của tôi'.")
TITLE_SUFFIX = re.compile(r"\s*[|\-–]\s*TikTok( Shop)?.*$", re.I)


# Page content is untrusted: only follow pages that stay on TikTok, and only fetch public https images.
TRUSTED_PAGE_HOST = "tiktok.com"
REQUIRE_HTTPS = True
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_TIMEOUT_MS = 15000


class SourceError(Exception):
    """The product page could not be read; message is meant for the user."""


@dataclass
class ProductPage:
    url: str
    title: str
    description: str
    image_urls: list[str] = field(default_factory=list)


def image_key(url: str) -> str:
    """Identity of an image across size variants: TikTok's CDN appends '~tplv-...:W:H' to one path."""
    path = urlparse(url).path
    return path.split("~", 1)[0]


def is_public_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" and (REQUIRE_HTTPS or parsed.scheme != "http"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        ipaddress.ip_address(host)
        return False  # raw IPs: no legitimate product image needs one; blocks LAN/loopback requests
    except ValueError:
        return True


def host_is_trusted(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == TRUSTED_PAGE_HOST or host.endswith("." + TRUSTED_PAGE_HOST)


def pick_image_urls(og_images: list[str], images: list[dict], min_side: int = 500, limit: int = 12) -> list[str]:
    """og:image first, then on-page images at least `min_side` px on both sides; deduplicated."""
    ordered = list(og_images) + [i["src"] for i in images if min(i.get("w", 0), i.get("h", 0)) >= min_side]
    picked, seen = [], set()
    for url in ordered:
        if not is_public_image_url(url) or url.lower().split("?")[0].endswith((".svg", ".gif")):
            continue
        key = image_key(url)
        if key in seen:
            continue
        seen.add(key)
        picked.append(url)
        if len(picked) >= limit:
            break
    return picked


def blocked_reason(status: int | None, title: str, text: str) -> str | None:
    """Why the loaded page is not a product page, or None if it looks fine."""
    if FIREWALL_PAGE.search(title) or FIREWALL_PAGE.search(text[:1500]):
        return NETWORK_BLOCKED
    if status and status >= 400:
        return f"TikTok trả về lỗi HTTP {status}. Thử lại sau, hoặc bấm 'Dùng ảnh của tôi'."
    if BLOCKED_PAGE.search(text):
        return ("TikTok yêu cầu xác minh hoặc đăng nhập. Mở link này trong cửa sổ Chrome của tool, "
                "xác minh xong rồi bấm 'Thử lại'.")
    return None


def clean_title(title: str) -> str:
    return TITLE_SUFFIX.sub("", title.strip())


def read_product_page(page, url: str, timeout_ms: int = 60000) -> ProductPage:
    from playwright.sync_api import Error as PlaywrightError

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightError as exc:
        message = str(exc)
        if "ERR_CERT" in message:
            raise SourceError(NETWORK_BLOCKED) from exc
        if "ERR_NAME_NOT_RESOLVED" in message or "ERR_INTERNET_DISCONNECTED" in message:
            raise SourceError("Không kết nối được tới TikTok. Kiểm tra mạng rồi thử lại.") from exc
        raise SourceError(f"Không mở được link: {message.splitlines()[0]}") from exc
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightError:
        pass  # pages with long-polling never go idle; what has loaded is enough
    page.mouse.wheel(0, 1200)  # nudge lazy-loaded gallery images
    page.wait_for_timeout(1500)
    data = page.evaluate(COLLECT_JS)
    if not host_is_trusted(data["url"]):
        raise SourceError(f"Link chuyển tới trang không phải TikTok ({urlparse(data['url']).hostname}), đã dừng lại.")
    urls = pick_image_urls(data["ogImages"], data["images"])
    if not urls:
        reason = blocked_reason(response.status if response else None, data["title"], data["text"])
        if reason:
            raise SourceError(reason)
        raise SourceError("Không thấy ảnh sản phẩm trên trang. Link có đúng là trang sản phẩm TikTok Shop không?")
    return ProductPage(url=data["url"], title=clean_title(data["title"]), description=data["description"].strip(),
                       image_urls=urls)


def download_images(request, urls: list[str], dest_dir: Path, min_side: int = 400,
                    should_stop: Callable[[], bool] = lambda: False) -> list[str]:
    """Fetch with the browser's cookies, keep real images ≥ min_side, save as numbered JPEGs."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS  # refuse decompression bombs instead of eating RAM
    dest_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for url in urls:
        if should_stop():
            break
        try:
            response = request.get(url, timeout=IMAGE_TIMEOUT_MS, max_redirects=3)
            body = response.body() if response.ok else b""
            if not body or len(body) > MAX_IMAGE_BYTES:
                continue
            with Image.open(BytesIO(body)) as img:
                if min(img.size) < min_side:
                    continue
                name = f"{len(names) + 1:02d}.jpg"
                img.convert("RGB").save(dest_dir / name, quality=95)
                names.append(name)
        except Exception:
            continue  # one broken image must not lose the others
    return names
