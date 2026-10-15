"""Flow agent mode (UI since 2026-10-15): the prompt goes to a chat agent that proposes a plan
("Would you like me to kick off this 1 video generation, costing 15 credits?") and waits for
Approve / Always approve / Reject. Resolution and duration are no longer settings, so they go
into the request text.
"""

import re
import time

from ..config import FlowConfig
from .flow_client import FlowClient, FlowError

CREDITS = re.compile(r"(\d[\d,.]*)\s*(?:credits?\b|tín dụng)", re.I)


def start_new_session(client: FlowClient) -> None:
    """A fresh chat, so a retry in the same project does not inherit the earlier conversation."""
    client.click("agent_new_session_button")


def configure_agent(client: FlowClient, cfg: FlowConfig) -> str:
    """Agent settings: always ask before generating (the tool checks the cost, then approves); video defaults."""
    client.click("agent_settings_button")
    client.click("agent_confirm_always")
    aspect_group = client.find("agent_video_aspect_group").first
    count_group = client.find("agent_count_group").last  # image counts come first, video counts last
    client.click("agent_aspect_radio", cfg.aspect_ratio, scope=aspect_group)
    client.click("agent_count_radio", cfg.outputs, scope=count_group)
    model = client.find("agent_video_model_button").first
    if cfg.model not in model.inner_text():
        client.click("agent_video_model_button")
        client.click("agent_model_menu_item", cfg.model)
    checks = {
        "Always": client.find("agent_confirm_always").first.locator("xpath=ancestor-or-self::mat-radio-button")
                  .locator("input[type=radio]").is_checked(),
        cfg.aspect_ratio: client.sel.locate(aspect_group, "agent_aspect_radio", cfg.aspect_ratio).first
                          .get_attribute("aria-checked") == "true",
        f"x{cfg.outputs}": client.sel.locate(count_group, "agent_count_radio", cfg.outputs).first
                           .get_attribute("aria-checked") == "true",
        cfg.model: cfg.model in model.inner_text(),
    }
    if not all(checks.values()):
        wrong = ", ".join(k for k, ok in checks.items() if not ok)
        raise FlowError(f"Thiết lập Agent của Flow không khớp cấu hình (chưa chọn được: {wrong}).")
    client.click("agent_settings_save")
    return f"{cfg.model} · {cfg.aspect_ratio} · x{cfg.outputs} · hỏi trước khi sinh"


def agent_tail(client: FlowClient, chars: int = 300) -> str:
    panel = client.find("agent_panel")
    return panel.first.inner_text()[-chars:].replace("\n", " ") if panel.count() else ""


def approve_plan(client: FlowClient, max_credits: int, timeout: float = 180) -> int:
    """Wait for the agent's proposal, check its cost, then Approve: this click is what spends credits."""
    approve = client.find("agent_approve_option")
    deadline = time.time() + timeout
    while not approve.count():
        if time.time() > deadline:
            raise FlowError(f"Sau {int(timeout)}s Agent của Flow vẫn chưa hỏi duyệt. Agent viết: {agent_tail(client)}",
                            "plan_rejected")
        client.page.wait_for_timeout(2000)
    plan = approve.last.evaluate("e => (e.closest('.message-row') || e.closest('flow-agent-panel')).innerText")
    try:
        credits = check_plan(plan, max_credits)
    except FlowError:
        try:
            client.find("agent_reject_option").last.click(timeout=5000)
        except Exception:
            pass  # the refusal below matters more than the click
        raise
    approve.last.click(timeout=15000)
    client.pause()
    return credits


def agent_request(prompt: str, cfg: FlowConfig, image_count: int = 1) -> str:
    videos = f"{cfg.outputs} video" + ("s" if cfg.outputs > 1 else "")
    settings = ", ".join(s for s in (cfg.model, cfg.aspect_ratio, cfg.resolution, cfg.duration) if s)
    source = ("the attached product image" if image_count == 1 else
              f"the {image_count} attached images (the first is the product; the others show it from other "
              "angles or in use)")
    # Seen 2026-10-15: unless told otherwise, the agent opened the video on the uploaded cutout.
    return (f"Generate exactly {videos} (no images) from {source}. Settings: {settings}. "
            "Use the images only as references for how the product looks, not as the first frame or any "
            "start/end frame: the video opens on the first shot described in the prompt. "
            f"Use this prompt verbatim, do not rewrite it:\n\n{prompt}")


def planned_credits(text: str) -> int | None:
    """Credits the agent says it will spend; the largest figure if it names several (e.g. a total)."""
    amounts = [int(re.sub(r"[,.]", "", m.group(1))) for m in CREDITS.finditer(text)]
    return max(amounts) if amounts else None


def check_plan(text: str, max_credits: int) -> int:
    """Approve only a plan with a known cost within budget: the agent, not the tool, picks what to generate."""
    credits = planned_credits(text)
    if credits is None:
        raise FlowError(f"Agent của Flow không nói rõ số credit nên tool không duyệt. Agent viết: {text[-300:]}",
                        "plan_rejected")
    if credits > max_credits:
        raise FlowError(f"Agent định tiêu {credits} credit, vượt mức flow.max_credits={max_credits}. Tool đã từ chối.",
                        "plan_rejected")
    return credits
