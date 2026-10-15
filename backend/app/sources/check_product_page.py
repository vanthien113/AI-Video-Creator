"""Read one TikTok Shop link and print what the tool would extract (no job, no download).

Usage (from backend/):  ../.venv/bin/python -m app.sources.check_product_page <link>
"""

import sys

from ..config import load_config
from ..flow.cdp_connection import BrowserNotRunning, browser_context
from .product_page_reader import SourceError, read_product_page


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        with browser_context(load_config().flow.cdp_port) as context:
            page = context.new_page()
            try:
                product = read_product_page(page, sys.argv[1])
            finally:
                page.close()
    except (BrowserNotRunning, SourceError) as exc:
        print(f"✖ {exc}")
        return 1
    print(f"✔ Trang: {product.url}\n  Tên: {product.title}\n  Mô tả: {product.description[:200]}")
    print(f"  {len(product.image_urls)} ảnh:")
    for url in product.image_urls:
        print(f"   - {url[:140]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
