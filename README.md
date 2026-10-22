# ORR Daily Pipeline

One click that produces the IAB Division of Vetting daily deliverables:

1. starts a dedicated Edge window with remote debugging (the only way Power BI GCC lets a script in),
2. **powerbi-export** refreshes the report's semantic model (report "…" menu → View semantic model →
   Refresh now) and waits for it to finish, then downloads the HSI and UACB deliverable tables (MASTER / TODAY / NOT SENT / CLOSED) as Excel,
3. **powerbi-report** screenshots the *Daily Metrics* and *SSN Verification Report* pages and fills the Word template,
4. copies everything into `ach-orr-daily-reports\Data Sources\MM-DD-YYYY\`,
5. runs the bundled `run_daily_reports.py` (from the ORR IAB **ach-orr-daily-reports** project) to build
   `HSI Daily <date>.xlsx` and `UACB Daily <date>.xlsx`.

The Word document and the two Daily workbooks are what you upload to SharePoint.

---

## Before you start

* Access to the Power BI workspace (you can open the report in a browser).
* **Python 3.10+** – install from [python.org](https://www.python.org/downloads/windows/), choose
  *Install for me only* (no admin needed) and tick *Add python.exe to PATH*.
* **Git for Windows** (per-user install is fine) – to clone this repo and pull updates.
* Microsoft Edge (already on every HHS laptop).

## Install (once)

1. Clone this repo somewhere under your user folder. `C:\Users\<you>\local_files\projects\` is a good
   spot because OneDrive does not sync it:

   ```
   git clone https://github.com/aahmed-hhs/ORR_Daily_Report_AUTOMATED.git "%USERPROFILE%\local_files\projects\orr-daily-pipeline"
   ```

2. Double-click **`setup.bat`**. It creates a private Python environment, installs the tools, and puts an
   **ORR Daily Pipeline** shortcut (the duck) on your Desktop.

   The `ach-orr-daily-reports` scripts that build the Daily workbooks are bundled in this repo. If you
   already keep a separate copy with your `Data Sources` history, create a `pipeline.local.yaml` next to
   `pipeline.yaml` containing `ach_repo: <path to that folder>` (this file stays out of git).

3. Open the duck, click **Start Edge only**, and sign in to Power BI in the Edge window that appears.
   This Edge uses its own profile folder (`%USERPROFILE%\local_files\edge-debug`) and remembers you,
   so this is a one-time step until the sign-in expires.

## Every day

Open the duck and click **Run today's pipeline**. Leave the three checkboxes as they are:

| Checkbox | What it does |
|---|---|
| Start the debug Edge first | Closes any open Edge windows and starts the debug profile on the report. Untick if it's already running. |
| Refresh the semantic model before exporting | Triggers a dataset refresh and waits (up to 1 min, see `powerbi_export\config.yaml` → `refresh:`) so the exports contain today's data. Untick to export whatever is already there. |
| Skip Power BI export | Reuse today's HSI/UACB downloads (handy when re-running after a small fix). |
| Skip report capture | Reuse today's PNGs and Word doc. |

Progress streams into the window; the bar at the bottom turns green when done and the
`Data Sources\<today>` folder opens. **Open today's folder** and **Open latest log** are there for
afterwards. Re-running on the same day is safe – files are overwritten and the previous Daily workbook
is removed before the new one is built.

Prefer the terminal? `run_pipeline.bat --start-edge` does the same thing (add `--no-refresh`, `--skip-export`,
`--skip-report` as needed). From Git Bash use `./run_pipeline.bat ...`.

### Run it on a schedule

In Git Bash (adjust the time, 24-hour clock):

```
MSYS_NO_PATHCONV=1 schtasks /Create /TN "ORR Daily Pipeline" /TR '"%USERPROFILE%\local_files\projects\orr-daily-pipeline\run_pipeline.bat" --start-edge' /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:00 /F
```

The laptop must be on and you signed in (locked is fine). The task force-closes Edge before it starts,
so pick a time you are not working in Edge.

## When something goes wrong

| Message | What to do |
|---|---|
| *The debug Edge is not running* | Tick **Start the debug Edge first**, or click **Start Edge only**. |
| *Power BI asked for sign-in (tab is on …)* | Your session expired. Sign in in the Edge window, then press Run again with the Edge checkbox unticked. |
| *The report page loaded but no visuals appeared* | Look at `powerbi_export\output\debug_page.png` – usually a Power BI banner or dialog is in the way. Close it in the Edge window and re-run. |
| *Refresh: could not find …* | Power BI changed its menus. Run the refresh alone to see it happen: `powerbi_export> ..\.venv\Scripts\powerbi-export.exe --refresh-only`; a screenshot is saved under `powerbi_export\output\<date>\`. |
| *Refresh: not confirmed within 1 min* | The run continues anyway. Raise `timeout_minutes` in `powerbi_export\config.yaml` if refreshes are normally slow. |
| *Cannot overwrite … it is open in Word/Excel* | Close that file and re-run. |
| *Could not find a page tab / button / visual named …* | The report layout changed. Update the names in `powerbi_export\config.yaml` or `powerbi_report\config.yaml`. |
| *ach-orr-daily-reports not found* | Fix `ach_repo` in `pipeline.yaml`, or re-download this repo if the bundled folder is missing. |

Full output of every run is in `logs\pipeline_YYYYMMDD.log`.

## Updating

```
cd "%USERPROFILE%\local_files\projects\orr-daily-pipeline" && git pull && setup.bat
```

## Where things live

```
orr-daily-pipeline\
  setup.bat               one-time installer (safe to re-run)
  pipeline_app.pyw        the desktop app (duck)
  run_pipeline.bat        command-line / Task Scheduler entry point
  run_pipeline.py         the orchestration logic (standard library only)
  pipeline.yaml           ach_repo (optional), edge_profile, cdp_port
  requirements.txt        everything installed into .venv
  powerbi_export\         download tables behind Power BI visuals   (config.yaml = which visuals)
  powerbi_report\         screenshot pages into a Word template      (config.yaml, templates\)
  ach-orr-daily-reports\  bundled Daily-workbook scripts; Data Sources\ is created here (git-ignored)
  duck.ico
  logs\                   one log per day (git-ignored)
  .venv\                  created by setup.bat (git-ignored)
```

The export and report tools each keep their own `config.yaml` with the report URLs, page and button
names, crop settings and template. Those are the files to edit when the Power BI report changes.

## Data handling

The exported workbooks contain PII. They are written only to `powerbi_export\output\` and to
`ach-orr-daily-reports\Data Sources\` on the local machine – nothing is uploaded by this tool. Both
locations are git-ignored. Clear out old date folders on whatever schedule your office requires.
