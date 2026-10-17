"""Actions for jobs created from a TikTok Shop link: create from a link, pick the product image."""

from .config import AppConfig
from .job_actions import IMAGE_SUFFIXES, InvalidAction, JobActions
from .job_models import GATES, PICK_GATE, JobState, JobStatus, TelegramOrigin, now_iso
from .job_store import JobStore
from .media.image_io import load_rgb
from .pipeline_runner import PipelineRunner
from .tiktok.post_plan import job_product_id

FINISHED = (JobStatus.done, JobStatus.cancelled, JobStatus.failed)
POST_MODES = ("now", "schedule")


class LinkJobActions(JobActions):
    def __init__(self, store: JobStore, runner: PipelineRunner, config: AppConfig):
        super().__init__(store, runner)
        self.config = config

    def create_from_link(self, url: str, telegram: TelegramOrigin | None = None) -> JobState | None:
        """New link job, or None when the same link is already waiting or running."""
        with self.store.lock:
            for job in self.store.list():
                if job.source and job.source.url == url and job.status not in FINISHED:
                    return None
            auto = self.config.telegram.auto_review
            gates = {g: True for g in GATES} if auto else self.config.review.auto_gates()
            label = "tiktok-" + url.rstrip("/").rsplit("/", 1)[-1].split("?")[0][-20:]
            job = self.store.create_link_job(url, label, gates, telegram)
        self.runner.publish_update(job.id, lambda j: None)
        self.runner.wake()
        return job

    def pick_image(self, job_id: str, candidate: str | None = None, upload: tuple[str, bytes] | None = None,
                   product_info: str | None = None, extras: list[str] | None = None) -> JobState:
        """`candidate` (or `upload`) is the main image; `extras` are more candidates sent to Flow as-is."""
        extras = list(extras or [])
        if not candidate and not upload:
            raise InvalidAction("Chọn một ảnh hoặc tải ảnh của bạn lên.")
        job = self.store.get(job_id)
        self._check_pickable(job, candidate)
        self._check_extras(job, candidate, extras)
        job_dir = self.store.job_dir(job_id)
        if candidate:
            suffix = ".jpg"
            try:
                data = (job_dir / "candidates" / candidate).read_bytes()
            except OSError as exc:
                raise InvalidAction("Ảnh này không còn trên máy, hãy chạy lại bước Đọc TikTok.") from exc
        else:
            suffix = "." + upload[0].rsplit(".", 1)[-1].lower() if "." in upload[0] else ""
            if suffix not in IMAGE_SUFFIXES:
                raise InvalidAction(f"Định dạng ảnh không hỗ trợ: {upload[0]}")
            data = upload[1]

        # Heavy file work happens outside the store lock; inside it we only swap files and flip state.
        staged = job_dir / f"input-staged{suffix}"
        staged.write_bytes(data)
        try:
            load_rgb(staged)
        except Exception as exc:
            staged.unlink(missing_ok=True)
            raise InvalidAction("File không phải ảnh hợp lệ.") from exc
        staged_extras = []
        for i, name in enumerate(extras, 1):
            staged_extras.append((job_dir / f"staged-ingredient-{i}.jpg", f"ingredient-{i}.jpg"))
            try:
                staged_extras[-1][0].write_bytes((job_dir / "candidates" / name).read_bytes())
            except OSError as exc:
                self._discard(staged, staged_extras)
                raise InvalidAction("Ảnh này không còn trên máy, hãy chạy lại bước Đọc TikTok.") from exc

        def mutate(j: JobState) -> None:
            try:
                self._require_idle(j)
                self._check_pickable(j, candidate)
            except InvalidAction:
                self._discard(staged, staged_extras)
                raise
            for old in [*job_dir.glob("input.*"), *job_dir.glob("ingredient-*")]:
                old.unlink()
            staged.replace(job_dir / f"input{suffix}")
            for path, final in staged_extras:
                path.replace(job_dir / final)
            j.input_file, j.cutout_model_index = f"input{suffix}", 0
            j.extra_ingredients = [final for _, final in staged_extras]
            if product_info is not None:
                j.product_info = product_info.strip()[:2000]
            j.current_step = "cutout"
            self._queue(j)

        return self._apply(job_id, mutate)

    def request_post(self, job_id: str, mode: str) -> JobState:
        """Đăng ngay / Lên lịch from the tool or Telegram: queue the tiktok_post step of a finished link job, once."""
        if mode not in POST_MODES:
            raise InvalidAction("Chế độ đăng không hợp lệ.")

        def mutate(j: JobState) -> None:
            self._require_idle(j)
            if j.post.mode:
                raise InvalidAction("Video này đã được yêu cầu đăng.")
            if j.status != JobStatus.done:
                raise InvalidAction("Chỉ đăng được khi job đã xong.")
            if j.source is None:
                raise InvalidAction("Chỉ job tạo từ link TikTok Shop mới đăng được (cần ID sản phẩm để Add link).")
            if not job_product_id(j):
                raise InvalidAction("Không biết ID sản phẩm của job này; chạy lại bước Đọc TikTok.")
            j.post.mode, j.post.requested_at = mode, now_iso()
            j.current_step = "tiktok_post"
            self._queue(j)

        return self._apply(job_id, mutate)

    def _check_extras(self, j: JobState, main: str | None, extras: list[str]) -> None:
        limit = self.config.flow.max_ingredients
        if len(extras) + 1 > limit:
            raise InvalidAction(f"Chọn tối đa {limit} ảnh cho một video (flow.max_ingredients).")
        if len(set(extras)) != len(extras) or (main and main in extras):
            raise InvalidAction("Mỗi ảnh chỉ chọn một lần.")
        if extras and (not j.source or any(x not in j.source.candidates for x in extras)):
            raise InvalidAction("Ảnh đã chọn không thuộc job này.")

    @staticmethod
    def _discard(staged, staged_extras) -> None:
        staged.unlink(missing_ok=True)
        for path, _ in staged_extras:
            path.unlink(missing_ok=True)

    @staticmethod
    def _check_pickable(j: JobState, candidate: str | None) -> None:
        picking = j.status == JobStatus.awaiting_review and j.gate == PICK_GATE
        fetch_failed = j.status == JobStatus.failed and j.error and j.error.step == "fetch_source"
        if not (picking or fetch_failed):
            raise InvalidAction("Job không ở bước chọn ảnh.")
        if candidate and (not j.source or candidate not in j.source.candidates):
            raise InvalidAction("Ảnh đã chọn không thuộc job này.")
