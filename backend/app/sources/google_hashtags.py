"""Ask Google's AI Mode for 3 TikTok hashtags trending in Vietnam for a product.

Observed 2026-10-16: the plain results page shows an AI answer only sometimes, while AI Mode
(udm=50) answered in ~8 s with a numbered list, each item starting with the hashtag, e.g.
"#giaycaogotnu (hoặc #giaycaogot)", followed by the reasons and sources.
It runs in the tool's Chrome, i.e. the same Google account as Flow: one query per video only.
"""

import re
import time
from urllib.parse import quote

AI_MODE_URL = "https://www.google.com/search?hl=vi&udm=50&q="
TAG = re.compile(r"#[0-9A-Za-zÀ-ỹĐđ_]{2,40}")
BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|【[^】]*】")
MAX_NAME = 90


def search_query(title: str) -> str:
    """Shop titles carry promo brackets ("(DEAL ĐỘC QUYỀN …)"): drop them and keep the product name short."""
    name = " ".join(BRACKETS.sub(" ", title).split())
    if len(name) > MAX_NAME:
        name = name[:MAX_NAME].rsplit(" ", 1)[0]
    return f"3 hashtag tiktok đang xu hướng ở Việt Nam cho sản phẩm {name}"


def parse_hashtags(items: list[str], text: str, count: int = 3) -> list[str]:
    """Lead hashtag of each list item ("#a (hoặc #b)" gives #a); top up from the free text if needed."""
    picked = [m.group(0) for line in items if (m := TAG.match(line.strip()))]
    picked += TAG.findall(text)
    return list(dict.fromkeys(picked))[:count]


def read_ai_mode(page, query: str, timeout: float = 25) -> tuple[list[str], str]:
    """(first line of every list item, page text) once the answer has stopped streaming."""
    page.goto(AI_MODE_URL + quote(query), wait_until="domcontentloaded", timeout=30000)
    deadline, last, stable = time.time() + timeout, "", 0
    while time.time() < deadline:
        if "/sorry/" in page.url:
            raise RuntimeError("Google yêu cầu xác minh (captcha)")
        text = page.inner_text("body")
        if "unusual traffic" in text.lower():
            raise RuntimeError("Google báo lưu lượng bất thường")
        stable = stable + 1 if text == last and TAG.search(text) else 0
        last = text
        if stable >= 3:
            break
        page.wait_for_timeout(700)
    items = page.evaluate("() => [...document.querySelectorAll('li')].map(li => (li.innerText || '').split('\\n')[0].trim())")
    return items, last
