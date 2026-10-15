"""Read basic video facts with ffprobe."""

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


def parse_probe(raw: dict) -> VideoInfo:
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("không có luồng hình")
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    fps = float(Fraction(rate)) if rate != "0/0" else 0.0
    duration = float(video.get("duration") or raw.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("thời lượng bằng 0")
    return VideoInfo(
        width=int(video["width"]), height=int(video["height"]), fps=fps, duration=duration,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def probe_video(path: Path) -> VideoInfo:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip()[-300:] or "ffprobe lỗi")
    return parse_probe(json.loads(result.stdout))
