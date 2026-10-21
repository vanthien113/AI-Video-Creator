"""Product page reader: pure filtering, plus a real-Chrome run on a local fixture page."""

import functools
import http.server
import threading

import pytest
from PIL import Image

from app.flow.chrome_launcher import cdp_tabs
from app.job_models import JobState, SourceInfo
from app.sources.product_page_reader import (
    blocked_reason, clean_title, host_is_trusted, image_key, is_public_image_url, pick_image_urls, shop_name,
)
from app.steps.fetch_product_step import run_fetch_product

CDN = "https://p16-oec-sg.ibyteimg.com/tos-alisg-i-aphluv4xwc-sg/abc123"


def test_image_key_ignores_size_variants():
    assert image_key(f"{CDN}~tplv-aphluv4xwc-resize-webp:800:800.webp?x=1") == image_key(f"{CDN}~tplv-crop:200:200.jpg")


def test_pick_image_urls_filters_and_dedupes():
    images = [
        {"src": f"{CDN}~tplv-resize:800:800.webp", "w": 800, "h": 800},   # same as og image
        {"src": "https://cdn.x/icon.png", "w": 64, "h": 64},               # too small
        {"src": "https://cdn.x/banner.png", "w": 1200, "h": 300},          # too thin
        {"src": "https://cdn.x/p2.jpg", "w": 700, "h": 700},
        {"src": "data:image/png;base64,AAA", "w": 900, "h": 900},
        {"src": "https://cdn.x/anim.gif", "w": 900, "h": 900},
    ]
    assert pick_image_urls([f"{CDN}~tplv-resize:1200:1200.jpg"], images) == [
        f"{CDN}~tplv-resize:1200:1200.jpg", "https://cdn.x/p2.jpg"]
    many = [{"src": f"https://cdn.x/{i}.jpg", "w": 600, "h": 600} for i in range(30)]
    assert len(pick_image_urls([], many, limit=12)) == 12


def test_blocked_reason_recognises_firewall_and_errors():
    fortigate = "FortiGate Application Control | Application Blocked | You have attempted to use an application " \
                "that violates your Internet usage policy. | Application TikTok"
    assert "tường lửa" in blocked_reason(403, "Application Control Violation", fortigate)
    assert "HTTP 500" in blocked_reason(500, "", "")
    assert "xác minh" in blocked_reason(200, "TikTok", "Drag the slider: slide to complete the puzzle")
    assert blocked_reason(200, "Son Kem Lì", "Mô tả sản phẩm") is None


def test_only_public_https_images_and_tiktok_pages():
    assert is_public_image_url("https://p16-oec-sg.ibyteimg.com/a.jpg")
    for bad in ("http://cdn.x/a.jpg", "https://127.0.0.1:8765/api/jobs", "https://192.168.1.10/a.jpg",
                "https://localhost/a.jpg", "file:///etc/passwd", "javascript:alert(1)"):
        assert not is_public_image_url(bad), bad
    assert host_is_trusted("https://shop.tiktok.com/vn/pdp/1")
    assert not host_is_trusted("https://evil-tiktok.com/x") and not host_is_trusted("https://tiktok.com.evil.io/")


@pytest.mark.parametrize("lines,shop", [(["Sold by LOURA"], "LOURA"), (["Được bán bởi  Giày Xinh Shoes "], "Giày Xinh Shoes"),
                                        (["149 sold"], ""), ([], "")])
def test_shop_name_from_the_sold_by_line(lines, shop):
    assert shop_name(lines) == shop


def test_clean_title():
    assert clean_title("Son Kem Lì Black Rouge | TikTok Shop") == "Son Kem Lì Black Rouge"


FIXTURE = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="Kem Chống Nắng XYZ | TikTok Shop">
<meta property="og:description" content="SPF50+ PA++++, 50ml">
<meta property="og:image" content="/main.jpg">
</head><body><h1>Kem Chống Nắng XYZ</h1>
<img src="/main.jpg"><img src="/side.jpg"><img src="/icon.jpg">
<div>Sold by XYZ Beauty Store</div></body></html>"""


@pytest.fixture
def fixture_site(tmp_path):
    (tmp_path / "index.html").write_text(FIXTURE, encoding="utf-8")
    for name, size in (("main.jpg", 900), ("side.jpg", 700), ("icon.jpg", 64)):
        Image.new("RGB", (size, size), "blue").save(tmp_path / name)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    server.shutdown()


@pytest.mark.skipif(cdp_tabs(9222) is None, reason="tool Chrome (CDP 9222) is not running")
def test_fetch_step_on_local_fixture_with_real_chrome(make_context, fixture_site, monkeypatch):
    monkeypatch.setattr("app.steps.fetch_product_step.notify", lambda *a: None)
    # The fixture is served from 127.0.0.1 over http, which production rules rightly refuse.
    monkeypatch.setattr("app.sources.product_page_reader.TRUSTED_PAGE_HOST", "127.0.0.1")
    monkeypatch.setattr("app.sources.product_page_reader.is_public_image_url", lambda url: url.startswith("http"))
    job = JobState(id="t", name="tiktok-1", input_file="", created_at="t", current_step="fetch_source",
                   source=SourceInfo(url=fixture_site))
    ctx = make_context(job=job)

    run_fetch_product(ctx)

    saved = ctx.holder["job"]
    assert saved.source.title == "Kem Chống Nắng XYZ"
    assert saved.source.candidates == ["01.jpg", "02.jpg"]  # og image first, icon dropped
    assert saved.product_info.startswith("Kem Chống Nắng XYZ\nSPF50+")
    assert saved.name == "kem-chong-nang-xyz"
    assert saved.source.shop == "XYZ Beauty Store"
    with Image.open(ctx.path("candidates/01.jpg")) as first:
        assert first.size == (900, 900)


# The page text under "Product description", as read on 2026-10-17 (the og:description meta tag only says
# "Buy <title> on TikTok Shop. Discover great prices on Dép lê…", which repeats the title with the wrong category).
DESCRIPTION_BLOCK = """Product description
[5590-CHÂN DÀY TĂNG SZ] Giày búp bê phối khuy xinh xắn đi mềm êm chân thiết kế basic
·
Kiến nghị chọn size: chuẩn sz
·
Size: full size 35/36/37/38/39
·
Đế: đế bệt, chất liệu cao su non đi êm chân và bền, bản đế chống trơn trượt tốt
Nếu bạn còn thắc mắc về sản phẩm, size số hãy ib cho chúng mình để được hỗ trợ nhanh nhất.
View more"""


def test_real_description_replaces_the_seo_sentence():
    from app.sources.product_page_reader import clean_description

    text = clean_description(DESCRIPTION_BLOCK, "[5590-CHÂN DÀY TĂNG SZ] Giày búp bê phối khuy xinh xắn đi mềm êm chân thiết kế basic")
    assert text.startswith("Kiến nghị chọn size: chuẩn sz\nSize: full size 35/36/37/38/39\nĐế: đế bệt")
    assert "Product description" not in text and "View more" not in text and "·" not in text
    assert "Giày búp bê phối khuy" not in text  # the title is sent on its own line already
    assert clean_description("", "x") == ""
    assert clean_description("Mô tả sản phẩm\nChất liệu: da PU\nXem thêm", "x") == "Chất liệu: da PU"


SEO = ("Buy Dép sandal lỗ nữ mới 2026 on TikTok Shop. Discover great prices on Dép lê and get free shipping "
       "on eligible items. Shop now for exclusive deals!")


def test_pick_description_prefers_the_real_text_and_drops_tiktoks_seo_sentence():
    from app.sources.product_page_reader import pick_description

    title = "[5590-GẦY MẢNH LÙI SZ] Giày búp bê phối khuy xinh xắn đi mềm êm chân thiết kế basic"
    assert pick_description(DESCRIPTION_BLOCK, SEO, title).startswith("Kiến nghị chọn size")
    # Image-only descriptions ("Product description / View more"): no text, and the SEO line says nothing new.
    assert pick_description("Product description\nView more", SEO, "Dép sandal lỗ nữ") == ""
    assert pick_description("", "SPF50+ PA++++, 50ml", "Kem") == "SPF50+ PA++++, 50ml"  # a real meta description
