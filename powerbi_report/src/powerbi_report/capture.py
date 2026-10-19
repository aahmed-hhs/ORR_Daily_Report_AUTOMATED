from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import PageSpec, Settings

CANVAS_SELECTORS = "#reportLandingContainer, .displayArea, exploration-container"
VISUAL_SELECTORS = "visual-container, .visualContainer, [class*='visualContainer']"
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


class _CdpHolder:
    """Close only our tab, never the user's whole browser."""

    def __init__(self, browser, page):
        self.browser, self.page = browser, page

    def close(self):
        try:
            self.page.close()
        finally:
            self.browser.close()  # detaches from CDP; does not quit Edge


def _open(p, s: Settings, headless: bool):
    """Return (holder, page).

    Three modes, in order of preference on a managed PC:
      1. cdp_url set   -> attach to an Edge started with --remote-debugging-port
      2. profile_dir   -> Playwright-owned persistent Edge profile
      3. otherwise     -> throwaway context seeded from auth.json
    """
    if s.cdp_url:
        try:
            browser = p.chromium.connect_over_cdp(s.cdp_url)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(
                f"Could not connect to Edge at {s.cdp_url}.\n"
                "Run scripts\\start_edge_debug.bat and leave that Edge open.\n"
                f"(details: {e})"
            ) from e
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        print(f"Attached to Edge at {s.cdp_url}", flush=True)
        page = ctx.new_page()
        page.set_viewport_size(s.viewport)
        return _CdpHolder(browser, page), page

    if s.profile_dir:
        s.profile_dir.mkdir(parents=True, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(
            str(s.profile_dir),
            channel=s.browser_channel,
            headless=headless,
            viewport=s.viewport,
            args=LAUNCH_ARGS,
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return ctx, page

    browser = p.chromium.launch(channel=s.browser_channel, headless=headless, args=LAUNCH_ARGS,
                                ignore_default_args=["--enable-automation"])
    state = str(s.auth_file) if s.auth_file.exists() else None
    ctx = browser.new_context(storage_state=state, viewport=s.viewport)
    return browser, ctx.new_page()


def _visuals_bounding_box(page, pad: int, exclude_text: list[str]) -> dict | None:
    """Smallest box containing the report visuals, plus padding.

    Skips visuals whose text contains any phrase in exclude_text, and skips
    oversized elements (backgrounds / page containers) that would swallow the
    whole canvas.
    """
    vp = page.viewport_size or {"width": 1920, "height": 1080}
    boxes = page.evaluate(
        """() => Array.from(document.querySelectorAll('visual-container, .visualContainer'))
                 .map(e => { const r = e.getBoundingClientRect();
                             return {x: r.left, y: r.top, w: r.width, h: r.height,
                                     text: (e.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60)}; })
                 .filter(r => r.w > 0 && r.h > 0)"""
    )
    if not boxes:
        print("  no visuals found on the page", flush=True)
        return None
    keep = []
    max_area = 0.85 * vp["width"] * vp["height"]
    for b in boxes:
        why = ""
        if b["w"] * b["h"] > max_area:
            why = "background/oversized"
        elif any(t.lower() in b["text"].lower() for t in exclude_text if t):
            why = "excluded by text"
        flag = f"  SKIP ({why})" if why else "  keep"
        print(f"{flag}: x={b['x']:.0f} y={b['y']:.0f} w={b['w']:.0f} h={b['h']:.0f}  '{b['text']}'", flush=True)
        if not why:
            keep.append(b)
    if not keep:
        return None
    x0 = max(0, min(b["x"] for b in keep) - pad)
    y0 = max(0, min(b["y"] for b in keep) - pad)
    x1 = min(vp["width"], max(b["x"] + b["w"] for b in keep) + pad)
    y1 = min(vp["height"], max(b["y"] + b["h"] for b in keep) + pad)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _wait_for_visuals(page, render_wait_ms: int) -> None:
    print("Waiting for visuals...", flush=True)
    try:
        page.wait_for_selector(VISUAL_SELECTORS, state="attached", timeout=60_000)
    except Exception:  # noqa: BLE001
        print("  (did not detect visual containers; taking the screenshot anyway)", flush=True)
    page.wait_for_timeout(render_wait_ms)


def _goto(page, url: str) -> None:
    # Power BI never goes network-idle, so only wait for the DOM.
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(3_000)
    if "login.microsoftonline" in page.url:
        raise SystemExit("Power BI asked for sign-in. Sign in in the Edge window, then rerun.")


def _click_page_tab(page, name: str) -> bool:
    """Switch to the report page whose tab/list entry reads exactly `name`.

    Power BI shows pages either as tabs along the bottom or as a list in the
    "Pages" pane on the left, and the markup differs between the two looks, so
    try a few locators from most to least specific.
    """
    exact = re.compile(rf"^\s*{re.escape(name)}\s*$", re.IGNORECASE)
    candidates = [
        page.get_by_role("tab", name=exact),
        page.get_by_role("button", name=exact),
        page.get_by_role("link", name=exact),
        page.get_by_role("listitem", name=exact),
        page.get_by_role("option", name=exact),
        page.locator("[class*='pageNavigation'], [class*='page-navigation'], [class*='pbi-tab'], "
                     "mat-list-item, [data-testid*='page']").filter(has_text=exact),
        page.get_by_text(name, exact=True),
    ]
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            loc.first.scroll_into_view_if_needed(timeout=5_000)
            loc.first.click(timeout=10_000)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _show_page(page, s: Settings, spec: PageSpec, first: bool) -> None:
    """Make `spec` the page on screen, by URL or by clicking its tab."""
    if spec.url:
        print(f"Opening page '{spec.name or spec.file}' by URL...", flush=True)
        _goto(page, spec.url)
        return
    if first:
        print("Opening report...", flush=True)
        _goto(page, s.report_url)
    if spec.name:
        print(f"Switching to page '{spec.name}'...", flush=True)
        before = page.url
        if not _click_page_tab(page, spec.name):
            if first:
                # report_url normally opens on this page already; carry on.
                print(f"  (tab '{spec.name}' not found; assuming report_url already shows it)", flush=True)
                return
            raise SystemExit(
                f"Could not find a page tab named '{spec.name}'. Check the exact name at the\n"
                "bottom/side of the report, or copy its URL into config.yaml under pages -> url."
            )
        page.wait_for_timeout(2_000)
        if page.url != before:
            print(f"  now at {page.url}", flush=True)


def _screenshot_page(page, spec: PageSpec, png_path: Path) -> None:
    print("Taking screenshot...", flush=True)
    clip = spec.crop or _visuals_bounding_box(page, spec.crop_padding, spec.crop_exclude_text)
    if clip and spec.crop_trim:
        t = spec.crop_trim
        clip = {
            "x": clip["x"] + t.get("left", 0),
            "y": clip["y"] + t.get("top", 0),
            "width": clip["width"] - t.get("left", 0) - t.get("right", 0),
            "height": clip["height"] - t.get("top", 0) - t.get("bottom", 0),
        }
    if clip:
        print(f"  cropping to x={clip['x']} y={clip['y']} w={clip['width']} h={clip['height']}", flush=True)
        page.screenshot(path=str(png_path), clip=clip)
    else:
        target = page.query_selector(CANVAS_SELECTORS)
        (target or page).screenshot(path=str(png_path))
    print(f"Captured {png_path}", flush=True)


def login(s: Settings) -> None:
    """Open a visible browser, let the user sign in, persist the session."""
    if s.cdp_url:
        print("cdp_url is set: you are using your own Edge, so there is nothing to save.")
        print("Just sign in to Power BI in that Edge window, then run the tool normally.")
        return
    with sync_playwright() as p:
        holder, page = _open(p, s, headless=False)
        page.goto(s.report_url)
        print("A browser window is open. Sign in, wait until the report is fully drawn,")
        input("then press Enter here to save the session... ")
        if s.profile_dir:
            print(f"Session kept in Edge profile at {s.profile_dir}")
        else:
            s.auth_file.parent.mkdir(parents=True, exist_ok=True)
            page.context.storage_state(path=str(s.auth_file))
            print(f"Saved session to {s.auth_file}")
        holder.close()


def capture_pages(s: Settings, targets: list[tuple[PageSpec, Path]], headless: bool = True) -> None:
    """Screenshot several report pages in one browser session.

    `targets` pairs each PageSpec with the PNG path to write.
    """
    if not s.cdp_url and not s.profile_dir and not s.auth_file.exists():
        raise SystemExit(f"No session at {s.auth_file}. Run with --login first.")
    for _, png in targets:
        png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        holder, page = _open(p, s, headless=headless)
        try:
            for i, (spec, png) in enumerate(targets):
                _show_page(page, s, spec, first=(i == 0))
                _wait_for_visuals(page, s.render_wait_ms)
                _screenshot_page(page, spec, png)
        finally:
            holder.close()


def capture(s: Settings, png_path: Path, headless: bool = True) -> Path:
    """Screenshot a single page (the first configured one). Kept for compatibility."""
    capture_pages(s, [(s.pages[0], png_path)], headless=headless)
    return png_path
