"""ORR Daily Pipeline - small desktop front end for run_pipeline.py.

Double-click this file (it opens without a console window) or make a desktop
shortcut to it. Everything it does goes through run_pipeline.py, so the
scheduled task and this window always behave the same way.
"""
from __future__ import annotations

import datetime as dt
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_pipeline as rp  # noqa: E402  (stdlib-only, safe to import with any Python)

PIPELINE = HERE / "run_pipeline.py"
PYTHON = rp.PYTHON if rp.PYTHON.exists() else Path(sys.executable)
DATA_SOURCES = rp.DATA_SOURCES
LOG_DIR = rp.LOG_DIR
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BG, PANEL, FG, MUTED = "#f4f5f7", "#ffffff", "#1f2933", "#6b7280"
OK, ERR, RUN = "#15803d", "#b91c1c", "#1d4ed8"
LOG_BG, LOG_FG = "#111827", "#e5e7eb"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ORR Daily Pipeline")
        self.configure(bg=BG)
        self.minsize(760, 560)
        self.proc: subprocess.Popen | None = None
        self.q: queue.Queue[tuple[str, object]] = queue.Queue()

        self.opt_edge = tk.BooleanVar(value=True)
        self.opt_skip_export = tk.BooleanVar(value=False)
        self.opt_skip_report = tk.BooleanVar(value=False)

        self._build()
        self.after(100, self._drain)
        if not rp.ACH_REPO.is_dir():
            self._append(f"ach-orr-daily-reports was not found at {rp.ACH_REPO}\n"
                         "Install it there, or set ach_repo in pipeline.yaml.\n", "err")
        if not PYTHON.exists() or PYTHON == Path(sys.executable) and not (HERE / ".venv").exists():
            self._append("No .venv found - run setup.bat once before using the pipeline.\n", "err")
        self._set_status(f"Ready.  Python: {PYTHON}", MUTED)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", foreground=MUTED)
        style.configure("TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 6))
        style.configure("Run.TButton", font=("Segoe UI Semibold", 11), padding=(18, 8))

        head = ttk.Frame(self, padding=(18, 16, 18, 6))
        head.pack(fill="x")
        ttk.Label(head, text="ORR Daily Pipeline", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, style="Sub.TLabel",
                  text=f"Power BI export  >  report capture  >  {rp.day_folder_for()}  >  HSI / UACB Daily workbooks"
                  ).pack(anchor="w")

        opts = ttk.Frame(self, padding=(18, 6))
        opts.pack(fill="x")
        ttk.Checkbutton(opts, text="Start the debug Edge first (closes any open Edge windows)",
                        variable=self.opt_edge).pack(anchor="w")
        ttk.Checkbutton(opts, text="Skip Power BI export (reuse today's HSI / UACB files)",
                        variable=self.opt_skip_export).pack(anchor="w")
        ttk.Checkbutton(opts, text="Skip report capture (reuse today's PNGs and Word doc)",
                        variable=self.opt_skip_report).pack(anchor="w")

        btns = ttk.Frame(self, padding=(18, 8))
        btns.pack(fill="x")
        self.btn_run = ttk.Button(btns, text="Run today's pipeline", style="Run.TButton", command=self.run_pipeline)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Open today's folder", command=self.open_folder).pack(side="right")
        ttk.Button(btns, text="Open latest log", command=self.open_log).pack(side="right", padx=8)
        ttk.Button(btns, text="Start Edge only", command=self.start_edge).pack(side="right")

        self.log = scrolledtext.ScrolledText(self, bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG,
                                             font=("Consolas", 10), relief="flat", padx=12, pady=10,
                                             state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 8))
        self.log.tag_configure("ok", foreground="#86efac")
        self.log.tag_configure("err", foreground="#fca5a5")
        self.log.tag_configure("hdr", foreground="#93c5fd")

        self.status = tk.Label(self, anchor="w", bg=BG, fg=MUTED, font=("Segoe UI", 10), padx=18, pady=8)
        self.status.pack(fill="x")

    # ------------------------------------------------------------------ actions
    def run_pipeline(self) -> None:
        args = ["--no-open"]
        if self.opt_edge.get():
            args.append("--start-edge")
        if self.opt_skip_export.get():
            args.append("--skip-export")
        if self.opt_skip_report.get():
            args.append("--skip-report")
        self._launch(args, "Pipeline")

    def start_edge(self) -> None:
        self._launch(["--edge-only"], "Start Edge")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           capture_output=True, creationflags=NO_WINDOW)
            self._append("Stopped by user.\n", "err")

    def open_folder(self) -> None:
        folder = rp.day_folder_for()
        target = folder if folder.exists() else (DATA_SOURCES if DATA_SOURCES.exists() else HERE)
        os.startfile(target)  # type: ignore[attr-defined]

    def open_log(self) -> None:
        logs = sorted(LOG_DIR.glob("pipeline_*.log")) if LOG_DIR.exists() else []
        if not logs:
            messagebox.showinfo("No logs yet", "Nothing has been run yet.")
            return
        os.startfile(logs[-1])  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ plumbing
    def _launch(self, args: list[str], label: str) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Busy", "Something is already running.")
            return
        if not PIPELINE.exists():
            messagebox.showerror("Missing file", f"Could not find {PIPELINE}")
            return
        env = dict(os.environ, NO_PROXY="127.0.0.1,localhost", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        cmd = [str(PYTHON), "-u", str(PIPELINE), *args]
        self._clear()
        self._append(f"{label}: {' '.join(cmd[2:])}\n\n", "hdr")
        self._set_status(f"{label} running...", RUN)
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        try:
            self.proc = subprocess.Popen(cmd, cwd=str(HERE), env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                         errors="replace", bufsize=1, creationflags=NO_WINDOW)
        except OSError as e:
            self._finish(label, 1, str(e))
            return
        threading.Thread(target=self._pump, args=(self.proc, label), daemon=True).start()

    def _pump(self, proc: subprocess.Popen, label: str) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self.q.put(("line", line))
        rc = proc.wait()
        self.q.put(("done", (label, rc)))

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "line":
                    text = str(payload)
                    tag = "hdr" if "===" in text else ("err" if "ERROR" in text or "WARNING" in text else None)
                    self._append(text, tag)
                else:
                    label, rc = payload  # type: ignore[misc]
                    self._finish(label, int(rc))
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _finish(self, label: str, rc: int, detail: str = "") -> None:
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        if rc == 0:
            self._append(f"\n{label} finished successfully.\n", "ok")
            self._set_status(f"{label} finished at {dt.datetime.now():%I:%M %p}.", OK)
        else:
            self._append(f"\n{label} failed (exit code {rc}). {detail}\n", "err")
            self._set_status(f"{label} failed - see the messages above.", ERR)

    def _append(self, text: str, tag: str | None = None) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text, tag) if tag else self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear(self) -> None:
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status.config(text=text, fg=color)


if __name__ == "__main__":
    App().mainloop()
