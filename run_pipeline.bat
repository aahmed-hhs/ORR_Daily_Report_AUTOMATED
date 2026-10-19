@echo off
REM ORR Daily Pipeline - command-line / Task Scheduler entry point.
REM Extra switches are passed through, e.g.  run_pipeline.bat --start-edge
REM Run setup.bat once first.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo The .venv folder is missing. Run setup.bat first.
    pause
    exit /b 1
)
set NO_PROXY=127.0.0.1,localhost
".venv\Scripts\python.exe" run_pipeline.py %*
if errorlevel 1 (
    echo.
    echo Pipeline stopped with an error. See the logs folder for details.
    pause
)
