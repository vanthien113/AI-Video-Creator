"""Link jobs: TikTok link → candidates → pick gate → runs straight through."""

import io

import pytest
from PIL import Image

from app.job_actions import InvalidAction
from app.job_models import JobStatus, TelegramOrigin

from .test_pipeline_runner import UPLOAD_STEPS, drain, new_job, rig  # noqa: F401  (fixture re-export)

URL = "https://shop.tiktok.com/vn/pdp/1737628275640009880?_t=abc"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
    return buf.getvalue()


def fake_fetch(store):
    def step(ctx):
        folder = ctx.path("candidates")
        folder.mkdir()
        for name in ("01.jpg", "02.jpg"):
            Image.new("RGB", (600, 600), "red").save(folder / name)

        def save(j):
            j.source.title, j.source.candidates = "Son Kem Lì", ["01.jpg", "02.jpg"]
            j.product_info = "Son Kem Lì\nmàu đỏ"

        ctx.update_job(save)

    return step


def test_link_job_waits_for_pick_then_runs_straight_through(rig):
    store, runner, actions, calls, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    assert job.current_step == "fetch_source" and all(job.auto_gates.values())

    drain(store, runner)
    waiting = store.get(job.id)
    assert waiting.status == JobStatus.awaiting_review and waiting.gate == "pick_image"
    with pytest.raises(InvalidAction):
        actions.approve(job.id)  # must pick an image, not just approve

    actions.pick_image(job.id, candidate="02.jpg", product_info="Son Kem Lì đỏ")
    picked = store.get(job.id)
    assert picked.input_file == "input.jpg" and picked.product_info == "Son Kem Lì đỏ"
    assert (store.job_dir(job.id) / "input.jpg").exists()

    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    assert calls == ["fetch_source"] + UPLOAD_STEPS


def test_pick_rejects_foreign_or_missing_candidates(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    drain(store, runner)
    for bad in ("../state.json", "03.jpg"):
        with pytest.raises(InvalidAction):
            actions.pick_image(job.id, candidate=bad)
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id)
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id, upload=("x.sh", b"#!"))
    assert store.get(job.id).gate == "pick_image"


def test_pick_after_candidate_files_vanished_is_a_clear_error(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    drain(store, runner)
    (store.job_dir(job.id) / "candidates" / "01.jpg").unlink()
    with pytest.raises(InvalidAction, match="không còn"):
        actions.pick_image(job.id, candidate="01.jpg")
    assert not list(store.job_dir(job.id).glob("input*"))


def test_telegram_origin_is_kept_for_the_reply(rig):
    _, _, actions, _, _ = rig
    job = actions.create_from_link(URL, TelegramOrigin(chat_id=111, message_id=42))
    assert (job.telegram.chat_id, job.telegram.message_id) == (111, 42)
    assert actions.create_from_link(URL.replace("abc", "zzz")).telegram is None  # pasted in the UI


def test_duplicate_link_ignored_until_finished(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    first = actions.create_from_link(URL)
    assert actions.create_from_link(URL) is None
    actions.cancel(first.id)
    assert actions.create_from_link(URL) is not None


def test_own_image_after_fetch_failure(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = InvalidAction("blocked")  # any exception → step fails
    job = actions.create_from_link(URL)
    drain(store, runner)
    assert store.get(job.id).error.step == "fetch_source"
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "cutout")  # no image yet
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id, upload=("photo.png", b"not an image"))
    actions.pick_image(job.id, upload=("photo.png", png_bytes()))
    assert store.get(job.id).input_file == "input.png"
    assert store.get(job.id).status == JobStatus.queued


def test_upload_jobs_still_start_at_cutout_and_cannot_fetch(rig):
    store, runner, actions, calls, _ = rig
    job = new_job(store)
    assert job.current_step == "cutout"
    drain(store, runner)
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "fetch_source")
    assert "fetch_source" not in calls
