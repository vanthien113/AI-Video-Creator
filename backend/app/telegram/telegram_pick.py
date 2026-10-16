"""Pick the product photos from Telegram: a numbered collage with one button per photo, then "Bắt đầu".

The web UI's pick panel keeps working; whichever picks first wins, and a tap on stale buttons
removes them. Button data is "p:<token>:<index>" (toggle) or "g:<token>" (go), under Telegram's 64 bytes.
"""

import math
import secrets
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import AppConfig
from ..job_actions import InvalidAction
from ..job_models import PICK_GATE, JobStatus
from .telegram_api import TelegramApiError

TILE = 320
COLUMNS = 4
BUTTONS_PER_ROW = 4


# ---- pure parts ---------------------------------------------------------------

def toggle(selection: list[str], name: str, limit: int) -> list[str]:
    """Tick or untick `name`, keeping click order (first = main image); past `limit` nothing changes."""
    if name in selection:
        return [n for n in selection if n != name]
    return [*selection, name] if len(selection) < limit else list(selection)


def keyboard(names: list[str], selection: list[str], token: str) -> dict:
    buttons = []
    for i, name in enumerate(names):
        order = selection.index(name) + 1 if name in selection else 0
        label = str(i + 1) if not order else f"✅{i + 1}·{'chính' if order == 1 else order}"
        buttons.append({"text": label, "callback_data": f"p:{token}:{i}"})
    rows = [buttons[i:i + BUTTONS_PER_ROW] for i in range(0, len(buttons), BUTTONS_PER_ROW)]
    go = f"▶ Bắt đầu với {len(selection)} ảnh" if selection else "Chọn ảnh rồi bấm Bắt đầu"
    return {"inline_keyboard": [*rows, [{"text": go, "callback_data": f"g:{token}"}]]}


def parse(data: str) -> tuple[str, str, int | None] | None:
    parts = (data or "").split(":")
    if len(parts) == 2 and parts[0] == "g":
        return "g", parts[1], None
    if len(parts) == 3 and parts[0] == "p" and parts[2].isdigit():
        return "p", parts[1], int(parts[2])
    return None


def make_collage(paths: list[Path], out: Path) -> Path:
    """All candidates in one image, 4 per row, each with its number in the corner."""
    rows = math.ceil(len(paths) / COLUMNS)
    sheet = Image.new("RGB", (COLUMNS * TILE, rows * TILE), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=40)
    for i, path in enumerate(paths):
        x, y = (i % COLUMNS) * TILE, (i // COLUMNS) * TILE
        with Image.open(path) as img:
            photo = img.convert("RGB")
        photo.thumbnail((TILE - 8, TILE - 8))
        sheet.paste(photo, (x + (TILE - photo.width) // 2, y + (TILE - photo.height) // 2))
        draw.ellipse((x + 10, y + 10, x + 74, y + 74), fill=(47, 91, 216), outline="white", width=3)
        draw.text((x + 42, y + 42), str(i + 1), font=font, fill="white", anchor="mm")
    sheet.save(out, quality=88)
    return out


# ---- Telegram side --------------------------------------------------------------

def send_picker(ctx, api) -> None:
    """At the pick gate: send the collage + buttons as a reply under the link message."""
    job, origin = ctx.job, ctx.job.telegram
    names = job.source.candidates
    collage = make_collage([ctx.path("candidates") / n for n in names], ctx.path("candidates-collage.jpg"))
    token = secrets.token_hex(4)
    limit = ctx.config.flow.max_ingredients
    caption = (f"{job.source.title or 'Sản phẩm TikTok'}\n\nBấm số để chọn tối đa {limit} ảnh "
               "(ảnh bấm đầu là ảnh chính), rồi bấm Bắt đầu. Chọn trên giao diện tool cũng được.")
    message_id = api.send_photo(origin.chat_id, collage, caption, reply_to=origin.message_id,
                                reply_markup=keyboard(names, [], token))

    def remember(j) -> None:
        j.telegram.pick_token, j.telegram.pick_message_id, j.telegram.pick_selection = token, message_id, []

    ctx.update_job(remember)


class PickHandler:
    """Turns a button tap into a toast text; edits the picker message as the selection changes."""

    def __init__(self, actions, api, config: AppConfig):
        self.actions, self.api, self.config = actions, api, config

    def handle(self, callback: dict) -> str:
        parsed = parse(callback.get("data", ""))
        message = callback.get("message") or {}
        chat_id, message_id = (message.get("chat") or {}).get("id"), message.get("message_id")
        if not parsed or chat_id is None:
            return ""
        kind, token, index = parsed
        job = next((j for j in self.actions.store.list() if j.telegram and j.telegram.pick_token == token), None)
        if job is None or not (job.status == JobStatus.awaiting_review and job.gate == PICK_GATE):
            self._edit(self.api.edit_caption, chat_id, message_id, "Job này không còn chờ chọn ảnh.")
            return "Job này không còn chờ chọn ảnh."
        names, selection = job.source.candidates, job.telegram.pick_selection
        limit = self.config.flow.max_ingredients

        if kind == "p":
            if index >= len(names):
                return ""
            chosen = toggle(selection, names[index], limit)
            if chosen == selection:
                return f"Chọn tối đa {limit} ảnh."
            self.actions.store.update(job.id, lambda j: setattr(j.telegram, "pick_selection", chosen))
            self._edit(self.api.edit_reply_markup, chat_id, message_id, keyboard(names, chosen, token))
            return f"Đã chọn {len(chosen)}/{limit} ảnh"

        if not selection:
            return "Chọn ít nhất 1 ảnh trước."
        try:
            self.actions.pick_image(job.id, candidate=selection[0], extras=selection[1:])
        except InvalidAction as exc:
            return str(exc)[:190]
        numbers = ", ".join(str(names.index(n) + 1) for n in selection)
        self._edit(self.api.edit_caption, chat_id, message_id,
                   f"✅ Đã chọn ảnh {numbers} (ảnh {names.index(selection[0]) + 1} là ảnh chính). Đang tạo video…")
        return "Bắt đầu!"

    @staticmethod
    def _edit(method, *args) -> None:
        try:
            method(*args)
        except TelegramApiError:
            pass  # e.g. "message is not modified" or the message was deleted: the pick itself already happened
