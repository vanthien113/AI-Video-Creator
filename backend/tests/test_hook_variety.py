"""Hooks kept repeating ("Đi cả ngày mà…"): Claude now sees the hooks of recent videos and must not reuse them."""

import json
import os

from app.steps.prompt_step import build_instruction, recent_hooks


def write_prompt(jobs_dir, job_id, summary, mtime):
    folder = jobs_dir / job_id
    folder.mkdir(parents=True)
    path = folder / "prompt.json"
    path.write_text(json.dumps({"prompt": "p", "summary": summary}, ensure_ascii=False), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_recent_hooks_newest_first_without_the_current_job_or_duplicates(tmp_path):
    write_prompt(tmp_path, "a", 'Hook: "Đi cả ngày mà chân vẫn êm, bạn tin không?" Ý tưởng…', 100)
    write_prompt(tmp_path, "b", 'Hook: "Đi cả ngày mà không đau chân!" Ý tưởng…', 200)
    write_prompt(tmp_path, "c", 'Hook: "Đi cả ngày mà không đau chân!" lặp lại', 300)
    write_prompt(tmp_path, "d", "Không có hook ở đây", 400)
    write_prompt(tmp_path, "me", 'Hook: "Hook của chính job này" …', 500)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "prompt.json").write_text("{not json", encoding="utf-8")

    assert recent_hooks(tmp_path, exclude="me") == ["Đi cả ngày mà không đau chân!",
                                                     "Đi cả ngày mà chân vẫn êm, bạn tin không?"]
    assert len(recent_hooks(tmp_path, exclude="me", limit=1)) == 1
    assert recent_hooks(tmp_path / "missing", exclude="x") == []


def test_instruction_lists_recent_hooks_to_avoid():
    text = build_instruction("rules", "", "", "", "", recent=["Đi cả ngày mà không đau chân!"])
    assert "Đi cả ngày mà không đau chân!" in text and "do not reuse" in text
    assert "do not reuse" not in build_instruction("rules", "", "", "", "")
