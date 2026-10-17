"""User actions on a job (approve, retry, continue, manual video, cancel).

Every status check runs inside the store lock together with the change it guards,
so an action can never act on a state the worker has already moved past.
"""

import json
from collections.abc import Callable

from .job_models import (FLOW_STEPS, PICK_GATE, STEPS, FlowState, JobState, JobStatus, TikTokDraftState,
                         TikTokPostState)
from .job_store import JobStore
from .media.video_probe import probe_video
from .pipeline_runner import PipelineRunner

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
FLOW_GENERATE_INDEX = STEPS.index("flow_generate")


class InvalidAction(ValueError):
    pass


def write_json_atomic(path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class JobActions:
    def __init__(self, store: JobStore, runner: PipelineRunner):
        self.store, self.runner = store, runner

    def approve(self, job_id: str, prompt_text: str | None = None) -> JobState:
        def mutate(j: JobState) -> None:
            if j.status != JobStatus.awaiting_review:
                raise InvalidAction("Job không ở trạng thái chờ duyệt.")
            if j.gate == PICK_GATE:
                raise InvalidAction("Hãy chọn ảnh sản phẩm trước.")
            if j.gate == "prompt" and prompt_text is not None:
                if not prompt_text.strip():
                    raise InvalidAction("Prompt không được để trống.")
                path = self.store.job_dir(job_id) / "prompt.json"
                data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                write_json_atomic(path, {**data, "prompt": prompt_text.strip()})
            self._queue(j)

        return self._apply(job_id, mutate)

    def retry(self, job_id: str, step: str, feedback: str = "", next_cutout_model: bool = False,
              new_image: tuple[str, bytes] | None = None) -> JobState:
        if step not in STEPS:
            raise InvalidAction(f"Bước không hợp lệ: {step}")
        suffix = ""
        if new_image:
            suffix = "." + new_image[0].rsplit(".", 1)[-1].lower() if "." in new_image[0] else ""
            if suffix not in IMAGE_SUFFIXES:
                raise InvalidAction(f"Định dạng ảnh không hỗ trợ: {new_image[0]}")
            step = "cutout"  # a new image invalidates every later artifact

        def mutate(j: JobState) -> None:
            self._require_idle(j)
            if j.status in (JobStatus.running, JobStatus.queued):
                raise InvalidAction("Job đang chạy hoặc đang chờ lượt.")
            if STEPS.index(step) > STEPS.index(j.current_step) and j.status != JobStatus.done:
                raise InvalidAction("Không thể nhảy qua bước chưa chạy.")
            if step == "fetch_source" and j.source is None:
                raise InvalidAction("Job này không tạo từ link nên không có bước đọc TikTok.")
            if not j.input_file and STEPS.index(step) > STEPS.index("fetch_source") and not new_image:
                raise InvalidAction("Job chưa có ảnh sản phẩm, hãy chọn ảnh trước.")
            if new_image:
                job_dir = self.store.job_dir(job_id)
                staged = job_dir / f"input-new{suffix}"
                staged.write_bytes(new_image[1])
                for old in job_dir.glob("input.*"):
                    old.unlink()
                staged.replace(job_dir / f"input{suffix}")
                j.input_file, j.cutout_model_index = f"input{suffix}", 0
            elif next_cutout_model:
                j.cutout_model_index += 1
            if STEPS.index(step) <= FLOW_GENERATE_INDEX:
                j.flow = FlowState(project_url=j.flow.project_url)  # an explicit re-run may submit again
            if STEPS.index(step) <= STEPS.index("export"):
                j.tiktok = TikTokDraftState()  # a new video gets its own draft
                j.post = TikTokPostState()  # ... and may be posted again
            elif step == "tiktok_post" and not j.post.done_at:
                j.post.recheck_since = j.post.submitted_at  # the next run looks for that post first
                j.post.submitted_at = None  # the UI warned that this may post twice
            j.current_step, j.feedback = step, feedback.strip()
            self._queue(j)

        return self._apply(job_id, mutate)

    def continue_after_manual_fix(self, job_id: str) -> JobState:
        def mutate(j: JobState) -> None:
            self._require_idle(j)
            if j.status != JobStatus.failed or not j.error or j.error.step not in FLOW_STEPS:
                raise InvalidAction("Chỉ dùng được khi bước Flow bị lỗi.")
            j.current_step = j.error.step
            if j.current_step == "flow_generate" and j.flow.project_url:
                j.flow.resume = True  # watch for the result instead of submitting again
            self._queue(j)

        return self._apply(job_id, mutate)

    def attach_manual_video(self, job_id: str, data: bytes) -> JobState:
        def allowed(j: JobState) -> None:
            self._require_idle(j)
            flow_failed = j.status == JobStatus.failed and j.error and j.error.step in FLOW_STEPS
            reviewing = j.status == JobStatus.awaiting_review and j.gate == "flow_video"
            if not (flow_failed or reviewing):
                raise InvalidAction("Chỉ tải video thủ công khi bước Flow lỗi hoặc đang duyệt video Flow.")

        self.store.update(job_id, allowed, persist=False)
        target = self.store.job_dir(job_id) / "flow-raw.mp4"
        tmp = target.with_suffix(".upload.mp4")
        tmp.write_bytes(data)
        try:
            probe_video(tmp)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise InvalidAction(f"File không phải video hợp lệ: {exc}") from exc

        def accept(j: JobState) -> None:
            allowed(j)  # re-check: state may have changed while probing
            tmp.replace(target)
            j.current_step, j.status = "flow_download", JobStatus.running

        self._apply(job_id, accept)
        self.runner.advance(job_id, "flow_download")
        self.runner.wake()
        return self.store.get(job_id)

    def cancel(self, job_id: str) -> JobState:
        def mutate(j: JobState) -> None:
            if j.status in (JobStatus.done, JobStatus.cancelled):
                raise InvalidAction("Job đã kết thúc.")
            if j.current_step == "tiktok_post" and j.post.submitted_at and not j.post.done_at:
                raise InvalidAction("Tool đã bấm Post/Schedule, không huỷ được nữa. Xem kết quả trên TikTok Studio.")
            j.status = JobStatus.cancelled

        return self._apply(job_id, mutate)

    # ---- helpers ----------------------------------------------------------
    def _require_idle(self, j: JobState) -> None:
        if self.runner.is_active(j.id):
            raise InvalidAction("Bước hiện tại của job vẫn đang chạy, đợi nó dừng hẳn rồi thử lại.")

    @staticmethod
    def _queue(j: JobState) -> None:
        j.status, j.gate, j.error, j.progress, j.message = JobStatus.queued, None, None, 0, ""

    def _apply(self, job_id: str, mutate: Callable[[JobState], None]) -> JobState:
        job = self.runner.publish_update(job_id, mutate)
        self.runner.wake()
        return job
