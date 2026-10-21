"""Map step names to their implementations."""

from .cutout_step import run_cutout
from .enhance_video_step import run_enhance
from .export_step import run_export
from .fetch_product_step import run_fetch_product
from .hashtags_step import run_hashtags
from .flow_steps import run_flow_download, run_flow_generate
from .prompt_step import run_prompt
from .send_telegram_step import run_send_telegram
from .shopee_step import run_shopee
from .step_types import StepFn
from .tiktok_draft_step import run_tiktok_draft
from .tiktok_post_step import run_tiktok_post
from .upscale_step import run_upscale


def build_steps() -> dict[str, StepFn]:
    return {
        "fetch_source": run_fetch_product,
        "cutout": run_cutout,
        "upscale": run_upscale,
        "prompt": run_prompt,
        "flow_generate": run_flow_generate,
        "flow_download": run_flow_download,
        "enhance": run_enhance,
        "export": run_export,
        "hashtags": run_hashtags,
        "shopee": run_shopee,
        "send_telegram": run_send_telegram,
        "tiktok_draft": run_tiktok_draft,
        "tiktok_post": run_tiktok_post,
    }
