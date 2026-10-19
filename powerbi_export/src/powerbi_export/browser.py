from __future__ import annotations

import os
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


def bypass_proxy_for_localhost() -> None:
    """Corporate proxies swallow 127.0.0.1; make sure local traffic skips them."""
    for var in ("NO_PROXY", "no_proxy"):
        parts = [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in parts:
                parts.append(host)
        os.environ[var] = ",".join(parts)


@contextmanager
def attached_page(cdp_url: str, accept_downloads: bool = True, viewport: dict | None = None):
    """Yield a fresh tab in the user's Edge (started with --remote-debugging-port)."""
    bypass_proxy_for_localhost()
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(
                f"Could not connect to Edge at {cdp_url}.\n"
                "Start Edge with --remote-debugging-port=9222 (see README) and leave it open.\n"
                f"(details: {e})"
            ) from e
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=accept_downloads)
        print(f"Attached to Edge at {cdp_url}", flush=True)
        page = ctx.new_page()
        if viewport:
            page.set_viewport_size(viewport)   # render the report at this size regardless of the window
        try:
            yield page
        finally:
            try:
                page.close()
            finally:
                browser.close()  # detach only; Edge stays open