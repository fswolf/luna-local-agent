@echo off
rem Start Luna on Windows from the folder she's in - see launch.py. It starts her
rem voice server too, if the installer set one up, and stops it when she exits.
rem The installer also writes luna.cmd (and a Start menu shortcut), which does the
rem same; this one is here from the start, for a copy that hasn't been installed
rem yet or a luna.cmd that went missing. start.sh does the same on Linux and macOS.
rem Not tested on Windows yet.
setlocal
cd /d "%~dp0"

set "py="
if exist install.json for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-Content -Raw install.json | ConvertFrom-Json).venv_python"`) do set "py=%%i"
if not defined py if exist "venv\Scripts\python.exe" set "py=venv\Scripts\python.exe"
if not defined py if exist ".venv\Scripts\python.exe" set "py=.venv\Scripts\python.exe"
if not defined py (
    echo No virtualenv found - run the installer first: powershell -ExecutionPolicy Bypass -File installer\install.ps1
    echo Trying the system python for now.
    set "py=python"
)

"%py%" launch.py %*
rem a crash: keep the window open long enough to read why
if errorlevel 1 pause
endlocal
