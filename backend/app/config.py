"""Load and validate config.yaml into typed settings."""

from pathlib import Path
from typing import Literal

import os

import yaml
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = ROOT / "bin"

ReviewMode = Literal["manual", "auto"]


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


class ServerConfig(BaseModel):
    port: int = 8765


class PathsConfig(BaseModel):
    export_dir: Path
    rules_file: Path
    jobs_dir: Path
    chrome_profile: Path

    @field_validator("*", mode="before")
    @classmethod
    def _resolve(cls, value):
        return resolve_path(value)


class ImageConfig(BaseModel):
    long_edge: int = Field(2048, ge=256, le=8192)
    background: Literal["white", "transparent"] = "white"
    padding: float = Field(0.08, ge=0, le=0.5)
    cutout_models: list[str] = Field(default_factory=lambda: ["birefnet-general", "isnet-general-use"], min_length=1)


class PromptConfig(BaseModel):
    timeout_sec: int = Field(180, ge=10)
    model: str = ""


class FlowConfig(BaseModel):
    project_url: str = ""
    model: str = "Veo 3.1 - Fast"
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"
    resolution: str = ""  # e.g. "720p"; empty = model default (only some models offer a choice)
    duration: str = ""    # e.g. "8s"; empty = model default
    outputs: int = Field(1, ge=1, le=4)
    max_ingredients: int = Field(3, ge=1, le=5)  # main product image + extra reference images
    max_credits: int = Field(20, ge=1)  # agent plans costing more are rejected
    download: Literal["1080p", "original"] = "1080p"
    timeout_sec: int = Field(600, ge=60)
    cdp_port: int = 9222
    chrome_app: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class VideoConfig(BaseModel):
    fps: int = Field(60, ge=24, le=120)
    long_edge: int = Field(3840, ge=720, le=7680)
    rife_model: str = "rife-v4.6"
    bitrate: str = "45M"
    min_free_gb: float = 3

    @property
    def label(self) -> str:
        """Name of the output size for file names and messages: 3840 → "4K", 2560 → "2K", 1920 → "1080p"."""
        return {3840: "4K", 2560: "2K", 1920: "1080p", 1280: "720p"}.get(self.long_edge, f"{self.long_edge}p")


class LogoConfig(BaseModel):
    """Our logo over Flow's ✦ mark, placed as fractions of the frame so it fits any output size.
    Defaults measured on five 720×1280 Flow downloads (2026-10-16): the mark is 48×48 px centred at
    (599.5, 1159.5); a 60 px circle there covers it with a little margin."""

    enabled: bool = False
    file: Path = Path("assets/logo.png")
    center_x: float = Field(0.8326, gt=0, lt=1)  # 599.5 / 720
    center_y: float = Field(0.9059, gt=0, lt=1)  # 1159.5 / 1280
    width: float = Field(0.0833, gt=0, lt=1)     # logo diameter: 60 / 720 of the frame width

    @field_validator("file", mode="before")
    @classmethod
    def _resolve(cls, value):
        return resolve_path(value)


class ReviewConfig(BaseModel):
    cutout: ReviewMode = "manual"
    prompt: ReviewMode = "manual"
    flow_video: ReviewMode = "manual"

    def auto_gates(self) -> dict[str, bool]:
        return {gate: mode == "auto" for gate, mode in self.model_dump().items()}


class TelegramConfig(BaseModel):
    enabled: bool = True
    allowed_user_ids: list[int] = Field(default_factory=list)
    auto_review: bool = True  # link jobs run straight through after the image is picked

    @property
    def bot_token(self) -> str:
        return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    @property
    def user_ids(self) -> list[int]:
        """allowed_user_ids plus TELEGRAM_ALLOWED_USER_IDS from .env (comma separated), which keeps IDs out of git."""
        from_env = [int(x) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").replace(",", " ").split() if x.isdigit()]
        return list(dict.fromkeys([*self.allowed_user_ids, *from_env]))


class TikTokConfig(BaseModel):
    save_draft: bool = True  # after export: upload to TikTok Studio and Save draft (never Post)
    upload_url: str = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"
    ai_generated_label: bool = True  # TikTok may take down realistic AI video that is not labelled
    timeout_sec: int = Field(600, ge=60)  # upload + processing of the exported file


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    paths: PathsConfig
    image: ImageConfig = ImageConfig()
    prompt: PromptConfig = PromptConfig()
    flow: FlowConfig = FlowConfig()
    video: VideoConfig = VideoConfig()
    review: ReviewConfig = ReviewConfig()
    telegram: TelegramConfig = TelegramConfig()
    tiktok: TikTokConfig = TikTokConfig()
    logo: LogoConfig = LogoConfig()


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal KEY=VALUE loader for secrets kept out of config.yaml; real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not os.environ.get(key):  # an empty exported variable must not hide the file's value
            os.environ[key] = value.strip().strip('"').strip("'")


def load_config(path: Path = ROOT / "config.yaml") -> AppConfig:
    load_dotenv()
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return AppConfig.model_validate(raw)
