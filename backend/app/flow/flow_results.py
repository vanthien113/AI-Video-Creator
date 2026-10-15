"""Watch Flow for the generated video, download it, and capture evidence on errors.

Observed 2026-10-15: a finished video is a <flow-video-tile> whose thumbnail <img> src is
flow-content.google/image/<id>; the playable <video> (same <id>) only mounts on hover.
Downloads go through the tile's "More options" → "Download" → "720p Original size" /
"1080p Upscaled" (disabled on some plans).
"""

import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from .flow_client import FlowClient, FlowError

PERCENT = re.compile(r"^(\d{1,3})%$")


def video_key(src: str) -> str:
    """Media id from a Flow URL (signed query params change between page loads)."""
    return urlparse(src).path.rstrip("/").rsplit("/", 1)[-1]


def list_videos(client: FlowClient) -> list[str]:
    """Video ids in grid order (newest first)."""
    srcs = client.find("result_video_thumb").evaluate_all("els => els.map(e => e.currentSrc || e.src).filter(Boolean)")
    return list(dict.fromkeys(video_key(s) for s in srcs))


def stable_video_ref(client: FlowClient, known: set[str], fresh_ref: str, log: Callable[[str], None]) -> str:
    """A just-finished video shows a temporary id; after a reload Flow serves a stable one.

    Reload, then take the video that was not there before submission.
    """
    client.page.reload(wait_until="domcontentloaded")
    client.page.wait_for_timeout(5000)
    client.dismiss_popups()
    fresh = [v for v in list_videos(client) if v not in known]
    if len(fresh) == 1:
        return fresh[0]
    log(f"flow: không xác định được mã ổn định ({len(fresh)} video mới); giữ mã tạm {fresh_ref[:40]}")
    return fresh_ref


def generation_percent(client: FlowClient) -> int | None:
    texts = client.page.evaluate(
        "() => [...document.querySelectorAll('body *')].filter(e => !e.children.length && /^\\d{1,3}%$/.test((e.textContent || '').trim())).map(e => e.textContent.trim())"
    )
    values = [int(m.group(1)) for t in texts if (m := PERCENT.match(t))]
    return max(values) if values else None


def check_errors(client: FlowClient, baseline_text: str) -> None:
    """Raise if an error message appeared on the page after submission."""
    before = set(baseline_text.splitlines())
    fresh = "\n".join(line for line in client.page.inner_text("body").splitlines() if line not in before)
    messages = {
        "out_of_credits": "Flow báo hết credit. Nạp thêm hoặc đợi chu kỳ mới rồi thử lại.",
        "policy_blocked": "Flow chặn yêu cầu vì chính sách nội dung. Sửa prompt (bước Prompt → Viết lại) rồi thử lại.",
        "generation_failed": "Flow báo sinh video thất bại.",
    }
    for kind, pattern in client.sel.error_patterns().items():
        if pattern.search(fresh):
            raise FlowError(messages.get(kind, f"Flow báo lỗi ({kind})."), kind)


def wait_for_new_video(client: FlowClient, known: set[str], timeout: float, baseline_text: str,
                       report: Callable[[float, str], None], should_stop: Callable[[], bool]) -> str:
    started = time.time()
    while time.time() - started < timeout:
        client.page.wait_for_timeout(5000)
        if should_stop():
            raise FlowError("Job đã bị huỷ (video vẫn có thể đang sinh trên Flow).", "cancelled")
        client.dismiss_popups()
        fresh = [v for v in list_videos(client) if v not in known]
        if fresh:
            return fresh[0]
        check_errors(client, baseline_text)
        elapsed = int(time.time() - started)
        percent = generation_percent(client)
        label = f"{percent}%" if percent is not None else f"{elapsed}s"
        progress = percent / 100 if percent is not None else elapsed / timeout
        report(0.3 + 0.65 * min(progress, 1), f"Flow đang sinh video ({label})")
    raise FlowError(f"Quá {int(timeout)}s chưa thấy video mới trên Flow.", "timeout")


def _open_download_menu(client: FlowClient, ref: str):
    tile = client.find("result_tile").filter(has=client.page.locator(f'[src*="{ref}"]')).first
    if not tile.count():
        raise FlowError("Không thấy video đã sinh trên trang dự án Flow.")
    tile.scroll_into_view_if_needed()
    tile.hover()
    client.pause()
    client.sel.locate(tile, "tile_more_button").first.click(timeout=10000)
    client.pause()
    client.find("download_menu_item").first.hover()
    client.pause()
    return tile


def download_video(client: FlowClient, ref: str, quality: str, dest: Path, log: Callable[[str], None]) -> str:
    """Download via the tile menu: 1080p when allowed, else the original; last resort the raw source."""
    try:
        tile = _open_download_menu(client, ref)
        wanted = ["download_option_1080p", "download_option_original"] if quality == "1080p" else ["download_option_original"]
        for key in wanted:
            option = client.find(key).last
            if not option.count() or option.is_disabled():
                log(f"flow_download: '{key}' không dùng được trên tài khoản này")
                continue
            with client.page.expect_download(timeout=300000) as download:
                option.click()
            download.value.save_as(dest)
            return key.removeprefix("download_option_")
    except FlowError:
        raise
    except Exception as exc:
        log(f"flow_download: menu tải lỗi ({type(exc).__name__}: {exc}); thử lấy nguồn video")
    client.page.keyboard.press("Escape")
    client.page.keyboard.press("Escape")
    tile = client.find("result_tile").filter(has=client.page.locator(f'[src*="{ref}"]')).first
    tile.hover()
    client.page.wait_for_timeout(1500)
    srcs = tile.locator("video").evaluate_all("els => els.map(e => e.currentSrc || e.src).filter(Boolean)")
    if not srcs:
        raise FlowError("Không lấy được nguồn video trên Flow.")
    response = client.page.request.get(srcs[0], timeout=120000)
    if not response.ok:
        raise FlowError(f"Tải video gốc thất bại (HTTP {response.status}).")
    dest.write_bytes(response.body())
    return "source"
