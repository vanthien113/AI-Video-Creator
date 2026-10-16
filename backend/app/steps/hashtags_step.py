"""Before the Telegram reply: 3 hashtags for the product, sent after the title so they copy together.

Google's AI Mode first (it reads recent web pages, so it knows what is trending); Claude as a
fallback (relevant, but it cannot know current trends). Never fails the job.
"""

import json

from ..flow.cdp_connection import browser_context, new_tab
from ..media.command_runner import require_tool, run_tool
from ..sources.google_hashtags import parse_hashtags, read_ai_mode, search_query
from .prompt_parsing import result_envelope
from .prompt_step import UNTRUSTED_NOTE, claude_args
from .step_types import JobContext

CLAUDE_ASK = ("Give 3 TikTok hashtags for selling this product in Vietnam: Vietnamese without diacritics, "
              "most relevant first. Reply with one line only, like: #a #b #c\n"
              "<shop_page>\n{title}\n</shop_page>\n" + UNTRUSTED_NOTE)


def from_google(ctx: JobContext, title: str) -> list[str]:
    with browser_context(ctx.config.flow.cdp_port) as context:
        page = new_tab(context)  # background tab: Chrome stays behind the user's work
        try:
            items, text = read_ai_mode(page, search_query(title))
        finally:
            page.close()
    tags = parse_hashtags(items, text)
    if len(tags) < 3:
        raise RuntimeError(f"Google chỉ trả về {len(tags)} hashtag")
    return tags


def from_claude(ctx: JobContext, title: str) -> list[str]:
    message = json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": CLAUDE_ASK.format(title=title)}]}}) + "\n"
    stdout = run_tool(claude_args(require_tool("claude"), ctx.config.prompt.model), timeout=120, cwd=ctx.job_dir,
                      stdin_text=message, should_stop=ctx.is_cancelled, label="claude -p (hashtag)")
    tags = parse_hashtags([], str(result_envelope(stdout).get("result", "")))
    if len(tags) < 3:
        raise RuntimeError(f"Claude chỉ trả về {len(tags)} hashtag")
    return tags


def run_hashtags(ctx: JobContext) -> None:
    title = ctx.job.source.title if ctx.job.source else ""
    if not title:
        return
    tags, source = [], ""
    for name, fetch in (("google", from_google), ("claude", from_claude)):
        ctx.report(0.2 if name == "google" else 0.6, f"Tìm hashtag ({name})")
        try:
            tags, source = fetch(ctx, title), name
            break
        except Exception as exc:  # hashtags are a nice-to-have: try the next source, never fail the job
            ctx.log(f"hashtags: {name} lỗi: {str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__}")

    def save(j) -> None:
        j.hashtags, j.hashtags_source = tags, source

    ctx.update_job(save)
    ctx.log(f"hashtags: {' '.join(tags) or '(không có)'} ({source or 'bỏ qua'})")
    ctx.report(1, " ".join(tags) or "Không lấy được hashtag")
