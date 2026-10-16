"""Picking the product photos from Telegram: numbered collage + inline buttons, then the job runs on."""

import json

import pytest
from PIL import Image

from app.job_models import JobStatus, TelegramOrigin
from app.steps.step_types import JobContext
from app.telegram.telegram_listener import TelegramListener
from app.telegram.telegram_pick import PickHandler, keyboard, make_collage, parse, send_picker, toggle

from .test_link_jobs import URL
from .test_pipeline_runner import drain, rig  # noqa: F401  (fixture re-export)

ME, CHAT, LINK_MSG, PICKER_MSG = 111222333, 111222333, 7, 99
NAMES = [f"{i:02d}.jpg" for i in range(1, 6)]


class FakeApi:
    def __init__(self):
        self.photos, self.markups, self.captions, self.answers = [], [], [], []

    def send_photo(self, chat_id, path, caption, reply_to=None, reply_markup=None):
        assert path.exists()
        self.photos.append({"chat_id": chat_id, "caption": caption, "reply_to": reply_to, "markup": reply_markup})
        return PICKER_MSG

    def edit_reply_markup(self, chat_id, message_id, reply_markup):
        self.markups.append((chat_id, message_id, reply_markup))

    def edit_caption(self, chat_id, message_id, caption):
        self.captions.append((chat_id, message_id, caption))

    def answer_callback(self, callback_id, text=""):
        self.answers.append((callback_id, text))


def labels(markup):
    return [b["text"] for row in markup["inline_keyboard"] for b in row]


def tap(data, user=ME):
    return {"id": "cb", "from": {"id": user}, "data": data, "message": {"message_id": PICKER_MSG, "chat": {"id": CHAT}}}


# ---- pure parts ---------------------------------------------------------------

def test_toggle_keeps_click_order_and_the_limit():
    assert toggle([], "03.jpg", 3) == ["03.jpg"]
    assert toggle(["03.jpg", "01.jpg"], "03.jpg", 3) == ["01.jpg"]  # untick: the next one becomes the main image
    assert toggle(["a", "b", "c"], "d", 3) == ["a", "b", "c"]


def test_keyboard_shows_order_and_fits_telegram_limits():
    markup = keyboard(NAMES, ["03.jpg", "01.jpg"], "abcd1234")
    assert labels(markup) == ["✅1·2", "2", "✅3·chính", "4", "5", "▶ Bắt đầu với 2 ảnh"]
    data = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert data[0] == "p:abcd1234:0" and data[-1] == "g:abcd1234"
    assert all(len(d.encode()) <= 64 for d in data)
    assert parse("p:abcd1234:2") == ("p", "abcd1234", 2) and parse("g:abcd1234") == ("g", "abcd1234", None)
    assert parse("x") is None and parse("p:abcd1234:nope") is None


def test_collage_has_one_numbered_tile_per_photo(tmp_path):
    paths = []
    for i in range(6):
        paths.append(tmp_path / f"{i}.jpg")
        Image.new("RGB", (800, 600), (40 * i, 0, 0)).save(paths[-1])
    out = make_collage(paths, tmp_path / "collage.jpg")
    with Image.open(out) as img:
        assert img.size == (4 * 320, 2 * 320)  # 4 per row


# ---- whole flow with a real job store -------------------------------------------

@pytest.fixture
def picking(rig):
    store, runner, actions, calls, behaviour = rig

    def fetch(ctx):
        (ctx.path("candidates")).mkdir()
        for name in NAMES:
            Image.new("RGB", (64, 64), "red").save(ctx.path("candidates") / name)
        ctx.update_job(lambda j: setattr(j.source, "candidates", list(NAMES)))
        ctx.update_job(lambda j: setattr(j.source, "title", "Giày cao gót"))

    behaviour["fetch_source"] = fetch
    job = actions.create_from_link(URL, TelegramOrigin(chat_id=CHAT, message_id=LINK_MSG))
    drain(store, runner)
    api = FakeApi()
    ctx = JobContext(job=store.get(job.id), job_dir=store.job_dir(job.id), config=runner.config,
                     report=lambda p, m: None, log=lambda m: None, update_job=lambda fn: store.update(job.id, fn))
    send_picker(ctx, api)
    return store, runner, actions, api, job.id, PickHandler(actions, api, runner.config)


def test_picker_goes_to_telegram_under_the_link(picking):
    store, _, _, api, job_id, _ = picking
    (photo,) = api.photos
    assert photo["chat_id"] == CHAT and photo["reply_to"] == LINK_MSG and "Giày cao gót" in photo["caption"]
    origin = store.get(job_id).telegram
    assert origin.pick_message_id == PICKER_MSG and origin.pick_token and origin.pick_selection == []
    assert labels(photo["markup"])[:5] == ["1", "2", "3", "4", "5"]


def test_buttons_pick_images_then_start_the_job(picking):
    store, runner, _, api, job_id, handler = picking
    token = store.get(job_id).telegram.pick_token
    assert "1/3" in handler.handle(tap(f"p:{token}:2"))
    handler.handle(tap(f"p:{token}:4"))
    assert labels(api.markups[-1][2])[2] == "✅3·chính" and labels(api.markups[-1][2])[4] == "✅5·2"

    assert handler.handle(tap(f"g:{token}")) == "Bắt đầu!"
    picked = store.get(job_id)
    assert picked.input_file == "input.jpg" and picked.extra_ingredients == ["ingredient-1.jpg"]
    assert picked.status == JobStatus.queued and picked.current_step == "cutout"
    assert "Đã chọn ảnh 3, 5" in api.captions[-1][2]


def test_start_without_a_pick_only_explains(picking):
    store, _, _, _, job_id, handler = picking
    token = store.get(job_id).telegram.pick_token
    assert "ít nhất 1 ảnh" in handler.handle(tap(f"g:{token}"))
    assert store.get(job_id).gate == "pick_image"


def test_buttons_after_a_web_pick_are_removed(picking):
    store, _, actions, api, job_id, handler = picking
    token = store.get(job_id).telegram.pick_token
    actions.pick_image(job_id, candidate="02.jpg")  # picked in the web UI first
    assert "không còn chờ chọn" in handler.handle(tap(f"p:{token}:0"))
    assert api.captions and "không còn chờ chọn" in api.captions[-1][2]


def test_listener_routes_taps_and_ignores_strangers(tmp_path):
    offset = tmp_path / "offset"
    offset.write_text("0")
    seen = []

    class Api(FakeApi):
        def get_updates(self, offset, timeout=30):
            return [{"update_id": 5, "callback_query": tap("g:x")},
                    {"update_id": 6, "callback_query": tap("g:x", user=999)}]

    api = Api()
    listener = TelegramListener(api, "tok", [ME], lambda u, c, m: True, offset,
                                on_callback=lambda cb: seen.append(cb["from"]["id"]) or "ok")
    listener.poll_once()
    assert seen == [ME]                            # the stranger's tap never reaches the handler
    assert api.answers == [("cb", "ok"), ("cb", "")]  # every tap is answered so the spinner stops
    assert offset.read_text() == "7"


def test_api_asks_telegram_for_button_taps():
    import httpx
    from app.telegram.telegram_api import TelegramApi

    seen = []
    api = TelegramApi("1:T", httpx.Client(transport=httpx.MockTransport(
        lambda r: seen.append(r) or httpx.Response(200, json={"ok": True, "result": []}))))
    api.get_updates(0)
    assert "callback_query" in json.loads(seen[0].url.params["allowed_updates"])
