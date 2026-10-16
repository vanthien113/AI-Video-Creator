"""Ask Google's AI Mode for TikTok hashtag candidates for a product (checked on TikTok afterwards).

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
BREAKS = re.compile(r"\s+[-–|]\s+|[,;|]|\s-(?=\s|\w)")
MAX_WORDS = 8


def search_query(title: str, product_type: str = "") -> str:
    """Ask by product type, not the whole shop title: with the full title Google glued its words into
    tags nobody uses (#depsandallonumuikin). `product_type` is what Claude named it at the prompt step
    ("dép sandal nữ"); without it, promo brackets go and the title stops at the first separator."""
    name = product_type or BREAKS.split(" ".join(BRACKETS.sub(" ", title).split()))[0]
    name = " ".join(name.split()[:MAX_WORDS])
    return f"10 hashtag tiktok phổ biến, đang được dùng nhiều ở Việt Nam cho {name}"


def parse_hashtags(items: list[str], text: str, count: int = 10) -> list[str]:
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
