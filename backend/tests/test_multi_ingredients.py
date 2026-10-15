"""Several product photos for one video: the first is the main image (cutout), the rest go to Flow as extra ingredients."""

import json

import pytest
from PIL import Image

from app.config import FlowConfig
from app.flow.flow_agent import agent_request
from app.job_actions import InvalidAction
from app.steps.prompt_step import build_instruction, build_message

from .test_link_jobs import URL
from .test_pipeline_runner import drain, rig  # noqa: F401  (fixture re-export)

NAMES = ["01.jpg", "02.jpg", "03.jpg", "04.jpg", "05.jpg"]


def fetch_five(ctx):
    folder = ctx.path("candidates")
    folder.mkdir()
    for i, name in enumerate(NAMES):
        Image.new("RGB", (64, 64), (40 * i, 0, 0)).save(folder / name)
    ctx.update_job(lambda j: setattr(j.source, "candidates", list(NAMES)))


@pytest.fixture
def picking(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fetch_five
    job = actions.create_from_link(URL)
    drain(store, runner)
    return store, actions, job


def test_main_image_plus_extras_in_the_order_picked(picking):
    store, actions, job = picking
    actions.pick_image(job.id, candidate="02.jpg", extras=["05.jpg", "01.jpg"])
    picked, folder = store.get(job.id), store.job_dir(job.id)
    assert picked.input_file == "input.jpg"
    assert picked.extra_ingredients == ["ingredient-1.jpg", "ingredient-2.jpg"]
    assert (folder / "ingredient-1.jpg").read_bytes() == (folder / "candidates" / "05.jpg").read_bytes()
    assert (folder / "ingredient-2.jpg").read_bytes() == (folder / "candidates" / "01.jpg").read_bytes()


@pytest.mark.parametrize("extras", [
    ["09.jpg"],                            # not from this job
    ["../state.json"],
    ["02.jpg"],                            # the main image again
    ["03.jpg", "03.jpg"],                  # twice
    ["01.jpg", "03.jpg", "04.jpg"],        # 4 images > flow.max_ingredients (3)
])
def test_bad_extras_are_refused_and_nothing_changes(picking, extras):
    store, actions, job = picking
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id, candidate="02.jpg", extras=extras)
    after = store.get(job.id)
    assert after.gate == "pick_image" and after.extra_ingredients == []
    assert not list(store.job_dir(job.id).glob("ingredient-*"))


def test_claude_sees_every_image_main_first(tmp_path):
    images = []
    for i in range(3):
        images.append(tmp_path / f"{i}.png")
        Image.new("RGB", (32, 32), (80 * i, 0, 0)).save(images[-1])
    content = json.loads(build_message(images, "write it"))["message"]["content"]
    assert [part["type"] for part in content] == ["image", "image", "image", "text"]
    assert "other angles or in use" in build_instruction("rules", "", "", "", "", extra_images=2)
    assert "other angles" not in build_instruction("rules", "", "", "", "")
    assert "not the first frame" in build_instruction("rules", "", "", "", "")


def test_agent_request_names_how_many_images():
    cfg = FlowConfig(model="Omni 1.1 Flash", resolution="720p", duration="10s")
    assert "from the attached product image." in agent_request("p", cfg)
    assert "from the 3 attached images" in agent_request("p", cfg, image_count=3)
