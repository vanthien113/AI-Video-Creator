"""Steps 4 and 5: generate the video on Google Flow, then download it."""

import json
import time

from ..flow.flow_agent import agent_request, approve_plan, configure_agent, start_new_session
from ..flow.flow_client import FlowClient, FlowError, flow_session
from ..flow.cdp_connection import capture_page_error
from ..flow.flow_results import download_video, list_videos, stable_video_ref, wait_for_new_video
from ..job_models import JobState, now_iso
from ..media.video_probe import probe_video
from .step_types import JobContext, StepFailure


def _read_prompt(ctx: JobContext) -> str:
    path = ctx.path("prompt.json")
    if not path.exists():
        raise StepFailure("Thiếu prompt.json, chạy lại bước Prompt.")
    return json.loads(path.read_text(encoding="utf-8"))["prompt"]


def _run_on_flow(ctx: JobContext, action) -> object:
    """Run `action(client)`; any Flow/Playwright error becomes a StepFailure with a screenshot."""
    from playwright.sync_api import Error as PlaywrightError

    try:
        with flow_session(ctx.config.flow) as client:
            try:
                return action(client)
            except (FlowError, PlaywrightError) as exc:
                shot = capture_page_error(client.page, ctx.path("errors"))
                message = str(exc) if isinstance(exc, FlowError) else f"Thao tác trên Flow lỗi: {str(exc).splitlines()[0]}"
                raise StepFailure(message, screenshot=shot) from exc
    except (FlowError, PlaywrightError) as exc:  # failed while connecting, before a page exists
        raise StepFailure(str(exc).splitlines()[0]) from exc


def run_flow_generate(ctx: JobContext) -> None:
    cfg = ctx.config.flow
    job = ctx.job
    if job.flow.submitted_at and not job.flow.resume:
        # Only an explicit retry (which clears submitted_at) may submit again.
        raise StepFailure("Job này đã gửi lên Flow. Chọn 'Tôi đã sửa tay, tiếp tục' hoặc 'Thử lại' (tốn credit).")
    prompt = _read_prompt(ctx)
    image = ctx.path("product-2k.png")

    def action(client: FlowClient) -> str:
        project_url = client.open_project(job.flow.project_url or cfg.project_url or None)
        ctx.log(f"flow: project {project_url}")
        if job.flow.resume:
            ctx.report(0.3, "Theo dõi kết quả sau khi sửa tay")
            known = set(job.flow.known_videos)
        else:
            known = set(list_videos(client))  # recorded before upload so a later "continue" can tell old from new

            def opened(j: JobState) -> None:
                j.flow.project_url, j.flow.known_videos = project_url, sorted(known)

            ctx.update_job(opened)
            ctx.report(0.05, "Thiết lập Agent của Flow")
            start_new_session(client)
            ctx.log(f"flow: settings {configure_agent(client, cfg)}")
            stamp = int(time.time())
            images = [(image, f"{job.id}-{stamp}.png")] + [
                (ctx.path(name), f"{job.id}-{stamp}-{name}") for name in job.extra_ingredients if ctx.path(name).exists()]
            ctx.report(0.1, f"Tải {len(images)} ảnh sản phẩm lên Flow")
            client.upload_ingredients(images)
            ctx.report(0.2, "Nhập prompt")
            client.fill_prompt(agent_request(prompt, cfg, image_count=len(images)))

            def mark_submitted(j: JobState) -> None:
                j.flow.submitted_at, j.flow.video_ref, j.flow.resume = now_iso(), None, False

            ctx.update_job(mark_submitted)  # recorded BEFORE clicking: a crash never resubmits
            client.submit()
            ctx.log("flow: submitted to agent")
            ctx.report(0.25, "Chờ Agent của Flow đề xuất")
            credits = approve_plan(client, cfg.max_credits)
            ctx.log(f"flow: approved agent plan ({credits} credit)")
        baseline = client.page.inner_text("body")
        fresh_ref = wait_for_new_video(client, known, cfg.timeout_sec, baseline, ctx.report, ctx.is_cancelled)
        ctx.report(0.97, "Xác nhận video trên Flow")
        return stable_video_ref(client, known, fresh_ref, ctx.log)

    ref = _run_on_flow(ctx, action)

    def done(j: JobState) -> None:
        j.flow.video_ref, j.flow.resume = ref, False

    ctx.update_job(done)
    ctx.log(f"flow: video {ref}")
    ctx.report(1, "Flow đã sinh xong video")


def run_flow_download(ctx: JobContext) -> None:
    cfg = ctx.config.flow
    job = ctx.job
    if not job.flow.video_ref or not job.flow.project_url:
        raise StepFailure("Chưa có video trên Flow để tải. Chạy lại bước sinh video hoặc tải video lên thủ công.")
    tmp = ctx.path("flow-raw.part.mp4")

    def action(client: FlowClient) -> str:
        client.open_project(job.flow.project_url)
        ctx.report(0.2, f"Tải video ({cfg.download})")
        return download_video(client, job.flow.video_ref, cfg.download, tmp, ctx.log)

    got = _run_on_flow(ctx, action)
    try:
        info = probe_video(tmp)
    except ValueError as exc:
        tmp.unlink(missing_ok=True)
        raise StepFailure(f"File tải về không phải video hợp lệ: {exc}") from exc
    tmp.replace(ctx.path("flow-raw.mp4"))
    ctx.log(f"flow_download: {got} {info}")
    ctx.report(1, f"Đã tải video {info.width}×{info.height} ({got})")
