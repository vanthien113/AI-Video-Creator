"""Single worker that moves queued jobs through the steps, pausing at review gates."""

import threading
import traceback
from collections.abc import Callable

from .config import AppConfig
from .event_bus import EventBus
from .job_models import GATE_AFTER_STEP, JobError, JobState, JobStatus, StepRecord, next_step, now_iso
from .job_store import JobStore
from .steps.step_types import JobContext, StepFailure, StepFn


class PipelineRunner:
    def __init__(self, store: JobStore, bus: EventBus, config: AppConfig, steps: dict[str, StepFn]):
        self.store, self.bus, self.config, self.steps = store, bus, config, steps
        self.active_job_id: str | None = None  # only changed under the store lock
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="pipeline-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def recover(self) -> None:
        """Called once at startup: re-queue jobs interrupted mid-step, never resubmit to Flow."""
        for job in self.store.list():
            if job.status != JobStatus.running:
                continue
            self.store.update(job.id, lambda j: self._close_record(j, j.current_step, "interrupted"))
            if job.current_step == "flow_generate" and job.flow.video_ref:
                self.advance(job.id, "flow_generate")  # video already exists; continue to download
            elif job.current_step == "flow_generate" and job.flow.submitted_at:
                self.fail(job.id, "flow_generate",
                          "Đã gửi lên Flow trước khi tắt tool — kiểm tra trên Flow rồi chọn "
                          "'Tôi đã sửa tay, tiếp tục' hoặc 'Thử lại' (sinh lại, tốn credit).")
            else:
                self.store.update(job.id, lambda j: setattr(j, "status", JobStatus.queued))

    # ---- worker loop ------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self.store.next_queued()
            if job is None:
                self._wake.wait(timeout=2)
                self._wake.clear()
                continue
            try:
                self.run_one(job)
            except Exception:  # never let the worker thread die silently
                traceback.print_exc()
                try:
                    self.fail(job.id, job.current_step, "Lỗi nội bộ của tool, xem terminal.")
                except Exception:
                    traceback.print_exc()
            finally:
                self._set_active(None)

    def run_one(self, job: JobState) -> None:
        step_name = job.current_step
        claimed = False

        def begin(j: JobState) -> None:
            nonlocal claimed
            if j.status != JobStatus.queued:  # cancelled or changed since we picked it
                return
            claimed = True
            self.active_job_id = j.id
            j.status, j.gate, j.error, j.progress, j.message = JobStatus.running, None, None, 0, ""
            j.history.append(StepRecord(step=step_name, started_at=now_iso()))

        job = self.publish_update(job.id, begin)
        if not claimed:
            return
        ctx = JobContext(
            job=job, job_dir=self.store.job_dir(job.id), config=self.config,
            report=lambda p, m: self._report(job.id, p, m),
            log=lambda line: self._log(job.id, line),
            update_job=lambda fn: self.store.update(job.id, fn),
            is_cancelled=lambda: self.store.get(job.id).status == JobStatus.cancelled,
        )
        ctx.log(f"▶ {step_name}")
        try:
            self.steps[step_name](ctx)
        except StepFailure as exc:
            ctx.log(f"✖ {step_name}: {exc.reason}")
            self.fail(job.id, step_name, exc.reason, exc.screenshot)
            return
        except Exception as exc:  # unexpected bug: keep the worker alive, surface it on the job
            ctx.log(traceback.format_exc())
            self.fail(job.id, step_name, f"Lỗi không mong đợi: {exc}")
            return
        ctx.log(f"✔ {step_name}")
        self.advance(job.id, step_name)

    def advance(self, job_id: str, finished_step: str) -> None:
        def mutate(j: JobState) -> None:
            self._close_record(j, finished_step, "ok")
            self._release(j)
            if j.status == JobStatus.cancelled or j.current_step != finished_step:
                return  # cancelled, or state moved on: a stale result must not overwrite it
            j.feedback, j.progress, j.message, j.error, j.flow.resume = "", 1, "", None, False
            following = next_step(finished_step)
            if following is None:
                j.status = JobStatus.done
                return
            j.current_step = following
            gate = GATE_AFTER_STEP.get(finished_step)
            if gate and not j.auto_gates.get(gate, False):
                j.status, j.gate = JobStatus.awaiting_review, gate
            else:
                j.status, j.gate = JobStatus.queued, None

        self.publish_update(job_id, mutate)

    def fail(self, job_id: str, step: str, reason: str, screenshot: str | None = None) -> None:
        def mutate(j: JobState) -> None:
            self._close_record(j, step, "failed")
            self._release(j)
            if j.status == JobStatus.cancelled:
                return
            j.status, j.current_step, j.gate = JobStatus.failed, step, None
            j.error = JobError(step=step, reason=reason, screenshot=screenshot)

        self.publish_update(job_id, mutate)

    def is_active(self, job_id: str) -> bool:
        """Read under the store lock (call from inside a store.update mutate)."""
        return self.active_job_id == job_id

    # ---- helpers ----------------------------------------------------------
    def _release(self, j: JobState) -> None:
        if self.active_job_id == j.id:
            self.active_job_id = None

    def _set_active(self, job_id: str | None) -> None:
        with self.store.lock:
            self.active_job_id = job_id

    @staticmethod
    def _close_record(j: JobState, step: str, outcome: str) -> None:
        for record in reversed(j.history):
            if record.step == step and record.finished_at is None:
                record.finished_at = now_iso()
                record.outcome = "cancelled" if j.status == JobStatus.cancelled else outcome
                return

    def publish_update(self, job_id: str, mutate: Callable[[JobState], None]) -> JobState:
        job = self.store.update(job_id, mutate)
        self.bus.publish({"type": "job", "job": job.model_dump(mode="json")})
        return job

    def _report(self, job_id: str, progress: float, message: str) -> None:
        def mutate(j: JobState) -> None:
            j.progress, j.message = max(0.0, min(1.0, progress)), message

        self.store.update(job_id, mutate, persist=False)
        self.bus.publish({"type": "progress", "id": job_id, "progress": progress, "message": message})

    def _log(self, job_id: str, line: str) -> None:
        with open(self.store.job_dir(job_id) / "log.txt", "a", encoding="utf-8") as fh:
            fh.write(f"[{now_iso()}] {line}\n")
