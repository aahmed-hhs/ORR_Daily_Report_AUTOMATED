"""Drive Power BI's 'Export data' menu for a visual and save the download."""
from __future__ import annotations

import datetime as dt
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page

from .browser import attached_page
from .config import ExportJob, Settings
from .postprocess import to_classic_layout

VISUAL_SEL = ".visualContainer, visual-container, visual-container-modern, [class*='visualContainer']"
MORE_BTN_SEL = (
    "button[aria-label*='More options' i], button[title*='More options' i], "
    "[data-testid='visual-more-options-btn'], button.vcMenuBtn, "
    "visual-container-header button, .visualHeader button[aria-label*='option' i]"
)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip().lower()


def find_visual(page: Page, visual_text: str) -> dict:
    """Locate the visual containing visual_text.

    Returns {'x','y','w','h','text','idx'} where idx is the position of the
    matching visual-container among all visual-containers on the page.
    """
    cands = page.evaluate(
        """(want) => {
             const norm = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
             const out = [];
             document.querySelectorAll('visual-container, visual-container-modern').forEach((e, idx) => {
                 const r = e.getBoundingClientRect();
                 const inner = e.querySelector('.visualContainer') || e;
                 const ir = inner.getBoundingClientRect();
                 const box = (ir.width > 20 && ir.height > 20) ? ir : r;
                 const text = norm(e.innerText);
                 if (box.width > 20 && box.height > 20 && text.includes(norm(want))) {
                     out.push({idx, x: box.left, y: box.top, w: box.width, h: box.height,
                               text: text.slice(0, 80)});
                 }
             });
             return out;
           }""",
        visual_text,
    )
    if not cands:
        seen = page.evaluate(
            """() => Array.from(document.querySelectorAll('visual-container, visual-container-modern'))
                     .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60)).filter(Boolean)"""
        )
        raise SystemExit(f"No visual containing {visual_text!r} on this page.\nVisuals seen:\n  - "
                         + "\n  - ".join(sorted(set(seen))))
    cands.sort(key=lambda c: c["w"] * c["h"])     # tightest match = the visual itself
    return cands[0]


def _hover_visual(page: Page, box: dict) -> None:
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    page.mouse.move(cx, cy)
    page.wait_for_timeout(400)
    page.mouse.move(cx + 5, cy + 5)
    page.wait_for_timeout(700)


def _menu_button_rect(page: Page, idx: int) -> dict | None:
    """Bounding rect of the '...' button that belongs to visual-container #idx."""
    return page.evaluate(
        """(idx) => {
             const vcs = document.querySelectorAll('visual-container, visual-container-modern');
             const vc = vcs[idx];
             if (!vc) return null;
             // header lives inside the container, or in a sibling header element
             let btn = vc.querySelector('button.vcMenuBtn, [data-testid="visual-more-options-btn"], button[aria-label*="More options" i]');
             if (!btn) {
                 const grp = vc.closest('visual-container-group, .visualContainerGroup') || vc.parentElement;
                 btn = grp && grp.querySelector('button.vcMenuBtn, [data-testid="visual-more-options-btn"], button[aria-label*="More options" i]');
             }
             if (!btn) return null;
             const r = btn.getBoundingClientRect();
             return {x: r.left, y: r.top, w: r.width, h: r.height, visible: r.width > 0 && r.height > 0};
           }""",
        idx,
    )


def open_page(page: Page, url: str, render_wait_ms: int) -> None:
    print(f"Opening {url}", flush=True)
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(2_000)
    # Poll for the visuals; if the tab is on a sign-in page (Microsoft, HHS PIV,
    # or any other host) say so instead of timing out.
    deadline = time.monotonic() + 90
    while True:
        if page.locator(VISUAL_SEL).count():
            break
        cur = page.url
        host = urlparse(cur).hostname or ""
        if "login.microsoftonline" in cur or not host.endswith("powerbigov.us"):
            raise SystemExit(f"Power BI asked for sign-in (tab is on {host}). "
                             "Sign in in the Edge window, then rerun.")
        if time.monotonic() > deadline:
            shot = Path("output") / "debug_page.png"
            shot.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(shot))
            title = page.title()
            body = page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 300)")
            raise SystemExit("The report page loaded but no visuals appeared in 90s.\n"
                             f"  url:   {cur}\n  title: {title}\n  text:  {body!r}\n"
                             f"  screenshot: {shot.resolve()}")
        page.wait_for_timeout(1_000)
    page.wait_for_timeout(render_wait_ms)


def click_page_tab(page: Page, page_name: str, render_wait_ms: int) -> None:
    """Click a tab in the Pages pane (expanding the pane if it is collapsed)."""
    print(f"Clicking page tab '{page_name}'", flush=True)
    tab = page.get_by_text(page_name, exact=True).filter(visible=True).first
    try:
        tab.wait_for(state="visible", timeout=5_000)
    except Exception:  # noqa: BLE001
        # pane may be collapsed: try the expander, then look again
        for sel in ("button[aria-label*='Expand pages' i]", "button[title*='Pages' i]",
                    "button[aria-label*='pages' i]"):
            btn = page.locator(sel).first
            if btn.count() and btn.is_visible():
                btn.click()
                page.wait_for_timeout(800)
                break
        tab = page.get_by_text(page_name, exact=True).filter(visible=True).first
        try:
            tab.wait_for(state="visible", timeout=10_000)
        except Exception:  # noqa: BLE001
            names = page.evaluate(
                """() => Array.from(document.querySelectorAll('[role="tab"], [role="option"], .pane-item, '
                       + 'pages-navigation-pane *, .pagesPane *'))
                         .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 60)"""
            )
            raise SystemExit(f"Could not find a page tab named {page_name!r}. Tabs seen: {sorted(set(names))}")
    tab.click()
    page.wait_for_timeout(1_500)
    page.wait_for_selector(VISUAL_SEL, state="attached", timeout=60_000)
    page.wait_for_timeout(render_wait_ms)


def click_button(page: Page, text: str, render_wait_ms: int) -> None:
    """Click a button / bookmark on the report page by its visible text."""
    print(f"Clicking button '{text}'", flush=True)
    target = page.get_by_text(text, exact=True).filter(visible=True).first
    try:
        target.wait_for(state="visible", timeout=10_000)
    except Exception:  # noqa: BLE001
        raise SystemExit(f"Could not find a button with text {text!r} on this page.")
    bb = target.bounding_box()
    if bb:  # click the centre so the whole button, not just its label, gets the click
        page.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
    else:
        target.click()
    page.wait_for_timeout(1_500)
    page.wait_for_timeout(render_wait_ms)


def export_visual(page: Page, job: ExportJob, out_path: Path, download_timeout_ms: int) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    box = find_visual(page, job.visual_text)
    print(f"  visual #{box['idx']} at x={box['x']:.0f} y={box['y']:.0f} w={box['w']:.0f} h={box['h']:.0f}  '{box['text'][:50]}'",
          flush=True)
    _hover_visual(page, box)

    def _export_item():
        loc = page.locator("[role='menuitem'], [role='menu'] button, [role='menu'] li, .pbi-menu-item, "
                           "mat-menu-item, .menuItem, [class*='menu'] [class*='item']") \
                  .filter(has_text=re.compile(r"export\s*data", re.I)).filter(visible=True)
        if loc.count():
            return loc.first
        loc = page.get_by_text(re.compile(r"^\s*export data\s*$", re.I)).filter(visible=True)
        return loc.first if loc.count() else None

    JS_FIND_BTN = """(idx) => {
        const vc = document.querySelectorAll('visual-container, visual-container-modern')[idx];
        if (!vc) return null;
        const q = 'button.vcMenuBtn, [data-testid="visual-more-options-btn"], button[aria-label*="More options" i]';
        let btn = vc.querySelector(q);
        if (!btn) { const g = vc.closest('visual-container-group, .visualContainerGroup') || vc.parentElement;
                    btn = g && g.querySelector(q); }
        return btn || null;
    }"""

    def _press_menu_button(method: str) -> bool:
        """Try to open the visual's '...' menu; return True if 'Export data' shows up."""
        if method == "dom-click":
            page.evaluate("(idx) => { const f = " + JS_FIND_BTN + "; const b = f(idx); if (b) b.click(); return !!b; }",
                          box["idx"])
        elif method == "dom-events":
            page.evaluate(
                "(idx) => { const f = " + JS_FIND_BTN + "; const b = f(idx); if (!b) return false;"
                "  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
                "    b.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window}));"
                "  return true; }",
                box["idx"])
        elif method == "mouse":
            rect = _menu_button_rect(page, box["idx"])
            if not rect or not rect["visible"]:
                return False
            page.mouse.click(rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2)
        page.wait_for_timeout(900)
        return _export_item() is not None

    # The header (and its "..." button) is only created once the visual is hovered,
    # and it is torn down after bookmarks/exports, so hover first and give it a moment.
    has_btn = False
    for attempt in range(5):
        _hover_visual(page, box)
        has_btn = page.evaluate("(idx) => { const f = " + JS_FIND_BTN + "; return !!f(idx); }", box["idx"])
        if has_btn:
            break
        page.mouse.move(5, 5)            # leave and come back to retrigger the hover state
        page.wait_for_timeout(600)
    if not has_btn:
        raise SystemExit("This visual has no 'More options' (...) button even after hovering. "
                         "Its header may be disabled in the report design.")

    opened = False
    for method in ("dom-click", "mouse", "dom-events"):
        _hover_visual(page, box)
        if _press_menu_button(method):
            print(f"  menu opened via {method}", flush=True)
            opened = True
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

    if not opened:
        shot = out_path.parent / "debug_menu.png"
        page.screenshot(path=str(shot))
        seen = page.evaluate(
            """() => Array.from(document.querySelectorAll('[role="menu"], [role="menuitem"], .pbi-menu, mat-menu-panel'))
                     .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim()).filter(Boolean).slice(0, 20)"""
        )
        raise SystemExit("Could not open the visual's menu or find 'Export data' in it.\n"
                         f"Menu text seen: {seen}\nScreenshot saved to {shot}")

    _export_item().click()

    dialog = page.get_by_role("dialog").first
    dialog.wait_for(state="visible", timeout=15_000)

    # The three radio options Power BI offers, keyed by the config value.
    OPTIONS = {
        "layout": ("Data with current layout", re.compile(r"^\s*Data with current layout", re.I)),
        "summarized": ("Summarized data", re.compile(r"^\s*Summarized data", re.I)),
        "underlying": ("Underlying data", re.compile(r"^\s*Underlying data", re.I)),
    }
    d = job.data.replace("_", " ").replace("-", " ")
    if d.startswith("under"):
        want = "underlying"
    elif "layout" in d or d.startswith("current"):
        want = "layout"
    else:
        want = "summarized"
    # Fallback order if the preferred option is greyed out for this visual.
    order = [want] + [k for k in ("layout", "summarized", "underlying") if k != want]

    # The dialog is a <pbi-radio-group>: each card is a <pbi-radio-button> wrapping a hidden
    # <input type="radio" aria-label="Data with current layout"> and a <label for=...>.
    # The selected card's wrapper carries the class "exportTypeRadioButton-selected".
    def _input(key):
        return dialog.locator(f"input[type='radio'][aria-label='{OPTIONS[key][0]}']").first

    def _host(key):
        return dialog.locator(f"pbi-radio-button:has(input[type='radio'][aria-label='{OPTIONS[key][0]}'])").first

    def _offered(key) -> bool:
        return _input(key).count() > 0

    def _checked(key) -> bool:
        try:
            if _input(key).is_checked():
                return True
            return "-selected" in (_host(key).get_attribute("class") or "")
        except Exception:  # noqa: BLE001
            return False

    def _disabled(key) -> bool:
        try:
            return _input(key).is_disabled() or "-disabled" in (_host(key).get_attribute("class") or "")
        except Exception:  # noqa: BLE001
            return False

    def _select(key) -> bool:
        inp, host = _input(key), _host(key)
        inp_id = inp.get_attribute("id")
        attempts = [
            ("label", lambda: dialog.locator(f"label[for='{inp_id}']").first.click(timeout=3_000)),
            ("card", lambda: host.click(timeout=3_000)),
            ("input", lambda: inp.check(force=True, timeout=3_000)),
            ("element", lambda: inp.evaluate("e => { e.click(); e.dispatchEvent(new Event('change', {bubbles: true})); }")),
        ]
        for how, do in attempts:
            try:
                do()
            except Exception:  # noqa: BLE001
                continue
            page.wait_for_timeout(500)
            if _checked(key):
                print(f"  selected '{OPTIONS[key][0]}' (via {how})", flush=True)
                return True
        return False

    page.wait_for_timeout(500)
    chosen = None
    if not any(_offered(k) for k in OPTIONS):
        # Older dialog variant without the pbi-radio-group: click the option text and carry on.
        print("  (export dialog without radio inputs; clicking option text)", flush=True)
        for key in order:
            t = dialog.get_by_text(OPTIONS[key][1]).first
            if t.count():
                t.click()
                chosen = key
                break
        if chosen is None:
            raise SystemExit("Could not find any data option in the Export dialog.")
    else:
        for key in order:
            if not _offered(key):
                print(f"  '{OPTIONS[key][0]}' is not offered for this visual", flush=True)
                continue
            if _disabled(key):
                print(f"  '{OPTIONS[key][0]}' is greyed out for this visual", flush=True)
                continue
            if _checked(key):
                print(f"  '{OPTIONS[key][0]}' already selected", flush=True)
                chosen = key
                break
            if _select(key):
                chosen = key
                break
            print(f"  could not select '{OPTIONS[key][0]}'", flush=True)
        if chosen is None:
            html_path = out_path.parent / "debug_export_dialog.html"
            try:
                html_path.write_text(dialog.evaluate("d => d.outerHTML"), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            raise SystemExit(f"Could not select a data option in the Export dialog. Dialog HTML: {html_path}")
    if chosen != want:
        print(f"  using '{OPTIONS[chosen][0]}' instead of '{OPTIONS[want][0]}'", flush=True)
    page.wait_for_timeout(400)

    # File format: a <pbi-dropdown> button showing e.g. ".xlsx (Excel 150,000-row max)".
    # Only touched when it shows a different format than requested.
    fmt_label = ".csv" if job.format == "csv" else ".xlsx"
    combo = dialog.locator("[data-testid='pbi-dropdown'], [role='combobox'], select, "
                           "button:has-text('.xlsx'), button:has-text('.csv')").first
    try:
        combo.wait_for(state="visible", timeout=3_000)
        current = combo.inner_text() or ""
        if fmt_label not in current:
            combo.click()
            page.locator("[role='option'], [role='listbox'] li, .pbi-dropdown-item") \
                .filter(has_text=re.compile(re.escape(fmt_label), re.I)).first.click(timeout=5_000)
            print(f"  file format set to {fmt_label}", flush=True)
    except Exception:  # noqa: BLE001
        print("  (file format left at the dialog default)", flush=True)

    with page.expect_download(timeout=download_timeout_ms) as dl:
        btn = dialog.locator("[data-testid='export-btn']").first
        if not btn.count():
            btn = dialog.get_by_role("button", name=re.compile(r"^Export$", re.I)).first
        btn.click()
    download = dl.value
    if out_path.suffix == "":
        out_path = out_path.with_suffix(Path(download.suggested_filename or f"x.{job.format}").suffix)
    download.save_as(str(out_path))
    page.keyboard.press("Escape")        # close any lingering dialog/toast
    page.mouse.move(5, 5)
    page.wait_for_timeout(1_000)
    if job.layout == "classic" and out_path.suffix.lower() == ".xlsx":
        to_classic_layout(out_path, sheet_name=job.sheet_name)
    print(f"Saved {out_path}", flush=True)
    return out_path


def run(s: Settings, only: str | None = None, refresh: bool | None = None, refresh_only: bool = False) -> list[Path]:
    jobs = [j for j in s.exports if not only or j.name == only]
    if not jobs and not refresh_only:
        raise SystemExit("Nothing to export" + (f" named {only!r}" if only else " (add entries under exports: in config.yaml)"))
    do_refresh = s.refresh_enabled if refresh is None else refresh
    today = dt.date.today()
    saved: list[Path] = []
    with attached_page(s.cdp_url, viewport=s.viewport) as page:
        if do_refresh or refresh_only:
            from .refresh import refresh_semantic_model
            refresh_semantic_model(page, s.report_url, s.render_wait_ms, s.refresh_timeout_min,
                                   wait=s.refresh_wait, fail_on_timeout=s.refresh_fail_on_timeout,
                                   debug_dir=s.output_dir)
            if refresh_only:
                return saved
        current_url, current_tab = None, None
        for job in jobs:
            url = job.page_url or s.report_url
            if url != current_url:
                open_page(page, url, s.render_wait_ms)
                current_url, current_tab = url, None
            if job.page_name and job.page_name != current_tab:
                click_page_tab(page, job.page_name, s.render_wait_ms)
                current_tab = job.page_name
            if job.click_button:
                click_button(page, job.click_button, s.render_wait_ms)
            fname = (job.filename or f"{job.name}_{{date}}.{job.format}").replace("{date}", f"{today:%Y%m%d}")
            print(f"Exporting '{job.name}' ({job.data}, {job.format})...", flush=True)
            saved.append(export_visual(page, job, s.output_dir / fname, s.download_timeout_ms))
    return saved