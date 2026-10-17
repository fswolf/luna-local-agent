#!/usr/bin/env bash
# Update Luna to the latest version from GitHub:   ./update.sh
#
#   1. copies config.json to agent/backups/ first, so your settings are safe
#   2. pulls the update, keeping any changes you made (git's autostash)
#   3. installs any Python packages the update added
#   4. checks her servers and says plainly what's missing, if anything
cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")" || exit 1

if [ ! -d .git ]; then
    echo "This folder isn't a git clone, so there's nothing to pull. Clone it again with:"
    echo "  git clone https://github.com/fswolf/luna-local-agent.git ~/ai-voice"
    exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
backup="agent/backups/config-$stamp.json"
if [ -f config.json ]; then
    mkdir -p agent/backups
    cp config.json "$backup" && echo "Saved your config.json as $backup"
fi

before=$(git rev-parse HEAD)
if ! git pull --autostash; then
    echo
    echo "The update didn't go through. 'git status' shows what's in the way."
    [ -f "$backup" ] && echo "Your config.json is safe in $backup."
    exit 1
fi

# Your changes and the update's in the same file: git leaves that file
# marked as conflicted. config.json is yours, so it goes back to your
# copy (anything new the update added has its default in the code).
conflicted=$(git diff --name-only --diff-filter=U)
if [ -n "$conflicted" ]; then
    if echo "$conflicted" | grep -qx "config.json" && [ -f "$backup" ]; then
        git checkout -q HEAD -- config.json && cp "$backup" config.json
        echo "config.json: kept your settings."
        conflicted=$(git diff --name-only --diff-filter=U)
    fi
    if [ -n "$conflicted" ]; then
        echo
        echo "These files have both your changes and the update's in them:"
        echo "$conflicted" | sed 's/^/  /'
        echo "To take the update's version of one:   git checkout HEAD -- <file>"
        echo "Your own version is kept in the stash:  git stash list"
        exit 1
    fi
    git reset -q                    # your other changes stay as they were, just unstaged
    git stash drop -q 2>/dev/null   # settled: the autostash isn't needed any more
fi

if [ "$before" = "$(git rev-parse HEAD)" ]; then
    echo "Already up to date."
else
    echo
    echo "What's new:"
    git --no-pager log --oneline --no-decorate "$before"..HEAD | head -20
fi
echo
exec ./start.sh --update
