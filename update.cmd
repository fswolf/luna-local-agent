@echo off
rem Update Luna to the latest version from GitHub (Windows):   update.cmd
rem   1. copies config.json to agent\backups\ first, so your settings are safe
rem   2. pulls the update, keeping any changes you made (git's autostash)
rem   3. installs any Python packages the update added, then checks her servers
rem update.sh does the same on Linux and macOS. Not tested on Windows yet.
setlocal
cd /d "%~dp0"

if not exist ".git" (
    echo This folder isn't a git clone, so there's nothing to pull. Clone it again with:
    echo   git clone https://github.com/fswolf/luna-local-agent.git
    goto :fail
)
where git >nul 2>nul || (echo git isn't installed - get it from https://git-scm.com & goto :fail)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "stamp=%%i"
set "backup=agent\backups\config-%stamp%.json"
if exist config.json (
    if not exist agent\backups mkdir agent\backups
    copy /y config.json "%backup%" >nul && echo Saved your config.json as %backup%
)

git pull --autostash
if errorlevel 1 goto :clash
git diff --name-only --diff-filter=U | findstr . >nul
if not errorlevel 1 goto :clash

echo.
if exist luna.cmd (
    call luna.cmd --update
) else (
    python launch.py --update
)
goto :end

:clash
echo.
echo The update didn't go through cleanly - you and the update changed the same file.
echo 'git status' shows which. To take the update's version of one:  git checkout HEAD -- ^<file^>
if exist "%backup%" echo Your config.json is safe in %backup% - copy it back over config.json to keep your settings.
:fail
pause
exit /b 1

:end
endlocal
