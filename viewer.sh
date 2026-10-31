#!/usr/bin/env bash
# The old name for ./studio.sh, kept so it still works.
exec "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/studio.sh" "$@"
