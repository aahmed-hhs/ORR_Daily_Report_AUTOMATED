# powerbi-export

Download the data behind Power BI visuals as .xlsx/.csv from Python, by
driving Power BI's own "Export data" menu in an Edge window you control.

Companion to `powerbi-report` (screenshot -> Word). Both attach to the same
Edge started with remote debugging, so you can run them back to back.

## Layout

```
powerbi_export/
├── pyproject.toml
├── config.yaml             # cdp_url, output folder, list of exports
├── README.md
├── src/powerbi_export/
│   ├── browser.py          # attach to Edge over CDP (proxy bypass included)
│   ├── config.py           # loads config.yaml
│   ├── export.py           # hover visual -> ... -> Export data -> save download
│   └── cli.py              # `powerbi-export` command
├── scripts/run_export.bat  # for Task Scheduler
├── output/                 # downloaded files (git-ignored)
└── tests/test_config.py
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

No `playwright install` needed; it attaches to the Edge already on the PC.

## Usage

1. Start Edge with remote debugging (same as for powerbi-report), e.g. Win+R:
   `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\Ahmed.Ahmed\local_files\edge-debug"`
   Make sure Power BI loads in that window.
2. Run:

```bash
powerbi-export --show            # watch it work
powerbi-export                   # quiet
powerbi-export --only daily_metrics
powerbi-export --list            # show what's configured
```

Files land in `output/` named per `filename` in `config.yaml`.

## Prerequisite on the Power BI side

Hover the visual in Power BI, click its "..." menu and confirm **Export data**
is present. If it is missing or disabled, your Power BI admin has turned off
export and this tool cannot work around that.

## Notes

- Power BI's menu labels change occasionally; if a run fails on a selector,
  run with `--show` to see where it stops and adjust `export.py`.
- Underlying-data exports can be large; raise `download_timeout_ms` if needed.
