"""Is a hashtag real on TikTok? Read the challenge/detail answer the tag page fetches for itself.

Measured 2026-10-16 (~1.2 s per tag): #giaycaogot → statusCode 0, 1,231,010 videos; #sandalnu2026 →
statusCode 0 but 10 videos; #depsandallonumuikin (glued together by Google's AI) → statusCode 10205.
"""

from collections.abc import Callable
from urllib.parse import quote

MIN_VIDEOS = 1000  # below this a tag exists but nobody really uses it


def tag_videos(page, tag: str) -> int | None:
    """Number of videos under `tag`, or None when TikTok has no such hashtag."""
    with page.expect_response(lambda r: "/api/challenge/detail" in r.url, timeout=15000) as answer:
        page.goto(f"https://www.tiktok.com/tag/{quote(tag.lstrip('#'))}", wait_until="domcontentloaded", timeout=30000)
    data = answer.value.json()
    if data.get("statusCode") != 0:
        return None
    info = data.get("challengeInfo") or {}
    stats = info.get("statsV2") or info.get("stats") or {}
    return int(stats.get("videoCount") or 0)


def pick_real(candidates: list[str], videos: Callable[[str], int | None], need: int = 3,
              min_videos: int = MIN_VIDEOS) -> tuple[list[str], bool]:
    """First `need` candidates (in the order given, i.e. most suitable first) that TikTok really uses.
    If TikTok cannot be reached, the first candidates are kept and flagged as unverified."""
    chosen: list[str] = []
    for i, tag in enumerate(candidates):
        try:
            count = videos(tag)
        except Exception:
            rest = [t for t in candidates[i:] if t not in chosen]
            return (chosen + rest)[:need], False
        if count is not None and count >= min_videos:
            chosen.append(tag)
            if len(chosen) == need:
                break
    return chosen, True
