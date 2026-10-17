"""The dry-run command: plans like the step, calls the studio with dry_run, never changes the job."""

from app.job_models import SourceInfo
from app.job_store import JobStore
from app.tiktok import check_post

URL = "https://shop.tiktok.com/vn/pdp/1737383451447231991"


def test_dry_run_never_clicks_and_leaves_the_job_alone(make_config, monkeypatch, tmp_path, capsys):
    config = make_config()
    store = JobStore(config.paths.jobs_dir)
    job = store.create("a.jpg", b"img", "", {"cutout": True, "prompt": True, "flow_video": True})
    video = tmp_path / "out.mp4"
    video.write_bytes(b"video")
    store.update(job.id, lambda j: (setattr(j, "source", SourceInfo(url=URL, title="Dép sục")),
                                    setattr(j, "export_path", str(video))))
    seen = {}

    class Studio:
        def __init__(self, ctx):
            pass

        def content_items(self):
            return []

        def post(self, plan, before_click, dry_run=False):
            seen.update(plan=plan, dry_run=dry_run)

    monkeypatch.setattr(check_post, "load_config", lambda: config)
    monkeypatch.setattr(check_post, "BrowserStudio", Studio)
    assert check_post.main([job.id, "--schedule"]) == 0
    assert seen["dry_run"] is True and seen["plan"].schedule_at and seen["plan"].product_id == "1737383451447231991"
    assert JobStore(config.paths.jobs_dir).get(job.id).post.mode is None  # nothing saved
    assert check_post.main(["no-such-job"]) == 2
