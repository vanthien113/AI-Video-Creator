"""Contract every pipeline step follows."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import AppConfig
from ..job_models import JobState


class StepFailure(Exception):
    """Expected failure with a message meant for the user (Vietnamese)."""

    def __init__(self, reason: str, screenshot: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.screenshot = screenshot


@dataclass
class JobContext:
    job: JobState
    job_dir: Path
    config: AppConfig
    report: Callable[[float, str], None]  # (progress 0..1, message)
    log: Callable[[str], None]
    update_job: Callable[[Callable[[JobState], None]], JobState]
    is_cancelled: Callable[[], bool] = field(default=lambda: False)

    def path(self, name: str) -> Path:
        return self.job_dir / name


StepFn = Callable[[JobContext], None]
