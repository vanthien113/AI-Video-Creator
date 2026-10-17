"""Job state schema shared by the store, the pipeline runner and the API."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# "fetch_source" only runs for jobs created from a TikTok Shop link; upload jobs start at "cutout".
# "send_telegram" only does work for jobs that came from Telegram; for the others it is a no-op.
# "tiktok_draft" saves the video as a TikTok Studio draft (never posts) when tiktok.save_draft is on.
# "hashtags" asks Google's AI Mode (Claude as fallback) for 3 hashtags; it never fails the job.
# "tiktok_post" posts or schedules the video on TikTok, only after the user pressed Đăng ngay / Lên lịch;
# until then it only sends those two buttons to Telegram.
STEPS = ["fetch_source", "cutout", "upscale", "prompt", "flow_generate", "flow_download", "enhance", "export",
         "hashtags", "send_telegram", "tiktok_draft", "tiktok_post"]
FIRST_UPLOAD_STEP = "cutout"

# A gate pauses the job right after the step it is keyed by.
# "pick_image" always waits for the user; the review gates can be set to auto per job.
PICK_GATE = "pick_image"
GATE_AFTER_STEP = {"fetch_source": PICK_GATE, "cutout": "cutout", "prompt": "prompt", "flow_download": "flow_video"}
GATES = ["cutout", "prompt", "flow_video"]

FLOW_STEPS = {"flow_generate", "flow_download"}


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    awaiting_review = "awaiting_review"
    failed = "failed"
    done = "done"
    cancelled = "cancelled"


class FlowState(BaseModel):
    project_url: str | None = None
    submitted_at: str | None = None
    known_videos: list[str] = Field(default_factory=list)
    video_ref: str | None = None
    resume: bool = False  # "Tôi đã sửa tay, tiếp tục": watch for the result instead of submitting


class SourceInfo(BaseModel):
    """What the fetch_source step read from the product page."""

    url: str
    title: str = ""
    description: str = ""
    candidates: list[str] = Field(default_factory=list)  # file names in <job>/candidates/
    product_id: str = ""  # from the page address after redirects; short vt.tiktok.com links carry none


class TelegramOrigin(BaseModel):
    """Where a link came from, so the finished video can be sent back as a reply."""

    chat_id: int
    message_id: int | None = None
    preview_sent: bool = False  # parts already delivered: a retry never sends duplicates
    file_sent: bool = False
    title_sent: bool = False
    # Photo picker sent to Telegram at the pick gate (numbered collage + buttons).
    pick_token: str | None = None       # short id carried in the button data (Telegram allows 64 bytes)
    pick_message_id: int | None = None
    pick_selection: list[str] = Field(default_factory=list)  # candidate file names, main image first


class TelegramMessageRef(BaseModel):
    chat_id: int
    message_id: int


class TikTokDraftState(BaseModel):
    saved_at: str | None = None  # draft saved: a retry only re-sends the Telegram note
    notified: bool = False


class TikTokPostState(BaseModel):
    """Đăng ngay / Lên lịch, started by a button in the tool or on Telegram. submitted_at is saved right before
    Post/Schedule is clicked and done_at once the post shows on TikTok Studio, so the tool never clicks twice."""

    mode: Literal["now", "schedule"] | None = None  # None = nobody asked: the step only offers the buttons
    requested_at: str | None = None
    scheduled_for: str | None = None  # local time, e.g. "2026-10-18T19:00:00"
    submitted_at: str | None = None
    done_at: str | None = None
    recheck_since: str | None = None  # click time of an unconfirmed attempt: looked for before posting again
    notified: bool = False  # result message sent on Telegram
    offer_token: str | None = None  # carried in the Telegram button data
    offer_message: TelegramMessageRef | None = None  # the message with the two buttons


class JobError(BaseModel):
    step: str
    reason: str
    screenshot: str | None = None  # file name relative to the job dir


class StepRecord(BaseModel):
    step: str
    started_at: str
    finished_at: str | None = None
    outcome: str = "running"  # running | ok | failed | cancelled


class JobState(BaseModel):
    id: str
    name: str
    input_file: str  # "" until a link job's image has been picked
    extra_ingredients: list[str] = Field(default_factory=list)  # more photos for Flow, e.g. "ingredient-1.jpg"
    created_at: str
    status: JobStatus = JobStatus.queued
    current_step: str = FIRST_UPLOAD_STEP
    gate: str | None = None
    auto_gates: dict[str, bool] = Field(default_factory=lambda: {g: False for g in GATES})
    note: str = ""
    product_info: str = ""  # title + description from the product page, editable at the pick gate
    source: SourceInfo | None = None
    telegram: TelegramOrigin | None = None
    hashtags: list[str] = Field(default_factory=list)  # sent after the title on Telegram
    hashtags_source: str = ""  # "google" | "claude" | "" (none found)
    hashtags_verified: bool = False  # each one checked on TikTok (exists, enough videos)
    status_message: TelegramMessageRef | None = None  # the one Telegram message edited as the job moves on
    tiktok: TikTokDraftState = Field(default_factory=TikTokDraftState)
    post: TikTokPostState = Field(default_factory=TikTokPostState)
    feedback: str = ""
    cutout_model_index: int = 0
    progress: float = 0
    message: str = ""
    history: list[StepRecord] = Field(default_factory=list)
    flow: FlowState = Field(default_factory=FlowState)
    error: JobError | None = None
    export_path: str | None = None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def next_step(step: str) -> str | None:
    index = STEPS.index(step)
    return STEPS[index + 1] if index + 1 < len(STEPS) else None
