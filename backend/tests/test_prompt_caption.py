"""The post caption is written by Claude with the prompt, not copied from the shop's listing name."""

import json

from PIL import Image

from app.job_models import JobState, SourceInfo
from app.steps import prompt_step
from app.steps.prompt_step import build_instruction, run_prompt


def test_instruction_asks_for_a_caption():
    assert '"caption"' in build_instruction("rules", "", "", "", "")


def test_prompt_step_saves_the_caption_on_the_job(make_context, tmp_path, monkeypatch):
    job = JobState(id="t", name="dep", input_file="input.jpg", created_at="t",
                   source=SourceInfo(url="u", title="Dép Tổ Ong Nữ Cao Cấp ABABAS 2546"))
    ctx = make_context(job=job)
    ctx.config.paths.rules_file.write_text("rules", encoding="utf-8")
    Image.new("RGB", (64, 64), "white").save(ctx.path("product-2k.png"))
    answer = {"prompt": "P", "summary": 'Hook: "H"', "product_type": "dép nữ",
              "caption": "Dép trắng mà dơ xả nước là sạch 🫧"}
    stdout = json.dumps({"type": "result", "is_error": False, "result": json.dumps(answer, ensure_ascii=False)})
    monkeypatch.setattr(prompt_step, "require_tool", lambda name: name)
    monkeypatch.setattr(prompt_step, "run_tool", lambda *a, **kw: stdout)

    run_prompt(ctx)

    assert ctx.holder["job"].caption == "Dép trắng mà dơ xả nước là sạch 🫧"
    saved = json.loads(ctx.path("prompt.json").read_text(encoding="utf-8"))
    assert saved["caption"] == "Dép trắng mà dơ xả nước là sạch 🫧"
