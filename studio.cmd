@echo off
rem The studio on Windows: Luna's portrait on its own, no Luna, with the control
rem panel and the pose studio. Opens in a window of its own and runs in the
rem background (no console left open); it stops by itself once its window is closed.
rem   studio.cmd --tab   open it in your usual browser instead
rem   studio.cmd --fg    keep it in this console (Ctrl+C stops it)
rem studio.sh does the same on Linux and macOS. Not tested on Windows yet.
rem What it says goes to %USERPROFILE%\.cache\ai-voice\studio.log
setlocal
cd /d "%~dp0"

set "py="
if exist install.json for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-Content -Raw install.json | ConvertFrom-Json).venv_python"`) do set "py=%%i"
if not defined py if exist "venv\Scripts\python.exe" set "py=venv\Scripts\python.exe"
if not defined py if exist ".venv\Scripts\python.exe" set "py=.venv\Scripts\python.exe"
if not defined py set "py=python"

if /i "%~1"=="--fg" (
    "%py%" portrait\viewer\view.py %*
    goto :end
)

rem pythonw.exe sits beside python.exe and runs with no console window
set "pyw=%py:python.exe=pythonw.exe%"
if not exist "%pyw%" set "pyw=pythonw"
start "" "%pyw%" portrait\viewer\view.py %*
echo Studio opening. It stops by itself when you close it.

:end
endlocal
