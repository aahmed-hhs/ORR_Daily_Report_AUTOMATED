"""ORR Daily Pipeline - one command that runs the whole morning routine.

    1. Make sure the debug Edge (remote-debugging port) is running.
    2. powerbi-export   -> refresh the semantic model, then HSI / UACB workbooks (powerbi_export\\)
    3. powerbi-report   -> dashboard PNGs + FO Deliverable docx  (powerbi_report\\)
    4. Copy those outputs into  ach-orr-daily-reports\\Data Sources\\MM-DD-YYYY\\{HSI,UACB}\\
    5. run_daily_reports.py from the bundled ach-orr-daily-reports folder
                        -> HSI Daily <date>.xlsx / UACB Daily <date>.xlsx

Run it with run_pipeline.bat, the desktop app (pipeline_app.pyw), or:
    .venv\\Scripts\\python.exe run_pipeline.py [--start-edge] [--skip-export] [--skip-report] [--no-open]

Settings live in pipeline.yaml next to this file. This script needs only the
standard library so the desktop app can import it with any Python.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------- settings
HERE = Path(__file__).resolve().parent
SETTINGS_FILE = HERE / "pipeline.yaml"
LOCAL_SETTINGS_FILE = HERE / "pipeline.local.yaml"   # per-machine overrides, git-ignored

DEFAULTS = {
    "ach_repo": str(HERE / "ach-orr-daily-reports"),   # bundled copy; override in pipeline.yaml
    "edge_profile": "~/local_files/edge-debug",
    "cdp_port": "9222",
}


def _read_settings() -> dict[str, str]:
    """Tiny 'key: value' reader so this file has no third-party imports."""
    out = dict(DEFAULTS)
    for f in (SETTINGS_FILE, LOCAL_SETTINGS_FILE):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip().strip('"').strip("'")
                if v:
                    out[k.strip()] = v
    # environment overrides, handy for testing: ORR_ACH_REPO=... etc.
    for k in DEFAULTS:
        if os.environ.get(f"ORR_{k.upper()}"):
            out[k] = os.environ[f"ORR_{k.upper()}"]
    return out


def _path(v: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(v))).resolve()


SETTINGS = _read_settings()
ACH_REPO = _path(SETTINGS["ach_repo"])
EDGE_PROFILE = _path(SETTINGS["edge_profile"])
CDP_HOST, CDP_PORT = "127.0.0.1", int(SETTINGS["cdp_port"])

VENV_BIN = HERE / ".venv" / ("Scripts" if os.name == "nt" else "bin")
EXE = ".exe" if os.name == "nt" else ""
PYTHON = VENV_BIN / f"python{EXE}"
EXPORT_PROJECT = HERE / "powerbi_export"
REPORT_PROJECT = HERE / "powerbi_report"
EXPORT_EXE = VENV_BIN / f"powerbi-export{EXE}"
REPORT_EXE = VENV_BIN / f"powerbi-report{EXE}"
EXPORT_OUTPUT = EXPORT_PROJECT / "output"           # + \YYYY-MM-DD\HSI, \UACB
REPORT_OUTPUT = REPORT_PROJECT / "output"           # dashboard_YYYYMMDD.png, ssn_verification_YYYYMMDD.png, *.docx

DATA_SOURCES = ACH_REPO / "Data Sources"
DAILY_SCRIPT = ACH_REPO / "run_daily_reports.py"
LOG_DIR = HERE / "logs"

DEPARTMENTS = ("HSI", "UACB")
EXPORT_KINDS = ("MASTER", "TODAY", "NOT SENT", "CLOSED")

# Names given to the powerbi_report outputs inside the date folder. {d} = report date MM-DD-YYYY.
DOCX_NAME = "IAB_Division of Vetting_Case Report_{d}.docx"
DASHBOARD_PNG_NAME = "FO Deliverable_{d}.png"       # run_daily_reports.py looks for "FO Deliverable*.png"
SSN_PNG_NAME = "SSN Verification Report_{d}.png"


def day_folder_for(today: dt.date | None = None) -> Path:
    today = today or dt.date.today()
    return DATA_SOURCES / f"{today:%m-%d-%Y}"


# --------------------------------------------------------------------------- helpers
class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = path.open("a", encoding="utf-8")

    def __call__(self, msg: str = "") -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}" if msg else ""
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def next_weekday(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def bypass_proxy_for_localhost() -> None:
    for var in ("NO_PROXY", "no_proxy"):
        parts = [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in parts:
                parts.append(host)
        os.environ[var] = ",".join(parts)


def edge_debug_running() -> bool:
    try:
        with socket.create_connection((CDP_HOST, CDP_PORT), timeout=2):
            return True
    except OSError:
        return False


def find_edge() -> Path | None:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return Path(p)
    return None


def start_url() -> str:
    """Page the debug Edge opens on: report_url from powerbi_report\\config.yaml, else Power BI home."""
    cfg = REPORT_PROJECT / "config.yaml"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("report_url:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return "https://app.powerbigov.us/"


def reset_edge_zoom(log: Log) -> None:
    """Edge remembers zoom per site in the profile. Clear it so every run captures at 100%.
    Only safe while Edge is closed (Edge rewrites the file on exit)."""
    import json
    prefs = EDGE_PROFILE / "Default" / "Preferences"
    if not prefs.exists():
        return
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
        part = data.get("partition") or {}
        had = bool(part.get("per_host_zoom_levels")) or "default_zoom_level" in part
        part.pop("per_host_zoom_levels", None)
        part.pop("default_zoom_level", None)
        if had:
            data["partition"] = part
            prefs.write_text(json.dumps(data), encoding="utf-8")
            log("Reset the debug Edge's saved zoom to 100%.")
    except Exception as e:  # noqa: BLE001
        log(f"(could not reset Edge zoom: {e})")


def start_edge(log: Log) -> bool:
    """Start Edge with remote debugging on a dedicated profile (closes any running Edge first)."""
    edge = find_edge()
    if not edge:
        log("msedge.exe not found; start Edge manually.")
        return False
    EDGE_PROFILE.mkdir(parents=True, exist_ok=True)
    log("Closing any running Edge and starting the debug profile...")
    subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
    time.sleep(3)
    reset_edge_zoom(log)
    subprocess.Popen([str(edge), f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={EDGE_PROFILE}",
                      start_url()],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(30):
        time.sleep(1)
        if edge_debug_running():
            log("Edge debug port is up.")
            time.sleep(12)  # cold start on these laptops is slow; let the window finish loading
            return True
    return False


def run_tool(cmd: list[str], cwd: Path, log: Log) -> None:
    exe = Path(cmd[0])
    if not exe.exists():
        raise SystemExit(f"Not found: {exe}\nRun setup.bat once to create the .venv and install the tools.")
    log(f"> {' '.join(cmd)}   (in {cwd})")
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        log("    " + line.rstrip())
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"{exe.name} failed with exit code {rc}. See the log above.")


def newest(paths: list[Path]) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def staged_name(dept: str, src: Path) -> str | None:
    """'HSI MASTER.xlsx' or 'HSI Deliverable MASTER.xlsx' -> 'HSI MASTER.xlsx'."""
    stem = src.stem.upper()
    for kind in EXPORT_KINDS:
        if stem.endswith(kind):
            return f"{dept} {kind}.xlsx"
    return None


def copy(src: Path, dst: Path, log: Log) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        raise SystemExit(f"Cannot overwrite {dst.name} - it is open in Word/Excel.\n"
                         f"Close it and run the pipeline again.\n  {dst}")
    log(f"    {src.name}  ->  {dst.relative_to(DATA_SOURCES)}")
    return dst


# --------------------------------------------------------------------------- steps
def step_export(log: Log, skip: bool, refresh: bool = True) -> Path:
    log("=== Step 1/4: powerbi-export (semantic model refresh + HSI / UACB workbooks) ===")
    if not skip:
        run_tool([str(EXPORT_EXE)] + ([] if refresh else ["--no-refresh"]), EXPORT_PROJECT, log)
    else:
        log("skipped (--skip-export); reusing existing files")
    folder = EXPORT_OUTPUT / f"{dt.date.today():%Y-%m-%d}"
    if not folder.is_dir():
        raise SystemExit(f"Export folder for today not found: {folder}")
    return folder


def step_report(log: Log, skip: bool) -> None:
    log("=== Step 2/4: powerbi-report (dashboard PNGs + FO Deliverable docx) ===")
    if not skip:
        run_tool([str(REPORT_EXE)], REPORT_PROJECT, log)
    else:
        log("skipped (--skip-report); reusing existing files")


def step_stage(log: Log, export_folder: Path, day_folder: Path, report_date: dt.date) -> None:
    log(f"=== Step 3/4: copying into {day_folder} ===")
    today_tag = f"{dt.date.today():%Y%m%d}"
    d = f"{report_date:%m-%d-%Y}"

    for dept in DEPARTMENTS:
        src_dir = export_folder / dept
        files = sorted(src_dir.glob("*.xlsx")) if src_dir.is_dir() else []
        if not files:  # older export layouts wrote everything flat into the date folder
            files = sorted(p for p in export_folder.glob("*.xlsx") if p.stem.upper().startswith(dept + " "))
        if not files:
            raise SystemExit(f"No {dept} workbooks found under {export_folder}")
        dst_dir = day_folder / dept
        dst_dir.mkdir(parents=True, exist_ok=True)
        for old in dst_dir.glob("* Daily *.xlsx"):   # a re-run must not feed the old Daily back in
            old.unlink()
            log(f"    removed stale {old.name}")
        n = 0
        for f in files:
            name = staged_name(dept, f)
            if not name:
                log(f"    skipping unrecognised file {f.name}")
                continue
            copy(f, dst_dir / name, log)
            n += 1
        if n != len(EXPORT_KINDS):
            log(f"    WARNING: expected {len(EXPORT_KINDS)} {dept} workbooks, found {n}")

    docx = newest(list(REPORT_OUTPUT.glob(f"*{report_date:%Y-%m-%d}*.docx"))) or newest(list(REPORT_OUTPUT.glob("*.docx")))
    dash = newest(list(REPORT_OUTPUT.glob(f"dashboard_{today_tag}.png")))
    ssn = newest(list(REPORT_OUTPUT.glob(f"ssn_verification_{today_tag}.png")))
    if not docx:
        raise SystemExit(f"No FO Deliverable .docx found in {REPORT_OUTPUT}")
    copy(docx, day_folder / DOCX_NAME.format(d=d), log)
    if dash:
        copy(dash, day_folder / DASHBOARD_PNG_NAME.format(d=d), log)
    else:
        log(f"    WARNING: dashboard_{today_tag}.png not found in {REPORT_OUTPUT}")
    if ssn:
        copy(ssn, day_folder / SSN_PNG_NAME.format(d=d), log)
    else:
        log(f"    WARNING: ssn_verification_{today_tag}.png not found in {REPORT_OUTPUT}")


def step_daily_reports(log: Log) -> None:
    """Run ach-orr-daily-reports' run_daily_reports.py unchanged, from inside that folder."""
    log("=== Step 4/4: run_daily_reports.py (HSI / UACB Daily workbooks) ===")
    if not DAILY_SCRIPT.exists():
        raise SystemExit(f"Not found: {DAILY_SCRIPT}\n"
                         "Install the ach-orr-daily-reports project there, or point ach_repo in pipeline.yaml at it.")
    py = PYTHON if PYTHON.exists() else Path(sys.executable)
    run_tool([str(py), str(DAILY_SCRIPT)], ACH_REPO, log)


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Export from Power BI, capture the report, build the daily workbooks.")
    ap.add_argument("--skip-export", action="store_true", help="reuse today's powerbi-export output")
    ap.add_argument("--skip-report", action="store_true", help="reuse today's powerbi-report output")
    ap.add_argument("--no-refresh", action="store_true",
                    help="do not refresh the semantic model before exporting")
    ap.add_argument("--start-edge", action="store_true",
                    help="if the debug Edge is not running, start it (closes any open Edge windows)")
    ap.add_argument("--edge-only", action="store_true",
                    help="just make sure the debug Edge is running (starting it if needed), then exit")
    ap.add_argument("--no-open", action="store_true", help="do not open the finished folder in Explorer")
    args = ap.parse_args()

    bypass_proxy_for_localhost()
    today = dt.date.today()
    report_date = next_weekday(today)
    day_folder = day_folder_for(today)
    log = Log(LOG_DIR / f"pipeline_{today:%Y%m%d}.log")

    if args.edge_only:
        if edge_debug_running():
            log(f"Debug Edge is already running on port {CDP_PORT}.")
        elif not start_edge(log):
            raise SystemExit("Could not start the debug Edge.")
        return

    log()
    log(f"Run date {today:%A %m/%d/%Y}  ->  report date {report_date:%A %m/%d/%Y}")
    if not ACH_REPO.is_dir():
        raise SystemExit(f"ach-orr-daily-reports not found at {ACH_REPO}\n"
                         "Install it there, or set ach_repo in pipeline.yaml.")

    needs_browser = not (args.skip_export and args.skip_report)
    if needs_browser and not edge_debug_running():
        if not (args.start_edge and start_edge(log)):
            raise SystemExit(
                f"The debug Edge is not running on port {CDP_PORT}.\n"
                "Start it first (Win+R):\n"
                f'  msedge --remote-debugging-port={CDP_PORT} --user-data-dir="{EDGE_PROFILE}"\n'
                "open Power BI in that window, then run this again "
                "(or re-run with --start-edge to let the script do it)."
            )

    t0 = time.time()
    export_folder = step_export(log, args.skip_export, refresh=not args.no_refresh)
    step_report(log, args.skip_report)
    step_stage(log, export_folder, day_folder, report_date)
    step_daily_reports(log)

    log()
    log(f"Done in {time.time() - t0:.0f}s. Files for {report_date:%m/%d/%Y} are in:")
    log(f"  {day_folder}")
    for p in sorted(day_folder.rglob("*")):
        if p.is_file():
            log(f"    {p.relative_to(day_folder)}")
    log("Check the Daily workbooks, then upload to SharePoint.")

    if not args.no_open and os.name == "nt":
        os.startfile(day_folder)  # type: ignore[attr-defined]


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"\nERROR: {e}", file=sys.stderr)
        raise
