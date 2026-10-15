"""Turn one incoming Telegram message into link jobs and a short reply (pure, no network)."""

import re
from collections.abc import Callable

TIKTOK_LINK = re.compile(r"https?://(?:[\w-]+\.)*tiktok\.com/[^\s<>\"']+", re.I)
TRAILING_PUNCTUATION = ".,;:!?)]}»”’"


def extract_tiktok_links(text: str) -> list[str]:
    links = [m.group(0).rstrip(TRAILING_PUNCTUATION) for m in TIKTOK_LINK.finditer(text or "")]
    return list(dict.fromkeys(links))


def handle_message(message: dict, allowed_ids: set[int], on_link: Callable[[str], bool]) -> str | None:
    """Return the reply text (None = stay silent). `on_link` returns False for a duplicate link."""
    text = (message.get("text") or message.get("caption") or "").strip()
    user_id = (message.get("from") or {}).get("id")
    is_start = text.startswith("/start")

    if user_id not in allowed_ids:
        if is_start:  # only reveal setup info to someone deliberately starting the bot
            return (f"ID Telegram của bạn: {user_id}\n"
                    "Thêm số này vào TELEGRAM_ALLOWED_USER_IDS trong file .env rồi khởi động lại AI Video Creator.")
        return None

    links = extract_tiktok_links(text)
    if not links:
        return "Sẵn sàng! Gửi link sản phẩm TikTok Shop vào đây." if is_start else \
            "Không thấy link TikTok trong tin nhắn."
    accepted = sum(1 for link in links if on_link(link))
    skipped = len(links) - accepted
    if not accepted:
        return "Link này đang có trong hàng chờ rồi."
    reply = "Đã nhận link ✅ Mở AI Video Creator để chọn ảnh." if accepted == 1 else \
        f"Đã nhận {accepted} link ✅ Mở AI Video Creator để chọn ảnh."
    return reply + (f" ({skipped} link đã có trong hàng chờ, bỏ qua.)" if skipped else "")
