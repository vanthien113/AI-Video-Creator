"""Whole pipeline through the REST API with a fake Flow (real worker thread, fake steps)."""

import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.job_models import STEPS
from app.main import create_app

from .conftest import make_test_clip


def fake_steps():
    def write(name, data=b"x"):
        return lambda ctx: ctx.path(name).write_bytes(data)

    def prompt(ctx):
        ctx.path("prompt.json").write_text(json.dumps({"prompt": "orig", "summary": "tóm tắt"}), encoding="utf-8")

    def flow_download(ctx):
        make_test_clip(ctx.path("flow-raw.mp4"), seconds=1)

    def export(ctx):
        dest = ctx.config.paths.export_dir / "out.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"video")
        ctx.update_job(lambda j: setattr(j, "export_path", str(dest)))

    steps = {s: (lambda ctx: None) for s in STEPS}
    steps.update(cutout=write("cutout.png"), prompt=prompt, flow_download=flow_download,
                 enhance=write("final-4k60.mp4"), export=export)
    return steps


@pytest.fixture
def client(make_config):
    app = create_app(make_config(), steps=fake_steps(), allowed_hosts=["testserver"])
    with TestClient(app) as c:
        yield c


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


def wait_for(client, job_id, predicate, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(0.05)
    raise AssertionError(f"timeout, last state: {job['status']} {job.get('gate')}")


def test_full_flow_with_reviews(client):
    res = client.post("/api/jobs", files=[("images", ("Sản phẩm.png", png_bytes(), "image/png"))],
                      data={"note": "Tết", "auto_gates": json.dumps({"cutout": False})})
    assert res.status_code == 200, res.text
    job_id = res.json()[0]["id"]

    job = wait_for(client, job_id, lambda j: j["status"] == "awaiting_review")
    assert job["gate"] == "cutout"
    assert client.get(f"/api/jobs/{job_id}/files/cutout.png").status_code == 200
    assert client.post(f"/api/jobs/{job_id}/approve", json={}).status_code == 200

    job = wait_for(client, job_id, lambda j: j["gate"] == "prompt")
    assert job["prompt"]["summary"] == "tóm tắt"
    assert client.post(f"/api/jobs/{job_id}/approve", json={"prompt": "  edited  "}).status_code == 200

    job = wait_for(client, job_id, lambda j: j["gate"] == "flow_video")
    assert job["prompt"]["prompt"] == "edited"
    client.post(f"/api/jobs/{job_id}/approve", json={})

    job = wait_for(client, job_id, lambda j: j["status"] == "done")
    assert job["export_path"].endswith("out.mp4")


def test_manual_video_replaces_flow_result(client):
    res = client.post("/api/jobs", files=[("images", ("a.png", png_bytes(), "image/png"))],
                      data={"auto_gates": json.dumps({"cutout": True, "prompt": True})})
    job_id = res.json()[0]["id"]
    wait_for(client, job_id, lambda j: j["gate"] == "flow_video")

    bad = client.post(f"/api/jobs/{job_id}/manual-video", files={"video": ("x.mp4", b"not a video", "video/mp4")})
    assert bad.status_code == 409

    clip = make_test_clip(client.app.state.services.store.jobs_dir / "clip.mp4", seconds=1)
    ok = client.post(f"/api/jobs/{job_id}/manual-video", files={"video": ("x.mp4", clip.read_bytes(), "video/mp4")})
    assert ok.status_code == 200, ok.text
    assert wait_for(client, job_id, lambda j: j["gate"] == "flow_video")["status"] == "awaiting_review"


def test_rejects_bad_input_and_unsafe_paths(client):
    bad = client.post("/api/jobs", files=[("images", ("doc.pdf", b"%PDF", "application/pdf"))])
    assert bad.status_code == 400
    res = client.post("/api/jobs", files=[("images", ("a.png", png_bytes(), "image/png"))])
    job_id = res.json()[0]["id"]
    assert client.get(f"/api/jobs/{job_id}/files/state.json").status_code == 403
    assert client.get(f"/api/jobs/{job_id}/files/../../config.yaml").status_code in (403, 404)
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post(f"/api/jobs/{job_id}/approve", json={}).status_code in (200, 409)
    evil = client.post(f"/api/jobs/{job_id}/cancel", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403


def test_pick_several_images_through_the_api(make_config):
    def fetch(ctx):
        (ctx.path("candidates")).mkdir()
        for name in ("01.jpg", "02.jpg", "03.jpg"):
            Image.new("RGB", (32, 32), "red").save(ctx.path("candidates") / name)
        ctx.update_job(lambda j: setattr(j.source, "candidates", ["01.jpg", "02.jpg", "03.jpg"]))

    steps = {**fake_steps(), "fetch_source": fetch}
    app = create_app(make_config(), steps=steps, allowed_hosts=["testserver"])
    with TestClient(app) as c:
        job = c.post("/api/links", json={"url": "https://shop.tiktok.com/vn/pdp/1"}).json()
        wait_for(c, job["id"], lambda j: j["gate"] == "pick_image")
        res = c.post(f"/api/jobs/{job['id']}/pick", data={"candidate": "02.jpg", "extra": ["03.jpg", "01.jpg"]})
        assert res.status_code == 200, res.text
        assert res.json()["extra_ingredients"] == ["ingredient-1.jpg", "ingredient-2.jpg"]


def test_reveal_shows_the_job_video_in_finder(client, monkeypatch):
    from app.api import jobs_routes

    opened = []
    monkeypatch.setattr(jobs_routes.subprocess, "run", lambda args, check: opened.append(args))
    res = client.post("/api/jobs", files=[("images", ("a.png", png_bytes(), "image/png"))],
                      data={"auto_gates": json.dumps({"cutout": True, "prompt": True})})
    job_id = res.json()[0]["id"]
    assert client.post(f"/api/jobs/{job_id}/reveal").status_code == 404  # no video yet
    wait_for(client, job_id, lambda j: j["gate"] == "flow_video")
    client.post(f"/api/jobs/{job_id}/approve", json={})
    wait_for(client, job_id, lambda j: j["status"] == "done")
    assert client.post(f"/api/jobs/{job_id}/reveal").status_code == 200
    assert opened[-1][:2] == ["open", "-R"]
    assert opened[-1][2].endswith(f"{job_id}/final-4k60.mp4")  # the project's copy, not the exported one
