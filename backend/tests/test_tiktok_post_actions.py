"""Đăng ngay / Lên lịch: who may ask, and retries or restarts never click Post a second time on their own."""

import pytest
from fastapi.testclient import TestClient

from app.job_actions import InvalidAction
from app.job_models import JobStatus, SourceInfo
from app.main import create_app
from app.steps.step_types import StepFailure

from .test_api_end_to_end import fake_steps, wait_for
from .test_link_jobs import URL
from .test_pipeline_runner import drain, new_job, rig  # noqa: F401  (fixture re-export)

ALL_AUTO = {"cutout": True, "prompt": True, "flow_video": True}


def done_link_job(store, runner, url=URL) -> str:
    job = new_job(store, ALL_AUTO)
    store.update(job.id, lambda j: setattr(j, "source", SourceInfo(url=url, title="Giày búp bê")))
    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    return job.id


def test_request_post_runs_the_post_step_once(rig):
    store, runner, actions, calls, _ = rig
    job_id = done_link_job(store, runner)
    calls.clear()
    queued = actions.request_post(job_id, "schedule")
    assert queued.status == JobStatus.queued and queued.current_step == "tiktok_post"
    assert queued.post.mode == "schedule" and queued.post.requested_at
    drain(store, runner)
    assert calls == ["tiktok_post"] and store.get(job_id).status == JobStatus.done
    with pytest.raises(InvalidAction, match="đã được yêu cầu đăng"):
        actions.request_post(job_id, "now")  # second tap, or the other side (tool / Telegram)


def test_request_post_only_for_finished_link_jobs_with_a_product_id(rig):
    store, runner, actions, _, _ = rig
    upload = new_job(store, ALL_AUTO)
    drain(store, runner)
    with pytest.raises(InvalidAction, match="link TikTok Shop"):
        actions.request_post(upload.id, "now")
    short = done_link_job(store, runner, url="https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA")
    with pytest.raises(InvalidAction, match="ID sản phẩm"):
        actions.request_post(short, "now")
    with pytest.raises(InvalidAction, match="không hợp lệ"):
        actions.request_post(short, "later")
    waiting = new_job(store)  # queued, far from done
    store.update(waiting.id, lambda j: setattr(j, "source", SourceInfo(url=URL)))
    with pytest.raises(InvalidAction, match="đã xong"):
        actions.request_post(waiting.id, "now")


def test_retry_after_a_click_without_confirmation_is_the_users_call(rig):
    store, runner, actions, _, behaviour = rig
    job_id = done_link_job(store, runner)

    def clicked_then_lost(ctx):
        ctx.update_job(lambda j: setattr(j.post, "submitted_at", "2026-10-17T10:31:00"))
        raise StepFailure("không thấy bài trên TikTok Studio")

    behaviour["tiktok_post"] = clicked_then_lost
    actions.request_post(job_id, "now")
    drain(store, runner)
    failed = store.get(job_id)
    assert failed.status == JobStatus.failed and failed.error.step == "tiktok_post" and failed.post.submitted_at
    actions.retry(job_id, "tiktok_post")  # the UI warned "có thể đăng 2 lần" before sending this
    retried = store.get(job_id)
    assert retried.post.submitted_at is None and retried.post.mode == "now"
    assert retried.post.recheck_since == "2026-10-17T10:31:00"  # the next run looks for that post first


def test_retry_after_posting_keeps_the_post_and_a_new_video_resets_it(rig):
    store, runner, actions, _, behaviour = rig
    job_id = done_link_job(store, runner)
    behaviour["tiktok_post"] = lambda ctx: ctx.update_job(
        lambda j: (setattr(j.post, "submitted_at", "t"), setattr(j.post, "done_at", "t")))
    actions.request_post(job_id, "now")
    drain(store, runner)
    actions.retry(job_id, "tiktok_post")  # e.g. only the Telegram message had failed
    kept = store.get(job_id).post
    assert kept.done_at == "t" and kept.submitted_at == "t"
    drain(store, runner)
    actions.retry(job_id, "export")  # a new video file may be posted again
    assert store.get(job_id).post.mode is None and store.get(job_id).post.done_at is None


def test_recover_never_clicks_post_again(rig):
    store, runner, _, _, _ = rig
    clicked, waiting = new_job(store), new_job(store)

    def at_post(submitted):
        def mutate(j):
            j.status, j.current_step, j.post.mode, j.post.submitted_at = (JobStatus.running, "tiktok_post",
                                                                         "schedule", submitted)
        return mutate

    store.update(clicked.id, at_post("2026-10-17T10:31:00"))
    store.update(waiting.id, at_post(None))
    runner.recover()
    recovered = store.get(clicked.id)
    assert recovered.status == JobStatus.failed and recovered.error.step == "tiktok_post"
    assert "TikTok Studio" in recovered.error.reason
    assert store.get(waiting.id).status == JobStatus.queued


def test_post_endpoint(make_config):
    app = create_app(make_config(), steps=fake_steps(), allowed_hosts=["testserver"])
    with TestClient(app) as client:
        svc = app.state.services
        job = svc.store.create("a.jpg", b"img", "", ALL_AUTO)
        wait_for(client, job.id, lambda j: j["status"] == "done")
        svc.store.update(job.id, lambda j: setattr(j, "source", SourceInfo(url=URL, title="Giày")))
        res = client.post(f"/api/jobs/{job.id}/post", json={"mode": "schedule"})
        assert res.status_code == 200 and res.json()["post"]["mode"] == "schedule"
        wait_for(client, job.id, lambda j: j["status"] == "done")
        assert client.post(f"/api/jobs/{job.id}/post", json={"mode": "now"}).status_code == 409
        assert client.post(f"/api/jobs/{job.id}/post", json={"mode": "later"}).status_code == 422


def test_cancel_is_refused_once_the_click_happened(rig):
    store, runner, actions, _, behaviour = rig
    job_id = done_link_job(store, runner)

    def clicked_then_lost(ctx):
        ctx.update_job(lambda j: setattr(j.post, "submitted_at", "2026-10-17T10:31:00"))
        raise StepFailure("không thấy bài")

    behaviour["tiktok_post"] = clicked_then_lost
    actions.request_post(job_id, "now")
    drain(store, runner)
    with pytest.raises(InvalidAction, match="không huỷ được nữa"):
        actions.cancel(job_id)
    assert store.get(job_id).status == JobStatus.failed
