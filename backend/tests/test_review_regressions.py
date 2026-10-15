"""Regressions for the code-review findings: no double Flow submit, cancel/retry races."""

import pytest

from app.job_actions import InvalidAction
from app.job_models import JobStatus
from app.steps.flow_steps import run_flow_generate
from app.steps.step_types import StepFailure

from .test_pipeline_runner import drain, new_job, rig  # noqa: F401  (fixture re-export)


def set_running_flow(store, job_id, **flow):
    def mutate(j):
        j.status, j.current_step = JobStatus.running, "flow_generate"
        for key, value in flow.items():
            setattr(j.flow, key, value)

    store.update(job_id, mutate)


def test_recover_with_finished_video_moves_on_to_download(rig):
    store, runner, _, calls, _ = rig
    job = new_job(store, {"cutout": True, "prompt": True})
    set_running_flow(store, job.id, submitted_at="t", video_ref="vid")
    runner.recover()
    assert store.get(job.id).current_step == "flow_download"
    drain(store, runner)
    assert "flow_generate" not in calls


def test_flow_generate_refuses_to_resubmit_without_explicit_retry(make_context):
    ctx = make_context()
    ctx.job.flow.submitted_at = "2026-10-15T10:00:00"
    with pytest.raises(StepFailure, match="đã gửi lên Flow"):
        run_flow_generate(ctx)


def test_retry_of_earlier_step_clears_flow_submission(rig):
    store, runner, actions, _, _ = rig
    job = new_job(store)
    drain(store, runner)  # waits at the cutout gate

    def submitted(j):
        j.flow.project_url, j.flow.submitted_at, j.flow.video_ref = "https://flow/p", "t", "vid"

    store.update(job.id, submitted)
    actions.retry(job.id, "cutout")
    flow = store.get(job.id).flow
    assert flow.submitted_at is None and flow.video_ref is None
    assert flow.project_url == "https://flow/p"


def test_actions_refused_while_cancelled_step_still_runs(rig):
    store, runner, actions, _, behaviour = rig
    job = new_job(store)
    seen = {}

    def step(ctx):
        actions.cancel(job.id)
        with pytest.raises(InvalidAction):
            actions.retry(job.id, "cutout")
        seen["checked"] = True

    behaviour["cutout"] = step
    drain(store, runner)
    assert seen["checked"]
    assert store.get(job.id).status == JobStatus.cancelled
    actions.retry(job.id, "cutout")  # allowed once the step has stopped
    assert store.get(job.id).status == JobStatus.queued


def test_approve_cannot_resurrect_a_cancelled_job(rig):
    store, runner, actions, _, _ = rig
    job = new_job(store)
    drain(store, runner)
    actions.cancel(job.id)
    with pytest.raises(InvalidAction):
        actions.approve(job.id)
    assert store.get(job.id).status == JobStatus.cancelled


def test_cancelled_queued_job_is_not_claimed(rig):
    store, runner, actions, calls, _ = rig
    job = new_job(store)
    snapshot = store.next_queued()
    actions.cancel(job.id)
    runner.run_one(snapshot)  # worker picked it just before the cancel landed
    assert calls == []
    assert store.get(job.id).status == JobStatus.cancelled


def test_retry_rejects_non_image_upload(rig):
    store, runner, actions, _, _ = rig
    job = new_job(store)
    drain(store, runner)
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "cutout", new_image=("evil.sh", b"#!/bin/sh"))
    assert (store.job_dir(job.id) / "input.jpg").exists()
