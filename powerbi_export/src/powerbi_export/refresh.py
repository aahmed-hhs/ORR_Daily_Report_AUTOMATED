"""Refresh the report's semantic model from the Power BI service UI and wait for it.

Flow (same as doing it by hand):
    report page  ->  "..." (More options) in the top action bar
                 ->  "View semantic model"
                 ->  "Refresh" at the top of the semantic model page  ->  "Refresh now"
                 ->  wait until the page's "Refreshed" time changes (or the timeout passes)
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page


def _visible(loc):
    return loc.filter(visible=True)


def _top_more_options(page: Page):
    """The '...' button in the report's top action bar (not a visual's '...')."""
    cands = _visible(page.get_by_role("button", name=re.compile(r"more options", re.I)))
    best, best_y = None, 1e9
    for i in range(cands.count()):
        b = cands.nth(i).bounding_box()
        if b and b["y"] < best_y:
            best, best_y = cands.nth(i), b["y"]
    if best is not None and best_y < 160:
        return best
    for sel in ("#reportActionBar button[aria-label*='More options' i]",
                "[data-testid='app-bar'] button[aria-label*='More' i]",
                "button[aria-label='More options']", "button[title='More options']"):
        loc = _visible(page.locator(sel)).first
        if loc.count():
            return loc
    return None


def _refreshed_text(page: Page) -> str:
    """The semantic model page's last-refresh line, e.g. 'Refreshed 10/19/26, 6:02:14 AM'.
    Deliberately ignores the bare 'Refresh' button label."""
    try:
        return page.evaluate(
            """() => {
                 const t = (document.body && document.body.innerText) || '';
                 const m = t.match(/\\b(Refreshed|Last refresh(ed)?|Data updated)\\b[^\\n]{0,60}/i);
                 return m ? m[0].trim() : '';
               }""")
    except Exception:  # noqa: BLE001
        return ""


def _refresh_in_progress(page: Page) -> bool:
    try:
        return page.evaluate(
            """() => /\\b(refreshing|refresh in progress|in progress)\\b/i
                     .test((document.body && document.body.innerText) || '')""")
    except Exception:  # noqa: BLE001
        return False


def refresh_semantic_model(page: Page, report_url: str, render_wait_ms: int, timeout_min: int,
                           wait: bool = True, fail_on_timeout: bool = False, debug_dir: Path | None = None) -> bool:
    """Returns True if a refresh was triggered (and, if wait=True, seen to complete)."""
    from .export import open_page  # local import to avoid a cycle at module load

    print("Refreshing the semantic model...", flush=True)
    open_page(page, report_url, min(render_wait_ms, 4000))

    btn = _top_more_options(page)
    if btn is None:
        _debug(page, debug_dir, "debug_refresh_menu.png")
        raise SystemExit("Refresh: could not find the '...' (More options) button in the report's top bar.")
    btn.click()
    page.wait_for_timeout(800)

    item = _visible(page.get_by_role("menuitem", name=re.compile(r"view semantic model|view dataset", re.I))).first
    if not item.count():
        item = _visible(page.get_by_text(re.compile(r"^\s*view (semantic model|dataset)\s*$", re.I))).first
    if not item.count():
        seen = page.evaluate("() => Array.from(document.querySelectorAll('[role=\"menuitem\"]'))"
                             ".map(e => e.innerText.trim()).filter(Boolean)")
        _debug(page, debug_dir, "debug_refresh_menu.png")
        raise SystemExit(f"Refresh: 'View semantic model' not in the menu. Items seen: {seen}")
    item.click()

    # The semantic model page opens in the same tab (sometimes a new one).
    page.wait_for_timeout(1500)
    target = page
    for p in page.context.pages:
        if "/datasets/" in p.url and p is not page:
            target = p
            break
    try:
        target.wait_for_url(re.compile(r"/datasets/"), timeout=60_000)
    except Exception:  # noqa: BLE001
        pass
    target.wait_for_load_state("domcontentloaded")
    target.wait_for_timeout(4000)
    before = _refreshed_text(target)
    print(f"  semantic model page: {target.url}", flush=True)
    if before:
        print(f"  before: {before}", flush=True)

    refresh_btn = _visible(target.get_by_role("button", name=re.compile(r"^\s*refresh", re.I))).first
    if not refresh_btn.count():
        refresh_btn = _visible(target.get_by_text(re.compile(r"^\s*refresh\s*$", re.I))).first
    if not refresh_btn.count():
        _debug(target, debug_dir, "debug_refresh_page.png")
        raise SystemExit("Refresh: could not find the 'Refresh' button on the semantic model page.")
    refresh_btn.click()
    target.wait_for_timeout(800)
    now_item = _visible(target.get_by_role("menuitem", name=re.compile(r"refresh now", re.I))).first
    if not now_item.count():
        now_item = _visible(target.get_by_text(re.compile(r"^\s*refresh now\s*$", re.I))).first
    if now_item.count():
        now_item.click()
    print("  refresh requested", flush=True)
    target.wait_for_timeout(3000)

    # Power BI sometimes answers with a dialog (e.g. "a refresh is already in progress").
    dlg = _visible(target.get_by_role("dialog")).first
    if dlg.count():
        txt = re.sub(r"\s+", " ", dlg.inner_text() or "")[:200]
        print(f"  dialog: {txt}", flush=True)
        ok = _visible(dlg.get_by_role("button", name=re.compile(r"^(ok|close|yes|refresh)$", re.I))).first
        if ok.count():
            ok.click()

    if not wait:
        _back_to_report(page, target)
        return True

    deadline = time.monotonic() + timeout_min * 60
    print(f"  waiting up to {timeout_min} min for the refresh to finish...", flush=True)
    while time.monotonic() < deadline:
        target.wait_for_timeout(10_000)
        try:
            target.reload(wait_until="domcontentloaded")
            target.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            continue
        now = _refreshed_text(target)
        if not _refresh_in_progress(target) and (now != before or not before):
            print(f"  done: {now or 'refresh no longer in progress'}", flush=True)
            _back_to_report(page, target)
            return True
        print(f"    still refreshing... ({now or 'no timestamp yet'})", flush=True)

    msg = f"Refresh: not confirmed within {timeout_min} min (last seen: {_refreshed_text(target)!r})."
    if fail_on_timeout:
        raise SystemExit(msg)
    print("  " + msg + " Continuing with the exports.", flush=True)
    _back_to_report(page, target)
    return False


def _back_to_report(page: Page, target: Page) -> None:
    if target is not page:
        try:
            target.close()
        except Exception:  # noqa: BLE001
            pass


def _debug(page: Page, debug_dir: Path | None, name: str) -> None:
    if not debug_dir:
        return
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(debug_dir / name), timeout=8_000)
        print(f"  screenshot: {debug_dir / name}", flush=True)
    except Exception:  # noqa: BLE001
        pass
