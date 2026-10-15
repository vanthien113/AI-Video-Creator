"""REST endpoints for jobs and the SSE event stream."""

import json
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ..job_actions import InvalidAction
from ..job_models import GATES
from ..job_store import JobNotFound

router = APIRouter(prefix="/api")

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
SERVABLE = re.compile(r"^(input\.\w+|candidates/\d{2}\.jpg|cutout\.png|product-2k\.png|flow-raw\.mp4|final-4k60\.mp4|log\.txt|errors/[\w.-]+\.png)$")


def services(request: Request):
    return request.app.state.services


def job_payload(svc, job) -> dict:
    data = job.model_dump(mode="json")
    prompt_file = svc.store.job_dir(job.id) / "prompt.json"
    try:
        data["prompt"] = json.loads(prompt_file.read_text(encoding="utf-8")) if prompt_file.exists() else None
    except (OSError, ValueError):
        data["prompt"] = None
    return data


def guarded(fn):
    try:
        return fn()
    except JobNotFound as exc:
        raise HTTPException(404, "Không tìm thấy job") from exc
    except InvalidAction as exc:
        raise HTTPException(409, str(exc)) from exc


async def read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File {upload.filename} quá lớn")
    return data


@router.post("/jobs")
async def create_jobs(request: Request, images: list[UploadFile] = File(...), note: str = Form(""),
                      auto_gates: str = Form("{}")):
    svc = services(request)
    try:
        requested = json.loads(auto_gates)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "auto_gates không hợp lệ") from exc
    defaults = svc.config.review.auto_gates()
    gates = {g: bool(requested.get(g, defaults[g])) for g in GATES}
    created = []
    for image in images:
        suffix = "." + (image.filename or "").rsplit(".", 1)[-1].lower()
        if suffix not in IMAGE_TYPES:
            raise HTTPException(400, f"Định dạng không hỗ trợ: {image.filename}")
        data = await read_limited(image, MAX_IMAGE_BYTES)
        created.append(svc.store.create(image.filename, data, note, gates))
    svc.runner.wake()
    for job in created:
        svc.bus.publish({"type": "job", "job": job.model_dump(mode="json")})
    return [job_payload(svc, j) for j in created]


class LinkBody(BaseModel):
    url: str


@router.post("/links")
def create_from_link(request: Request, body: LinkBody):
    """Same as sending the link to the Telegram bot; handy when the phone is not around."""
    svc = services(request)
    url = body.url.strip()
    if not re.match(r"^https?://([\w-]+\.)*tiktok\.com/", url):
        raise HTTPException(400, "Chỉ nhận link TikTok")
    job = svc.actions.create_from_link(url)
    if job is None:
        raise HTTPException(409, "Link này đang có trong hàng chờ rồi")
    return job_payload(svc, job)


@router.post("/jobs/{job_id}/pick")
async def pick_image(request: Request, job_id: str, candidate: str = Form(""), product_info: str | None = Form(None),
                     image: UploadFile | None = File(None), extra: list[str] = Form([])):
    svc = services(request)
    upload = None
    if image is not None and image.filename:
        upload = (image.filename, await read_limited(image, MAX_IMAGE_BYTES))
    return await run_in_threadpool(
        guarded, lambda: job_payload(svc, svc.actions.pick_image(job_id, candidate or None, upload, product_info,
                                                                 [e for e in extra if e])))


@router.get("/jobs")
def list_jobs(request: Request):
    svc = services(request)
    return [job_payload(svc, j) for j in svc.store.list()]


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    svc = services(request)
    return guarded(lambda: job_payload(svc, svc.store.get(job_id)))


@router.get("/jobs/{job_id}/files/{name:path}")
def get_job_file(request: Request, job_id: str, name: str):
    svc = services(request)
    guarded(lambda: svc.store.get(job_id))
    if not SERVABLE.fullmatch(name):
        raise HTTPException(403, "Không được phép tải file này")
    path = svc.store.job_dir(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "Chưa có file")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


class ApproveBody(BaseModel):
    prompt: str | None = None


@router.post("/jobs/{job_id}/approve")
def approve(request: Request, job_id: str, body: ApproveBody):
    svc = services(request)
    return guarded(lambda: job_payload(svc, svc.actions.approve(job_id, body.prompt)))


@router.post("/jobs/{job_id}/retry")
async def retry(request: Request, job_id: str, step: str = Form(...), feedback: str = Form(""),
                next_cutout_model: bool = Form(False), image: UploadFile | None = File(None)):
    svc = services(request)
    new_image = None
    if image is not None and image.filename:
        new_image = (image.filename, await read_limited(image, MAX_IMAGE_BYTES))
    return await run_in_threadpool(
        guarded, lambda: job_payload(svc, svc.actions.retry(job_id, step, feedback, next_cutout_model, new_image)))


@router.post("/jobs/{job_id}/continue")
def continue_job(request: Request, job_id: str):
    svc = services(request)
    return guarded(lambda: job_payload(svc, svc.actions.continue_after_manual_fix(job_id)))


@router.post("/jobs/{job_id}/manual-video")
async def manual_video(request: Request, job_id: str, video: UploadFile = File(...)):
    svc = services(request)
    data = await read_limited(video, MAX_VIDEO_BYTES)
    return await run_in_threadpool(guarded, lambda: job_payload(svc, svc.actions.attach_manual_video(job_id, data)))


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: str):
    svc = services(request)
    return guarded(lambda: job_payload(svc, svc.actions.cancel(job_id)))


@router.get("/events")
async def events(request: Request):
    bus = services(request).bus

    async def stream():
        async for event in bus.subscribe():
            if await request.is_disconnected():
                break
            yield ": ping\n\n" if event is None else f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
