"""Pure builders for the ffmpeg / RIFE command lines used by the enhance step."""

from pathlib import Path

FRAME_PATTERN = "%08d.png"


def target_size(width: int, height: int, long_edge: int) -> tuple[int, int]:
    """Scale so the long edge equals `long_edge`, keep aspect, force even dimensions."""
    if width >= height:
        return long_edge, max(2, round(long_edge * height / width / 2) * 2)
    return max(2, round(long_edge * width / height / 2) * 2), long_edge


def target_frame_count(duration: float, fps: int) -> int:
    return max(2, round(duration * fps))


def extract_frames_command(src: Path, out_dir: Path) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-fps_mode", "passthrough", str(out_dir / FRAME_PATTERN)]


def rife_command(rife_bin: Path, model_dir: Path, in_dir: Path, out_dir: Path, frame_count: int) -> list[str]:
    return [
        str(rife_bin), "-i", str(in_dir), "-o", str(out_dir), "-m", str(model_dir),
        "-n", str(frame_count), "-f", FRAME_PATTERN,
    ]


def preview_command(src: Path, out: Path, size: tuple[int, int]) -> list[str]:
    """Small H.264 copy that plays inline on phones (Telegram), audio re-encoded to AAC."""
    width, height = size
    return [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-maxrate", "12M", "-bufsize", "24M",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
    ]


def encode_command(
    frames_dir: Path, audio_src: Path, has_audio: bool, fps: int,
    size: tuple[int, int], bitrate: str, out: Path,
) -> list[str]:
    width, height = size
    args = ["ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-framerate", str(fps),
            "-i", str(frames_dir / FRAME_PATTERN)]
    if has_audio:
        args += ["-i", str(audio_src)]
    args += [
        "-map", "0:v:0",
        "-vf", f"scale={width}:{height}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0,format=yuv420p",
        "-c:v", "hevc_videotoolbox", "-b:v", bitrate, "-tag:v", "hvc1", "-r", str(fps),
    ]
    if has_audio:
        args += ["-map", "1:a:0", "-c:a", "copy", "-shortest"]
    args += ["-movflags", "+faststart", str(out)]
    return args
