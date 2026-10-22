from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


@dataclass(frozen=True)
class PageSpec:
    """One report page (tab) to capture."""

    name: str
    file: str                       # PNG base name -> output_dir/file_YYYYMMDD.png
    template: Path | None           # None = screenshot only
    output_name: str | None         # e.g. "Data Summary Report {date}.docx"
    url: str | None                 # open this instead of clicking the tab
    crop: dict | None
    crop_padding: int
    crop_exclude_text: list
    crop_trim: dict


@dataclass(frozen=True)
class Settings:
    report_url: str
    template: Path
    output_dir: Path
    auth_file: Path
    viewport: dict
    image_width_inches: float
    render_wait_ms: int
    date_format: str
    report_date: str
    image_placeholder: str
    date_placeholder: str
    browser_channel: str | None
    profile_dir: Path | None
    cdp_url: str | None
    crop: dict | None
    crop_padding: int
    crop_exclude_text: list
    crop_trim: dict
    output_date_format: str = "%Y%m%d"
    page_view: str | None = "Fit to page"
    pages: list = field(default_factory=list)


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_") or "page"


def load(path: Path | None = None) -> Settings:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    base = cfg_path.parent

    def to_path(v) -> Path:
        v = Path(v)
        return v if v.is_absolute() else (base / v).resolve()

    def p(key: str) -> Path:
        return to_path(raw[key])

    ph = raw.get("placeholders", {})
    crop = raw.get("crop") or None
    crop_padding = int(raw.get("crop_padding", 12))
    crop_exclude_text = list(raw.get("crop_exclude_text") or [])
    crop_trim = {k: int(v) for k, v in (raw.get("crop_trim") or {}).items()}
    template = p("template")

    pages: list[PageSpec] = []
    for i, item in enumerate(raw.get("pages") or []):
        if isinstance(item, str):
            item = {"name": item}
        name = item.get("name")
        if not name:
            raise SystemExit(f"pages[{i}] in {cfg_path} needs a name")
        # A page with no "template" key at all keeps the global template so a
        # bare `- name: X` entry still produces a document; `template: null`
        # (or "") explicitly means screenshot only.
        if "template" in item:
            tpl = to_path(item["template"]) if item["template"] else None
        else:
            tpl = template
        pages.append(PageSpec(
            name=str(name),
            file=str(item.get("file") or _slug(str(name))),
            template=tpl,
            output_name=item.get("output_name") or raw.get("output_name") or None,
            url=item.get("url") or None,
            crop=item.get("crop") or (None if "crop" in item else crop),
            crop_padding=int(item.get("crop_padding", crop_padding)),
            crop_exclude_text=list(item["crop_exclude_text"] if "crop_exclude_text" in item
                                   else crop_exclude_text),
            crop_trim={k: int(v) for k, v in item["crop_trim"].items()} if item.get("crop_trim")
            else (crop_trim if "crop_trim" not in item else {}),
        ))
    if not pages:  # legacy single-page config
        pages.append(PageSpec(
            name="", file="dashboard", template=template, url=raw["report_url"],
            output_name=raw.get("output_name") or None,
            crop=crop, crop_padding=crop_padding, crop_exclude_text=crop_exclude_text,
            crop_trim=crop_trim,
        ))

    return Settings(
        report_url=raw["report_url"],
        template=template,
        output_dir=p("output_dir"),
        auth_file=p("auth_file"),
        viewport=raw.get("viewport", {"width": 1920, "height": 1080}),
        image_width_inches=float(raw.get("image_width_inches", 6.5)),
        render_wait_ms=int(raw.get("render_wait_ms", 10000)),
        date_format=raw.get("date_format", "%B %d, %Y"),
        report_date=str(raw.get("report_date", "today")).lower(),
        image_placeholder=ph.get("image", "{{DASHBOARD}}"),
        date_placeholder=ph.get("date", "{{DATE}}"),
        browser_channel=raw.get("browser_channel") or None,
        profile_dir=p("profile_dir") if raw.get("profile_dir") else None,
        cdp_url=raw.get("cdp_url") or None,
        crop=crop,
        crop_padding=crop_padding,
        crop_exclude_text=crop_exclude_text,
        crop_trim=crop_trim,
        output_date_format=str(raw.get("output_date_format") or "%Y%m%d"),
        page_view=(raw.get("page_view") if "page_view" in raw else "Fit to page") or None,
        pages=pages,
    )
