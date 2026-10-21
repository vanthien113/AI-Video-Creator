"""A Shopee link for the product, found from the main photo: Google Lens, then up to shopee.max_candidates
product pages (shop name, sold count, stars) read from Shopee's own pdp JSON. Fake browser, no network."""

from contextlib import contextmanager

import pytest

from app.config import ShopeeConfig
from app.job_models import JobState, ShopeeListing, SourceInfo
from app.sources.shopee_search import (
    ShopeeBlocked, listing_from_pdp, parse_sold, pick_listing, product_url, product_urls, read_listing, same_shop,
)
from app.steps import shopee_step
from app.steps.shopee_step import run_shopee

SLUG = "https://shopee.vn/D%C3%A9p-cross-hai-quai-n%E1%BB%AF-CV215-i.233428276.27079774899?extraParams=%7B%7D"
AD = "https://shopee.vn/product/1414757953/44119153976?gads_t_sig=abc"


def test_product_url_drops_the_slug_and_tracking():
    assert product_url(SLUG) == "https://shopee.vn/product/233428276/27079774899"
    assert product_url(AD) == "https://shopee.vn/product/1414757953/44119153976"
    assert product_url("https://shopee.vn/") is None  # home page, shop page...: not a product


def test_product_urls_keep_google_order_without_repeats():
    links = [SLUG, "https://shopee.vn/search?keyword=dep", AD, SLUG.replace("?extraParams=%7B%7D", "")]
    assert product_urls(links, 5) == ["https://shopee.vn/product/233428276/27079774899",
                                      "https://shopee.vn/product/1414757953/44119153976"]
    assert len(product_urls(links, 1)) == 1


@pytest.mark.parametrize("display,count", [("10k+", 10000), ("1,2k", 1200), ("1.2k", 1200), ("956", 956),
                                           ("1,5tr", 1500000), ("2m+", 2000000), ("", 0), (None, 0)])
def test_parse_sold(display, count):
    assert parse_sold(display) == count


def test_listing_from_pdp_json():
    data = {"data": {"item": {"item_rating": {"rating_star": 4.87}},
                     "product_review": {"sold_count_display": "10k+"},
                     "shop_detailed": {"name": "Xuka shop "}}}
    assert listing_from_pdp(data, "https://shopee.vn/product/1/2") == ShopeeListing(
        url="https://shopee.vn/product/1/2", shop="Xuka shop", sold=10000, rating=4.87)


class FakePage:
    """goto() lands on `lands_on`; the pdp response arrives unless Shopee showed its bot check."""

    def __init__(self, lands_on, pdp=None):
        self.url, self.lands_on, self.pdp = "about:blank", lands_on, pdp

    @contextmanager
    def expect_response(self, predicate, timeout):
        holder = type("Response", (), {})()
        yield holder
        if self.pdp is None:
            raise TimeoutError("no pdp response")
        holder.value = type("Value", (), {"json": lambda _self: self.pdp})()

    def goto(self, url, **_):
        self.url = self.lands_on


PDP = {"data": {"item": {"item_rating": {"rating_star": 4.5}}, "product_review": {"sold_count_display": "1,2k"},
                "shop_detailed": {"name": "LOURA"}}}


def test_read_listing_from_the_product_page():
    url = "https://shopee.vn/product/1/2"
    assert read_listing(FakePage(url, PDP), url) == ShopeeListing(url=url, shop="LOURA", sold=1200, rating=4.5)


def test_read_listing_stops_on_the_bot_check():
    with pytest.raises(ShopeeBlocked):
        read_listing(FakePage("https://shopee.vn/verify/traffic?anti_bot_tracking_id=x"), "https://shopee.vn/product/1/2")
    with pytest.raises(ShopeeBlocked):  # the data may still arrive before the redirect
        read_listing(FakePage("https://shopee.vn/verify/captcha", PDP), "https://shopee.vn/product/1/2")


@pytest.mark.parametrize("tiktok,shopee,same", [
    ("LOURA", "loura.official", True), ("Giày Xinh Shoes", "giayxinh", True), ("Xuka", "Xuka shop ", True),
    ("LOURA", "Xuka shop", False), ("Shop", "Mely shop", False), ("", "Xuka shop", False),
])
def test_same_shop_ignores_case_accents_and_generic_words(tiktok, shopee, same):
    assert same_shop(tiktok, shopee) is same


def test_pick_prefers_the_tiktok_shop_then_sales_then_stars():
    a = ShopeeListing(url="a", shop="Xuka shop", sold=10000, rating=4.9)
    b = ShopeeListing(url="b", shop="LOURA", sold=50, rating=4.1)
    c = ShopeeListing(url="c", shop="Mely", sold=10000, rating=4.95)
    assert pick_listing([a, b, c], "loura").url == "b"
    assert pick_listing([a, b, c], "Không có").url == "c"  # same sales: more stars
    assert pick_listing([], "LOURA") is None


class FakeBrowser:
    def __init__(self, links, listings):
        self.links_found, self.listings, self.read = links, listings, []

    def links(self, image):
        assert image.exists()
        return self.links_found

    def listing(self, url):
        self.read.append(url)
        found = self.listings[url]
        if isinstance(found, Exception):
            raise found
        return found


PRODUCTS = [f"https://shopee.vn/product/{n}/{n}" for n in range(1, 6)]


@pytest.fixture
def shopee_job(make_context, make_config, monkeypatch):
    def build(listings, links=PRODUCTS, shop="LOURA", **shopee_cfg):
        job = JobState(id="t", name="dep", input_file="input.jpg", created_at="t",
                       source=SourceInfo(url="https://shop.tiktok.com/vn/pdp/1", title="Dép", shop=shop))
        ctx = make_context(job=job, config=make_config(shopee=ShopeeConfig(**shopee_cfg)))
        ctx.path("input.jpg").write_bytes(b"jpg")
        browser = FakeBrowser(links, listings)

        @contextmanager
        def fake_open(_ctx):
            yield browser

        monkeypatch.setattr(shopee_step, "open_browser", fake_open)
        return ctx, browser

    return build


def listings(*shops, sold=(100, 200, 300, 400, 500)):
    return {url: ShopeeListing(url=url, shop=shop, sold=s) for url, shop, s in zip(PRODUCTS, shops, sold)}


def test_reads_at_most_max_candidates_and_keeps_the_best_seller(shopee_job):
    ctx, browser = shopee_job(listings("A", "B", "C", "D", "E"), max_candidates=3)
    run_shopee(ctx)
    assert browser.read == PRODUCTS[:3]
    assert ctx.job.shopee.url == PRODUCTS[2]  # most sold of the three read


def test_stops_at_the_tiktok_shop(shopee_job):
    ctx, browser = shopee_job(listings("A", "Loura Official", "C", "D", "E"))
    run_shopee(ctx)
    assert browser.read == PRODUCTS[:2] and ctx.job.shopee.shop == "Loura Official"


def test_no_shopee_page_opens_so_the_first_google_result_goes_marked(shopee_job):
    found = listings("A", "B", "C", "D", "E")
    found[PRODUCTS[0]] = ShopeeBlocked("Shopee yêu cầu xác minh")
    ctx, browser = shopee_job(found)
    run_shopee(ctx)
    assert browser.read == PRODUCTS[:1]  # stops at the bot check
    assert ctx.job.shopee == ShopeeListing(url=PRODUCTS[0], checked=False)


def test_a_bot_check_after_some_pages_keeps_the_best_of_those(shopee_job):
    found = listings("A", "B", "C", "D", "E")
    found[PRODUCTS[1]] = ShopeeBlocked("Shopee yêu cầu xác minh")
    ctx, browser = shopee_job(found)
    run_shopee(ctx)
    assert browser.read == PRODUCTS[:2] and ctx.job.shopee.url == PRODUCTS[0] and ctx.job.shopee.checked


def test_a_page_that_will_not_load_counts_as_not_opened(shopee_job):
    found = listings("A", "B", "C", "D", "E")
    found[PRODUCTS[0]] = RuntimeError("Chrome went away")
    ctx, _ = shopee_job(found)
    run_shopee(ctx)  # no exception
    assert ctx.job.shopee == ShopeeListing(url=PRODUCTS[0], checked=False)


def test_a_google_error_means_no_link_and_never_fails_the_job(shopee_job):
    ctx, browser = shopee_job(listings("A", "B", "C", "D", "E"))
    browser.links = lambda image: (_ for _ in ()).throw(RuntimeError("Google yêu cầu xác minh (captcha)"))
    run_shopee(ctx)
    assert ctx.job.shopee is None


def test_switched_off_does_nothing(shopee_job):
    ctx, browser = shopee_job(listings("A", "B", "C", "D", "E"), enabled=False)
    run_shopee(ctx)
    assert browser.read == [] and ctx.job.shopee is None


def test_no_shopee_result_on_google(shopee_job):
    ctx, browser = shopee_job({}, links=["https://shopee.vn/"])
    run_shopee(ctx)
    assert browser.read == [] and ctx.job.shopee is None


def test_max_candidates_is_a_setting():
    assert ShopeeConfig().max_candidates == 3
    with pytest.raises(ValueError):
        ShopeeConfig(max_candidates=0)
