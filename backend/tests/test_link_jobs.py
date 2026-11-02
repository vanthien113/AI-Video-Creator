"""Link jobs: TikTok link → candidates → pick gate → runs straight through."""

import io

import pytest
from PIL import Image

from app.job_actions import InvalidAction
from app.job_models import JobStatus, TelegramMessageRef, TelegramOrigin
from app.telegram import telegram_setup
from app.telegram.telegram_api import TelegramApiError
from app.telegram.telegram_setup import channel_copy_handler, link_handler

from .test_pipeline_runner import UPLOAD_STEPS, drain, new_job, rig  # noqa: F401  (fixture re-export)

URL = "https://shop.tiktok.com/vn/pdp/1737628275640009880?_t=abc"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
    return buf.getvalue()


def fake_fetch(store):
    def step(ctx):
        folder = ctx.path("candidates")
        folder.mkdir()
        for name in ("01.jpg", "02.jpg"):
            Image.new("RGB", (600, 600), "red").save(folder / name)

        def save(j):
            j.source.title, j.source.candidates = "Son Kem Lì", ["01.jpg", "02.jpg"]
            j.product_info = "Son Kem Lì\nmàu đỏ"

        ctx.update_job(save)

    return step


def test_link_job_waits_for_pick_then_runs_straight_through(rig):
    store, runner, actions, calls, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    assert job.current_step == "fetch_source" and all(job.auto_gates.values())

    drain(store, runner)
    waiting = store.get(job.id)
    assert waiting.status == JobStatus.awaiting_review and waiting.gate == "pick_image"
    with pytest.raises(InvalidAction):
        actions.approve(job.id)  # must pick an image, not just approve

    actions.pick_image(job.id, candidate="02.jpg", product_info="Son Kem Lì đỏ")
    picked = store.get(job.id)
    assert picked.input_file == "input.jpg" and picked.product_info == "Son Kem Lì đỏ"
    assert (store.job_dir(job.id) / "input.jpg").exists()

    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    assert calls == ["fetch_source"] + UPLOAD_STEPS


def test_pick_rejects_foreign_or_missing_candidates(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    drain(store, runner)
    for bad in ("../state.json", "03.jpg"):
        with pytest.raises(InvalidAction):
            actions.pick_image(job.id, candidate=bad)
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id)
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id, upload=("x.sh", b"#!"))
    assert store.get(job.id).gate == "pick_image"


def test_pick_after_candidate_files_vanished_is_a_clear_error(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    job = actions.create_from_link(URL)
    drain(store, runner)
    (store.job_dir(job.id) / "candidates" / "01.jpg").unlink()
    with pytest.raises(InvalidAction, match="không còn"):
        actions.pick_image(job.id, candidate="01.jpg")
    assert not list(store.job_dir(job.id).glob("input*"))


def test_telegram_origin_is_kept_for_the_reply(rig):
    _, _, actions, _, _ = rig
    job = actions.create_from_link(URL, TelegramOrigin(chat_id=111, message_id=42))
    assert (job.telegram.chat_id, job.telegram.message_id) == (111, 42)
    assert actions.create_from_link(URL.replace("abc", "zzz")).telegram is None  # pasted in the UI


class TopicApi:
    def __init__(self, topics_on=True):
        self.topics_on, self.created, self.sent = topics_on, [], []

    def create_forum_topic(self, chat_id, name):
        if not self.topics_on:
            raise TelegramApiError("createForumTopic: Bad Request: the chat is not a forum")
        self.created.append((chat_id, name))
        return 70 + len(self.created)

    def send_message(self, chat_id, text, thread_id=None):
        self.sent.append((chat_id, text, thread_id))


def test_each_telegram_link_gets_its_own_topic(rig):
    _, _, actions, _, _ = rig
    api = TopicApi()
    on_link = link_handler(actions, api)
    assert on_link(URL, 111, 42)
    assert not on_link(URL, 111, 43)  # already queued: no second, empty topic
    assert len(api.created) == 1 and api.sent == []  # the status message will be the topic's first message
    assert actions.open_link_job(URL).telegram.target() == (111, {"thread_id": 71})


def test_with_topics_off_the_job_replies_under_the_link(rig):
    _, _, actions, _, _ = rig
    assert link_handler(actions, TopicApi(topics_on=False))(URL, 111, 42)
    assert actions.open_link_job(URL).telegram.target() == (111, {"reply_to": 42})


def test_the_channel_posts_copy_is_where_the_jobs_comments_go(rig, monkeypatch):
    store, _, actions, _, _ = rig
    monkeypatch.setattr(telegram_setup, "COPY_WAIT_SEC", 0)
    channel, group, api = -100123, -100777, TopicApi()
    assert link_handler(actions, api, topics=False)(URL, 111, 42)
    assert api.created == []  # channel mode: the post and its comments replace the topic
    job = actions.open_link_job(URL)
    store.update(job.id, lambda j: setattr(j, "status_message", TelegramMessageRef(chat_id=channel, message_id=9)))
    on_copy = channel_copy_handler(store, channel)
    on_copy(-100999, 9, group, 3)  # another channel's post
    on_copy(channel, 8, group, 3)  # a post that is not this job's
    assert store.get(job.id).telegram.target() == (111, {"reply_to": 42})
    on_copy(channel, 9, group, 4)
    assert store.get(job.id).telegram.target() == (group, {"reply_to": 4})


def test_duplicate_link_ignored_until_finished(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = fake_fetch(store)
    first = actions.create_from_link(URL)
    assert actions.create_from_link(URL) is None
    actions.cancel(first.id)
    assert actions.create_from_link(URL) is not None


def test_own_image_after_fetch_failure(rig):
    store, runner, actions, _, behaviour = rig
    behaviour["fetch_source"] = InvalidAction("blocked")  # any exception → step fails
    job = actions.create_from_link(URL)
    drain(store, runner)
    assert store.get(job.id).error.step == "fetch_source"
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "cutout")  # no image yet
    with pytest.raises(InvalidAction):
        actions.pick_image(job.id, upload=("photo.png", b"not an image"))
    actions.pick_image(job.id, upload=("photo.png", png_bytes()))
    assert store.get(job.id).input_file == "input.png"
    assert store.get(job.id).status == JobStatus.queued


def test_upload_jobs_still_start_at_cutout_and_cannot_fetch(rig):
    store, runner, actions, calls, _ = rig
    job = new_job(store)
    assert job.current_step == "cutout"
    drain(store, runner)
    with pytest.raises(InvalidAction):
        actions.retry(job.id, "fetch_source")
    assert "fetch_source" not in calls
