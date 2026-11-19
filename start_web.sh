#!/usr/bin/env bash
# Luna in her own window (the web UI), no terminal to keep open: the same as
# ./start.sh --web. ./start.sh is the terminal instead.
exec "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/start.sh" --web "$@"
