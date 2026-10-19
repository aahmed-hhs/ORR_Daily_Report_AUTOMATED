from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


@dataclass(frozen=True)
class ExportJob:
    name: str
    visual_text: str
    page_name: str | None = None     # tab in the Pages pane to click
    page_url: str | None = None      # or go straight to a page URL
    click_button: str | None = None  # text of a button/bookmark on the page to press first
    layout: str = "classic"          # classic = headers in row 1, filters note at bottom | raw = as downloaded
    sheet_name: str = "Export"
    data: str = "summarized"
    format: str = "xlsx"
    filename: str | None = None


@dataclass(frozen=True)
class Settings:
    cdp_url: str
    report_url: str
    output_dir: Path
    viewport: dict
    render_wait_ms: int
    download_timeout_ms: int
    exports: list[ExportJob]


def load(path: Path | None = None) -> Settings:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    base = cfg_path.parent
    today = dt.date.today().strftime(raw.get("folder_date_format", "%Y-%m-%d"))
    out = Path(str(raw.get("output_dir", "output")).replace("{date}", today))
    out = out if out.is_absolute() else (base / out).resolve()

    jobs: list[ExportJob] = []
    for i, e in enumerate(raw.get("exports") or []):
        if not e.get("visual_text"):
            raise SystemExit(f"exports[{i}] is missing visual_text")
        if not (e.get("page_name") or e.get("page_url") or raw.get("report_url")):
            raise SystemExit(f"exports[{i}] needs page_name or page_url (or set report_url at the top)")
        jobs.append(ExportJob(
            name=str(e.get("name", f"export{i + 1}")),
            visual_text=e["visual_text"],
            page_name=e.get("page_name"),
            page_url=e.get("page_url"),
            click_button=e.get("click_button"),
            layout=str(e.get("layout", raw.get("layout", "classic"))).lower(),
            sheet_name=str(e.get("sheet_name", raw.get("sheet_name", "Export"))),
            data=str(e.get("data", "summarized")).lower(),
            format=str(e.get("format", "xlsx")).lower().lstrip("."),
            filename=e.get("filename"),
        ))
    return Settings(
        cdp_url=raw.get("cdp_url", "http://127.0.0.1:9222"),
        report_url=raw.get("report_url", ""),
        output_dir=out,
        viewport=raw.get("viewport") or {"width": 1920, "height": 1080},
        render_wait_ms=int(raw.get("render_wait_ms", 8000)),
        download_timeout_ms=int(raw.get("download_timeout_ms", 180000)),
        exports=jobs,
    )