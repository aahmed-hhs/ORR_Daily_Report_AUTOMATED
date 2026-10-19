from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

from . import capture as cap
from . import config
from .dates import report_date_for
from .document import fill_template


def _bypass_proxy_for_localhost() -> None:
    """Corporate proxies swallow 127.0.0.1; make sure local traffic skips them."""
    for var in ("NO_PROXY", "no_proxy"):
        cur = os.environ.get(var, "")
        parts = [x.strip() for x in cur.split(",") if x.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in parts:
                parts.append(host)
        os.environ[var] = ",".join(parts)


def main() -> None:
    _bypass_proxy_for_localhost()
    ap = argparse.ArgumentParser(prog="powerbi-report",
                                 description="Capture Power BI report pages; insert them into Word templates.")
    ap.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    ap.add_argument("--login", action="store_true", help="Sign in interactively and save the session")
    ap.add_argument("--show", action="store_true", help="Run the capture with a visible browser")
    ap.add_argument("--skip-capture", action="store_true", help="Reuse existing images (see --image)")
    ap.add_argument("--image", type=Path, default=None,
                    help="Image to insert when using --skip-capture (applies to the first page)")
    ap.add_argument("--page", action="append", default=None, metavar="NAME",
                    help="Only process the page(s) with this name or file key; repeatable")
    ap.add_argument("--list-pages", action="store_true", help="Print the configured pages and exit")
    args = ap.parse_args()

    s = config.load(args.config)
    if args.login:
        cap.login(s)
        return

    pages = s.pages
    if args.list_pages:
        for pg in pages:
            kind = f"template {pg.template.name}" if pg.template else "screenshot only"
            print(f"- {pg.name or '(default)'}  [{pg.file}]  {kind}")
        return
    if args.page:
        wanted = {w.lower() for w in args.page}
        pages = [pg for pg in pages if pg.name.lower() in wanted or pg.file.lower() in wanted]
        if not pages:
            raise SystemExit(f"No configured page matches {args.page}. Use --list-pages to see them.")

    today = dt.date.today()
    report_date = report_date_for(s.report_date, today)

    targets: list[tuple[config.PageSpec, Path]] = []
    for i, pg in enumerate(pages):
        png = args.image if (args.image and i == 0) else s.output_dir / f"{pg.file}_{today:%Y%m%d}.png"
        targets.append((pg, png))

    if not args.skip_capture:
        cap.capture_pages(s, targets, headless=not args.show)
    else:
        missing = [str(png) for _, png in targets if not png.exists()]
        if missing:
            raise SystemExit("--skip-capture given but image(s) not found:\n  " + "\n  ".join(missing))

    for pg, png in targets:
        if not pg.template:
            print(f"{pg.name or pg.file}: screenshot only -> {png}")
            continue
        if pg.output_name:
            # {date} = run date, {report_date} = date printed in the document,
            # both formatted with output_date_format (default YYYYMMDD).
            fmt = s.output_date_format
            name = pg.output_name.format(date=today.strftime(fmt), report_date=report_date.strftime(fmt))
            if not name.lower().endswith(".docx"):
                name += ".docx"
            out_docx = s.output_dir / name
        else:
            out_docx = s.output_dir / f"{pg.template.stem}_{today:%Y%m%d}.docx"
        fill_template(
            pg.template,
            png,
            out_docx,
            image_placeholder=s.image_placeholder,
            date_placeholder=s.date_placeholder,
            date_format=s.date_format,
            image_width_inches=s.image_width_inches,
            run_date=report_date,
        )


if __name__ == "__main__":
    main()
