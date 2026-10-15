"""Thread-safe persistence of jobs: one folder per job, state in state.json."""

import re
import threading
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .job_models import JobState, JobStatus, SourceInfo, TelegramOrigin, now_iso

STATE_FILE = "state.json"


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_text = ascii_text.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:40] or "image"


class JobNotFound(KeyError):
    pass


class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.lock = self._lock  # shared with the runner for state that must change atomically with jobs
        self._jobs: dict[str, JobState] = {}
        self._load_all()

    def _load_all(self) -> None:
        for state_path in self.jobs_dir.glob(f"*/{STATE_FILE}"):
            try:
                job = JobState.model_validate_json(state_path.read_text(encoding="utf-8"))
            except ValueError:
                continue  # unreadable job folder: leave it alone, do not crash startup
            self._jobs[job.id] = job

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def _new_job_dir(self, label: str) -> tuple[str, Path]:
        base = f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(label)}"
        job_id, n = base, 2
        while self.job_dir(job_id).exists():
            job_id, n = f"{base}-{n}", n + 1
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True)
        return job_id, job_dir

    def create_link_job(self, url: str, label: str, auto_gates: dict[str, bool],
                        telegram: TelegramOrigin | None = None) -> JobState:
        with self._lock:
            job_id, _ = self._new_job_dir(label)
            job = JobState(
                id=job_id, name=slugify(label), input_file="", created_at=now_iso(),
                current_step="fetch_source", source=SourceInfo(url=url), auto_gates=auto_gates, telegram=telegram,
            )
            self._save(job)
            return job.model_copy(deep=True)

    def create(self, filename: str, data: bytes, note: str, auto_gates: dict[str, bool]) -> JobState:
        stem, suffix = Path(filename).stem, Path(filename).suffix.lower() or ".jpg"
        with self._lock:
            job_id, job_dir = self._new_job_dir(stem)
            input_file = f"input{suffix}"
            (job_dir / input_file).write_bytes(data)
            job = JobState(
                id=job_id, name=stem, input_file=input_file, created_at=now_iso(),
                note=note.strip(), auto_gates=auto_gates,
            )
            self._save(job)
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> JobState:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFound(job_id)
            return self._jobs[job_id].model_copy(deep=True)

    def list(self) -> list[JobState]:
        with self._lock:
            jobs = [j.model_copy(deep=True) for j in self._jobs.values()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def update(self, job_id: str, mutate: Callable[[JobState], None], persist: bool = True) -> JobState:
        """Apply `mutate` to the live state under the lock; return a snapshot."""
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFound(job_id)
            job = self._jobs[job_id]
            mutate(job)
            if persist:
                self._save(job)
            return job.model_copy(deep=True)

    def next_queued(self) -> JobState | None:
        with self._lock:
            queued = [j for j in self._jobs.values() if j.status == JobStatus.queued]
            if not queued:
                return None
            return min(queued, key=lambda j: j.created_at).model_copy(deep=True)

    def _save(self, job: JobState) -> None:
        self._jobs[job.id] = job
        path = self.job_dir(job.id) / STATE_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
