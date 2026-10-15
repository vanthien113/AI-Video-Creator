"""State machine: gates, auto gates, failures, retries, recovery after restart."""

import pytest

from app.event_bus import EventBus
from app.job_actions import InvalidAction
from app.link_job_actions import LinkJobActions
from app.job_models import STEPS, JobStatus

UPLOAD_STEPS = STEPS[STEPS.index("cutout"):]
from app.job_store import JobStore
from app.pipeline_runner import PipelineRunner
from app.steps.step_types import StepFailure


@pytest.fixture
def rig(make_config):
    config = make_config()
    calls: list[str] = []
    behaviour: dict[str, object] = {}

    def make_step(name):
        def step(ctx):
            calls.append(name)
            action = behaviour.get(name)
            if isinstance(action, Exception):
                raise action
            if callable(action):
                action(ctx)
        return step

    store = JobStore(config.paths.jobs_dir)
    runner = PipelineRunner(store, EventBus(), config, {s: make_step(s) for s in STEPS})
    return store, runner, LinkJobActions(store, runner, config), calls, behaviour


def drain(store, runner, limit=50):
    for _ in range(limit):
        job = store.next_queued()
        if job is None:
            return
        runner.run_one(job)
    raise AssertionError("pipeline did not settle")


def new_job(store, auto=None):
    gates = {"cutout": False, "prompt": False, "flow_video": False, **(auto or {})}
    return store.create("Son Môi Đỏ.jpg", b"img", "note", gates)


def test_stops_at_each_gate_and_finishes_after_approvals(rig):
    store, runner, actions, calls, _ = rig
    job = new_job(store)
    assert job.id.endswith("son-moi-do")

    drain(store, runner)
    assert store.get(job.id).status == JobStatus.awaiting_review
    assert store.get(job.id).gate == "cutout"
    assert calls == ["cutout"]

    actions.approve(job.id)
    drain(store, runner)
    assert store.get(job.id).gate == "prompt"

    actions.approve(job.id)
    drain(store, runner)
    assert store.get(job.id).gate == "flow_video"

    actions.approve(job.id)
    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    assert calls == UPLOAD_STEPS


def test_auto_gates_run_straight_through(rig):
    store, runner, _, calls, _ = rig
    job = new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    assert calls == UPLOAD_STEPS


def test_waiting_job_does_not_block_the_next(rig):
    store, runner, _, calls, _ = rig
    first = new_job(store)
    second = new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    drain(store, runner)
    assert store.get(first.id).status == JobStatus.awaiting_review
    assert store.get(second.id).status == JobStatus.done


def test_failure_then_retry_resumes_from_failed_step(rig):
    store, runner, actions, calls, behaviour = rig
    job = new_job(store, {"cutout": True})
    behaviour["upscale"] = StepFailure("hỏng")
    drain(store, runner)
    failed = store.get(job.id)
    assert failed.status == JobStatus.failed
    assert failed.error.step == "upscale" and failed.error.reason == "hỏng"

    del behaviour["upscale"]
    actions.retry(job.id, "upscale")
    drain(store, runner)
    assert store.get(job.id).gate == "prompt"
    assert calls == ["cutout", "upscale", "upscale", "prompt"]


def test_unexpected_exception_is_reported_not_fatal(rig):
    store, runner, _, _, behaviour = rig
    job = new_job(store)
    behaviour["cutout"] = RuntimeError("boom")
    drain(store, runner)
    assert "boom" in store.get(job.id).error.reason


def test_retry_rules(rig):
    store, runner, actions, _, _ = rig
    job = new_job(store)
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "cutout")  # still queued
    drain(store, runner)
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "enhance")  # cannot skip ahead
    actions.retry(job.id, "cutout", next_cutout_model=True)
    assert store.get(job.id).cutout_model_index == 1


def test_new_video_gets_a_new_tiktok_draft_but_a_retried_note_does_not(rig):
    store, runner, actions, _, behaviour = rig
    job = new_job(store, {"cutout": True, "prompt": True, "flow_video": True})
    behaviour["tiktok_draft"] = lambda ctx: ctx.update_job(lambda j: setattr(j.tiktok, "saved_at", "t"))
    drain(store, runner)
    actions.retry(job.id, "tiktok_draft")  # only the Telegram note is re-sent
    assert store.get(job.id).tiktok.saved_at == "t"
    drain(store, runner)
    actions.retry(job.id, "enhance")  # a re-encoded video is a different draft
    assert store.get(job.id).tiktok.saved_at is None


def test_recover_requeues_but_never_resubmits_to_flow(rig):
    store, runner, _, _, _ = rig
    plain, flow = new_job(store), new_job(store)
    store.update(plain.id, lambda j: (setattr(j, "status", JobStatus.running), setattr(j, "current_step", "upscale")))

    def submitted(j):
        j.status, j.current_step, j.flow.submitted_at = JobStatus.running, "flow_generate", "2026-10-15T10:00:00"

    store.update(flow.id, submitted)
    runner.recover()
    assert store.get(plain.id).status == JobStatus.queued
    recovered = store.get(flow.id)
    assert recovered.status == JobStatus.failed and recovered.error.step == "flow_generate"


def test_continue_after_manual_fix_sets_resume(rig):
    store, runner, actions, _, behaviour = rig
    job = new_job(store, {"cutout": True, "prompt": True})

    def opened_then_failed(ctx):
        ctx.update_job(lambda j: (setattr(j.flow, "project_url", "https://flow/p/1"),
                                  setattr(j.flow, "submitted_at", "t")))
        raise StepFailure("lỗi giao diện")

    behaviour["flow_generate"] = opened_then_failed
    drain(store, runner)
    assert store.get(job.id).error.step == "flow_generate"
    actions.continue_after_manual_fix(job.id)
    resumed = store.get(job.id)
    assert resumed.status == JobStatus.queued and resumed.flow.resume


def test_cancel_during_step_wins_over_completion(rig):
    store, runner, actions, _, behaviour = rig
    job = new_job(store)
    behaviour["cutout"] = lambda ctx: actions.cancel(job.id)
    drain(store, runner)
    assert store.get(job.id).status == JobStatus.cancelled


def test_store_reloads_state_from_disk(rig, make_config):
    store, _, _, _, _ = rig
    job = new_job(store)
    store.update(job.id, lambda j: setattr(j, "note", "đã lưu"))
    reloaded = JobStore(store.jobs_dir)
    assert reloaded.get(job.id).note == "đã lưu"
