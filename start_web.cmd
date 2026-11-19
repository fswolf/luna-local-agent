@echo off
rem Luna in her own window (the web UI), no console to keep open: the same as start.cmd --web.
rem start.cmd is the terminal instead.
call "%~dp0start.cmd" --web %*
