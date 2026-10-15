import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import AppConfig, PathsConfig  # noqa: E402
from app.job_models import JobState  # noqa: E402
from app.steps.step_types import JobContext  # noqa: E402


@pytest.fixture
def make_config(tmp_path):
    def build(**overrides) -> AppConfig:
        paths = PathsConfig(
            export_dir=tmp_path / "export", rules_file=tmp_path / "rules.md",
            jobs_dir=tmp_path / "jobs", chrome_profile=tmp_path / "chrome",
        )
        return AppConfig(paths=paths, **overrides)

    return build


@pytest.fixture
def make_context(tmp_path, make_config):
    def build(job: JobState | None = None, config: AppConfig | None = None) -> JobContext:
        job = job or JobState(id="t", name="sample", input_file="input.png", created_at="2026-01-01T00:00:00")
        job_dir = tmp_path / "job"
        job_dir.mkdir(exist_ok=True)
        holder = {"job": job, "reports": []}

        def update(fn):
            fn(holder["job"])
            return holder["job"]

        ctx = JobContext(
            job=job, job_dir=job_dir, config=config or make_config(),
            report=lambda p, m: holder["reports"].append((p, m)),
            log=lambda line: None, update_job=update,
        )
        ctx.holder = holder
        return ctx

    return build


def make_test_clip(path: Path, width=640, height=360, seconds=2, fps=24, audio=True) -> Path:
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"testsrc2=size={width}x{height}:rate={fps}:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True)
    return path
