"""Flow agent mode: the request sent to the agent and the check of its plan before approving."""

import pytest

from app.config import FlowConfig
from app.flow.flow_agent import agent_request, check_plan, planned_credits
from app.flow.flow_client import FlowError

PLAN = "Use this prompt verbatim...\n\nWould you like me to kick off this 1 video generation, costing 15 credits?"


def test_agent_request_carries_settings_and_verbatim_prompt():
    cfg = FlowConfig(model="Omni 1.1 Flash", aspect_ratio="9:16", resolution="720p", duration="10s", outputs=1)
    text = agent_request("A slow orbit around the shoes.", cfg)
    assert "exactly 1 video" in text and "no images" in text
    assert "Omni 1.1 Flash, 9:16, 720p, 10s" in text
    assert "verbatim" in text
    assert text.endswith("A slow orbit around the shoes.")
    # Seen 2026-10-15: the agent opened the video on the uploaded cutout unless told not to.
    assert "not as the first frame" in text and "first shot described in the prompt" in text


def test_agent_request_skips_empty_resolution_and_duration():
    text = agent_request("p", FlowConfig(model="Veo 3.1 - Fast", resolution="", duration="", outputs=2))
    assert "exactly 2 videos" in text
    assert "Veo 3.1 - Fast, 9:16." in text


@pytest.mark.parametrize("text,expected", [
    (PLAN, 15),
    ("Mình sẽ tạo 1 video, tốn 12 credit. Bạn đồng ý không?", 12),
    ("This will use 1,000 credits.", 1000),
    ("Shall I generate 1 video now?", None),
])
def test_planned_credits(text, expected):
    assert planned_credits(text) == expected


def test_check_plan_accepts_within_budget():
    assert check_plan(PLAN, max_credits=20) == 15


@pytest.mark.parametrize("text", [PLAN.replace("15 credits", "100 credits"), "Shall I generate 1 video now?"])
def test_check_plan_refuses_over_budget_or_unknown_cost(text):
    with pytest.raises(FlowError) as err:
        check_plan(text, max_credits=20)
    assert err.value.kind == "plan_rejected"
