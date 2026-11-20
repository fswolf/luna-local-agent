@echo off
rem Luna, download and go (Windows): double-click to start her. The first
rem run gets her own Python (a minute or two); later runs start her straight away.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0luna.ps1" %*
if errorlevel 1 pause
