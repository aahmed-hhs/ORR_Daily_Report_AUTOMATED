from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from .export import run


def main() -> None:
    ap = argparse.ArgumentParser(prog="powerbi-export",
                                 description="Download the data behind Power BI visuals as .xlsx/.csv.")
    ap.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    ap.add_argument("--only", default=None, help="Run just the export with this name")
    ap.add_argument("--list", action="store_true", help="List configured exports and exit")
    ap.add_argument("--show", action="store_true", help="(kept for parity with powerbi-report; the attached Edge is always visible)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--refresh", action="store_true", help="refresh the semantic model first (overrides config)")
    g.add_argument("--no-refresh", action="store_true", help="skip the semantic model refresh (overrides config)")
    ap.add_argument("--refresh-only", action="store_true", help="just refresh the semantic model and exit")
    args = ap.parse_args()
    s = config.load(args.config)
    if args.list:
        for j in s.exports:
            print(f"{j.name:20s} {j.data:11s} {j.format:5s} visual='{j.visual_text}'")
        return
    refresh = True if args.refresh else (False if args.no_refresh else None)
    files = run(s, only=args.only, refresh=refresh, refresh_only=args.refresh_only)
    if args.refresh_only:
        print("\nDone: semantic model refresh")
    else:
        print(f"\nDone: {len(files)} file(s) in {s.output_dir}")


if __name__ == "__main__":
    main()
