"""What gets posted on TikTok and when: product ID, title, the next free schedule slot. Pure, no browser."""

import re
from collections.abc import Iterable
from datetime import datetime, timedelta

from ..job_models import JobState

PRODUCT_ID = re.compile(r"/(?:pdp|product)/(?:[^/?#]+/)?(\d{10,})")
MAX_DAYS_AHEAD = 30  # TikTok Studio's calendar offered today + 30 days (surveyed 2026-10-17)
WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


def product_id_from_url(url: str) -> str:
    match = PRODUCT_ID.search(url or "")
    return match.group(1) if match else ""


def job_product_id(job: JobState) -> str:
    """Saved when the product page was read; older jobs fall back to their link when it is a /pdp/ link."""
    if not job.source:
        return ""
    return job.source.product_id or product_id_from_url(job.source.url)


def post_title(job: JobState) -> str:
    """Claude's caption; jobs from before captions fall back to the shop's product title."""
    return (job.caption or (job.source.title if job.source else "") or job.name).strip()


def next_slot(now: datetime, slots: list[int], lead_min: int, taken: Iterable[datetime | None]) -> datetime:
    """First slot strictly after the latest post already there (on TikTok or scheduled by this tool) and at
    least lead_min minutes from now; past the day's last slot, the first slot of the next day."""
    floor = max([now + timedelta(minutes=lead_min), *(t for t in taken if t)])
    day = floor.replace(hour=0, minute=0, second=0, microsecond=0)
    hours = sorted(set(slots))
    for hour in hours:
        if day.replace(hour=hour) > floor:
            return day.replace(hour=hour)
    return day + timedelta(days=1, hours=hours[0])


def too_far(slot: datetime, now: datetime) -> bool:
    return slot.date() > (now + timedelta(days=MAX_DAYS_AHEAD)).date()


def slot_label(when: datetime, weekday: bool = True) -> str:
    """'19:00 Chủ nhật 18/10' for messages; weekday=False gives the short '19:00 18/10'."""
    day = f" {WEEKDAYS[when.weekday()]}" if weekday else ""
    return f"{when:%H:%M}{day} {when:%d/%m}"
