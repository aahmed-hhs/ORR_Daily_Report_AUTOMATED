# powerbi-report

Capture a Power BI report page as an image and drop it into a Word template.

## Layout

```
powerbi_report/
├── pyproject.toml          # package metadata + dependencies
├── config.yaml             # report URL, template path, browser mode, placeholders
├── README.md
├── .gitignore              # excludes secrets/ and output/
├── src/powerbi_report/
│   ├── __init__.py
│   ├── config.py           # loads config.yaml
│   ├── capture.py          # browser attach/launch + screenshot
│   ├── document.py         # python-docx template filling
│   └── cli.py              # command-line entry point
├── templates/
│   └── report_template.docx   # put {{DASHBOARD}} and {{DATE}} in it
├── secrets/                # auth.json / profile (git-ignored)
├── output/                 # dated .docx and .png files (git-ignored)
├── scripts/
│   ├── start_edge_debug.bat   # start Edge so the tool can attach to it
│   └── run_report.bat         # for Windows Task Scheduler
└── tests/
    └── test_document.py
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

No `playwright install` is needed: the tool uses the Edge already on the PC.

Edit `config.yaml` if the report URL or template path changes. In the Word
template, put `{{DASHBOARD}}` in its own paragraph where the image should go
and `{{DATE}}` wherever the run date should appear.

## Usage on a managed (government) PC  <- default mode

Conditional-access policy usually blocks Power BI in any browser the script
launches itself. Instead, the tool attaches to an Edge you start:

1. Double-click `scripts\start_edge_debug.bat`. It closes Edge, then restarts
   it with remote debugging on port 9222 and a dedicated profile folder
   (`%USERPROFILE%\local_files\edge-debug`).
2. First time only: click the profile icon in that Edge and sign in with your
   work account, then open the Power BI report and confirm it loads.
3. Leave that Edge open and run:

```bash
powerbi-report --show     # watch it work
powerbi-report            # same, quieter
```

Output lands in `output/` as `dashboard_<date>.png` and
`report_template_<date>.docx`.

`cdp_url` in `config.yaml` turns this mode on. Comment it out to let Playwright
launch its own browser (then `powerbi-report --login` once to save a session).

## Other commands

```bash
powerbi-report --skip-capture --image some.png   # reuse an existing image
powerbi-report --config other.yaml               # different report/template
pytest                                           # unit test for the Word step
```

## Scheduling

`scripts/run_report.bat` activates the venv and runs the tool. Point a Windows
Task Scheduler task at it. The debug Edge must be running (and signed in) at
that time.

## Security

The profile folder and `secrets/` hold live login sessions. Treat them like a
password: keep them out of shared drives and source control.
