"""Before the Telegram reply: 3 hashtags for the product, sent after the title so they copy together.

10 candidates from Google's AI Mode (Claude as a fallback), most suitable first; each is checked on
TikTok and the first 3 that exist with enough videos are kept. Never fails the job.
"""

import json

from ..flow.cdp_connection import browser_context, new_tab
from ..media.command_runner import require_tool, run_tool
from ..sources.google_hashtags import parse_hashtags, read_ai_mode, search_query
from ..sources.tiktok_hashtags import pick_real, tag_videos
from .prompt_parsing import result_envelope
from .prompt_step import UNTRUSTED_NOTE, claude_args
from .step_types import JobContext

CANDIDATES = 10
CLAUDE_ASK = ("Give 10 TikTok hashtags people really use for selling this kind of product in Vietnam: Vietnamese "
              "without diacritics, short and common (not glued from the product title), most relevant first. "
              "Reply with one line only, like: #a #b #c\n<shop_page>\n{title}\n</shop_page>\n" + UNTRUSTED_NOTE)


def from_google(ctx: JobContext, title: str, product_type: str = "") -> list[str]:
    with browser_context(ctx.config.flow.cdp_port) as context:
        page = new_tab(context)  # background tab: Chrome stays behind the user's work
        try:
            items, text = read_ai_mode(page, search_query(title, product_type))
        finally:
            page.close()
    tags = parse_hashtags(items, text, CANDIDATES)
    if len(tags) < 3:
        raise RuntimeError(f"Google chỉ trả về {len(tags)} hashtag")
    return tags


def from_claude(ctx: JobContext, title: str) -> list[str]:
    message = json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": CLAUDE_ASK.format(title=title)}]}}) + "\n"
    stdout = run_tool(claude_args(require_tool("claude"), ctx.config.prompt.model), timeout=120, cwd=ctx.job_dir,
                      stdin_text=message, should_stop=ctx.is_cancelled, label="claude -p (hashtag)")
    tags = parse_hashtags([], str(result_envelope(stdout).get("result", "")), CANDIDATES)
    if len(tags) < 3:
        raise RuntimeError(f"Claude chỉ trả về {len(tags)} hashtag")
    return tags


def tiktok_checker(ctx: JobContext):
    """videos(tag) on TikTok, each look-up in its own background tab."""
    def videos(tag: str) -> int | None:
        with browser_context(ctx.config.flow.cdp_port) as context:
            page = new_tab(context)
            try:
                return tag_videos(page, tag)
            finally:
                page.close()

    return videos


def product_type(ctx: JobContext) -> str:
    """The main product type Claude named at the prompt step ("dép sandal nữ"); "" for older jobs."""
    try:
        return json.loads(ctx.path("prompt.json").read_text(encoding="utf-8")).get("product_type", "") or ""
    except (OSError, ValueError, AttributeError):
        return ""


def run_hashtags(ctx: JobContext) -> None:
    title = ctx.job.source.title if ctx.job.source else ""
    if not title:
        return
    kind = product_type(ctx)
    candidates, source = [], ""
    sources = (("google", lambda: from_google(ctx, title, kind)), ("claude", lambda: from_claude(ctx, title)))
    for name, fetch in sources:
        ctx.report(0.15 if name == "google" else 0.4, f"Tìm hashtag ({name})")
        try:
            candidates, source = fetch(), name
            break
        except Exception as exc:  # hashtags are a nice-to-have: try the next source, never fail the job
            ctx.log(f"hashtags: {name} lỗi: {str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__}")
    tags, verified = [], False
    if candidates:
        ctx.log(f"hashtags: ứng viên ({source}) {' '.join(candidates)}")
        ctx.report(0.7, "Kiểm tra hashtag trên TikTok")
        tags, verified = pick_real(candidates, tiktok_checker(ctx))

    def save(j) -> None:
        j.hashtags, j.hashtags_source, j.hashtags_verified = tags, source if tags else "", verified

    ctx.update_job(save)
    state = "đã kiểm tra trên TikTok" if verified else "chưa xác minh"
    ctx.log(f"hashtags: {' '.join(tags) or '(không có)'} ({source or 'bỏ qua'}, {state})")
    ctx.report(1, " ".join(tags) or "Không lấy được hashtag")
