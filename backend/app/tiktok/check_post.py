"""Dry run of the Đăng TikTok step on a real job: everything in TikTok Studio except the final Post/Schedule click.

    cd backend && ../.venv/bin/python -m app.tiktok.check_post <job-id> [--schedule]

With --schedule it reads the Content page and picks the slot like the step does. It uploads the job's exported
video into the form (nothing is posted), fills the title and hashtags, adds the product link, turns on the AI
label, sets When to post, and stops (it does not wait for TikTok's content check, the real step does). The tab stays open in the tool's Chrome, in the background: look at it, then
close it to throw the upload away. The job's state is not changed. Run it while no job is running.
"""

import argparse
import sys

from ..config import load_config
from ..job_store import JobNotFound, JobStore
from ..steps.step_types import JobContext, StepFailure
from ..steps.tiktok_post_step import BrowserStudio, make_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy thử Đăng TikTok, dừng trước nút Post/Schedule.")
    parser.add_argument("job_id")
    parser.add_argument("--schedule", action="store_true", help="chạy thử Lên lịch (mặc định: Đăng ngay)")
    args = parser.parse_args(argv)
    config = load_config()
    store = JobStore(config.paths.jobs_dir)
    try:
        job = store.get(args.job_id)
    except JobNotFound:
        print(f"Không có job {args.job_id}")
        return 2
    job.post.mode = "schedule" if args.schedule else "now"  # local copy only, never saved
    ctx = JobContext(job=job, job_dir=store.job_dir(job.id), config=config,
                     report=lambda p, m: print(f"[{p:4.0%}] {m}"), log=print, update_job=lambda fn: job)
    studio = BrowserStudio(ctx)
    try:
        plan = make_plan(ctx, studio)
        print(f"Kế hoạch: {plan}")
        studio.post(plan, before_click=lambda: None, dry_run=True)
    except StepFailure as exc:
        print(f"✖ {exc.reason}" + (f" (ảnh chụp: {exc.screenshot})" if exc.screenshot else ""))
        return 1
    print("✔ Đã dừng trước nút Post/Schedule. Xem tab TikTok Studio trong Chrome của tool rồi đóng tab đó.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
