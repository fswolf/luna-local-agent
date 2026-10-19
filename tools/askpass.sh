#!/usr/bin/env bash
# sudo -A runs this when Luna's command needs root (shell.sudo on): a password box on YOUR screen.
# The password goes straight from here to sudo - Luna never sees it. Cancel = the command fails.
prompt="${1:-Password for sudo:}"
cmd="${LUNA_SUDO_COMMAND:-a command}"
title="Luna wants root for: ${cmd:0:90}"
if command -v zenity >/dev/null; then exec zenity --password --title="$title"
elif command -v kdialog >/dev/null; then exec kdialog --title "$title" --password "$prompt"
elif command -v yad >/dev/null; then exec yad --entry --hide-text --title="$title" --text="$prompt"
elif command -v ksshaskpass >/dev/null; then exec ksshaskpass "$title"
elif command -v ssh-askpass >/dev/null; then exec ssh-askpass "$title"
elif command -v osascript >/dev/null; then
    exec osascript -e 'on run argv' -e 'text returned of (display dialog (item 1 of argv) with title "Luna" default answer "" with hidden answer)' -e 'end run' "$title"
fi
echo "shell.sudo: no password dialog found - install zenity (sudo dnf install zenity)" >&2
exit 1
