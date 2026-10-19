@echo off
setlocal
REM ===========================================================================
REM  ORR Daily Pipeline - one-time setup.  Safe to run again at any time.
REM
REM   1. finds Python 3 (no admin rights needed - a per-user install is fine)
REM   2. creates .venv and installs the two Power BI tools + pandas/openpyxl
REM   3. checks the ach-orr-daily-reports scripts are present (bundled, or ach_repo in pipeline.yaml)
REM   4. creates the dedicated Edge profile folder
REM   5. puts an "ORR Daily Pipeline" shortcut (duck icon) on your Desktop
REM ===========================================================================
cd /d "%~dp0"
set "ROOT=%cd%"
echo.
echo  ORR Daily Pipeline setup
echo  %ROOT%
echo.

REM ---- 1. Python ------------------------------------------------------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
    echo  [!] Python 3.10 or newer was not found.
    echo      Install it from https://www.python.org/downloads/windows/  -  choose
    echo      "Install for me only" ^(no admin needed^) and tick "Add python.exe to PATH".
    echo      Then run setup.bat again.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%v"
echo  [1/5] Python %PYVER% found

REM ---- 2. Virtual environment + packages -------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [2/5] Creating .venv ...
    %PY% -m venv .venv || goto :fail
) else (
    echo  [2/5] .venv already exists
)
set "VPY=%ROOT%\.venv\Scripts\python.exe"
echo        Installing packages ^(this takes a few minutes the first time^) ...
"%VPY%" -m pip install --quiet --upgrade pip
"%VPY%" -m pip install --quiet -r requirements.txt || goto :pipfail
echo        Packages installed

REM ---- 3. ach-orr-daily-reports -----------------------------------------------
for /f "delims=" %%p in ('"%VPY%" -c "import run_pipeline as rp; print(rp.ACH_REPO)"') do set "ACH=%%p"
if exist "%ACH%\run_daily_reports.py" (
    echo  [3/5] ach-orr-daily-reports found at %ACH%
) else (
    echo  [3/5] ach-orr-daily-reports was NOT found at:
    echo          %ACH%
    echo        If you set ach_repo in pipeline.yaml, check that path. Otherwise the bundled
    echo        copy in this folder is missing - re-download or git pull this repo.
    set "ACH_MISSING=1"
)

REM ---- 4. Edge profile folder -------------------------------------------------
for /f "delims=" %%p in ('"%VPY%" -c "import run_pipeline as rp; print(rp.EDGE_PROFILE)"') do set "EDGEPROF=%%p"
if not exist "%EDGEPROF%" mkdir "%EDGEPROF%"
echo  [4/5] Edge debug profile folder: %EDGEPROF%

REM ---- 5. Desktop shortcut ----------------------------------------------------
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\ORR Daily Pipeline.lnk\"); $s.TargetPath='%PYW%'; $s.Arguments='\"%ROOT%\pipeline_app.pyw\"'; $s.WorkingDirectory='%ROOT%'; $s.IconLocation='%ROOT%\duck.ico,0'; $s.Description='ORR Daily Pipeline'; $s.Save()" >nul 2>&1
if errorlevel 1 (
    echo  [5/5] Could not create the Desktop shortcut automatically.
    echo        Right-click pipeline_app.pyw ^> Send to ^> Desktop instead.
) else (
    echo  [5/5] Desktop shortcut "ORR Daily Pipeline" created
)

echo.
echo  Setup complete.  Next:
if defined ACH_MISSING echo    0. Install ach-orr-daily-reports ^(see step 3 above^) - the pipeline will not run without it.
echo    1. Double-click the "ORR Daily Pipeline" shortcut on your Desktop.
echo    2. Click "Start Edge only", and sign in to Power BI in the Edge window that opens
echo       ^(first time only - the profile remembers you afterwards^).
echo    3. Click "Run today's pipeline".
echo.
pause
exit /b 0

:pipfail
echo.
echo  [!] pip could not install the packages. If you are on the HHS network this is
echo      usually the proxy - try again, or run:  "%VPY%" -m pip install -r requirements.txt
echo      to see the full error.
pause
exit /b 1

:fail
echo.
echo  [!] Setup stopped. Fix the problem above and run setup.bat again.
pause
exit /b 1
