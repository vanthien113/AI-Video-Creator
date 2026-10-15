"""Dry run on Flow: every action up to (not including) "Start generation". Spends no credits.

Usage (from backend/):  ../.venv/bin/python -m app.flow.check_selectors [--project URL] [--image PATH]
"""

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import load_config
from .flow_agent import configure_agent, start_new_session
from .flow_client import FlowError, flow_session


def sample_image() -> Path:
    path = Path(tempfile.gettempdir()) / "flow-check-product.png"
    img = Image.new("RGB", (1024, 1024), "white")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((380, 220, 640, 820), 40, fill=(200, 40, 60))
    img.save(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="URL dự án Flow để thử (bỏ trống = tạo dự án mới)")
    parser.add_argument("--image", type=Path, help="Ảnh dùng để thử tải lên")
    args = parser.parse_args()
    cfg = load_config().flow
    image = args.image or sample_image()

    results: list[tuple[str, bool, str]] = []
    try:
        with flow_session(cfg) as client:
            checks = [
                ("Mở dự án", lambda: client.open_project(args.project or cfg.project_url or None)),
                ("Mở phiên Agent mới", lambda: start_new_session(client) or "ok"),
                ("Thiết lập Agent", lambda: configure_agent(client, cfg)),
                ("Tải ảnh làm nguyên liệu", lambda: client.upload_ingredients([(image, "flow-check.png")]) or "ok"),
                ("Nhập prompt", lambda: client.fill_prompt("Flow selector check, do not generate.") or "ok"),
                ("Thấy nút Start generation", lambda: str(client.find("generate_button").first.is_visible())),
            ]
            for label, action in checks:
                try:
                    results.append((label, True, str(action())))
                except FlowError as exc:
                    results.append((label, False, str(exc)))
                    break
            try:  # leave the project as we found it
                client.page.keyboard.press("Escape")
                client.fill_prompt(" ")
                client.clear_ingredients()
            except FlowError:
                pass
    except FlowError as exc:
        print(f"✖ {exc}")
        return 1
    for label, ok, detail in results:
        print(f"{'✔' if ok else '✖'} {label}: {detail}")
    return 0 if all(ok for _, ok, _ in results) and len(results) == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
