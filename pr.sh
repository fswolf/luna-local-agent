#!/usr/bin/env bash
#
# Send changes as a pull request instead of pushing to main.
#
#   ./pr.sh setup              one-time: GitHub CLI, login, your name/email
#   ./pr.sh fixed the voice    commit to a new branch, push, open a PR
#   ./pr.sh                    push the branch you're on and open/refresh its PR
#   ./pr.sh done               after the PR is merged: back to main, pull, tidy up
#
# Personal and private files (the same ones push.sh knows about) are never
# committed, so config.json and your conversations stay on this machine.
#
set -euo pipefail
cd "$(dirname "$0")"

PRIVATE_PATTERN='agent/memory\.json|history/conversation\.json|history/transcript\.jsonl|reminders/reminders\.json|Claude outputs/'
PERSONAL_PATTERN='^config\.json$|^agent/agent\.json$'
BASE=main

die() { echo "$*" >&2; exit 1; }
ask() { printf '%s [y/N] ' "$1"; read -r r; [ "$r" = y ] || [ "$r" = Y ]; }

need_gh() {
    command -v gh >/dev/null || die "GitHub CLI missing - run: ./pr.sh setup"
    gh auth status >/dev/null 2>&1 || die "Not logged in to GitHub - run: ./pr.sh setup"
}

setup() {
    if ! command -v gh >/dev/null; then
        if command -v brew >/dev/null; then brew install gh
        elif command -v dnf >/dev/null; then sudo dnf install -y gh
        else die "Install the GitHub CLI first: https://cli.github.com"; fi
    fi
    gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web
    gh auth setup-git

    if [ -z "$(git config user.name || true)" ]; then
        printf 'Your name for commits: '; read -r n; git config --global user.name "$n"
    fi
    # GitHub's private no-reply address: links commits to the account
    # without publishing a real email. Also repairs a bad earlier value.
    e=$(git config user.email || true)
    case "$e" in *@*.*) case "$e" in *'{'*) e="" ;; esac ;; *) e="" ;; esac
    if [ -z "$e" ]; then
        e=$(gh api user -q '"\(.id)+\(.login)@users.noreply.github.com"' 2>/dev/null || true)
        case "$e" in *+*@users.noreply.github.com) ;; *) printf 'Your GitHub email: '; read -r e ;; esac
        git config --global user.email "$e"
    fi
    echo "Ready as $(git config user.name) <$(git config user.email)> / GitHub: $(gh api user -q .login)"
}

done_cmd() {
    need_gh
    branch=$(git rev-parse --abbrev-ref HEAD)
    [ "$branch" != "$BASE" ] || { git pull --ff-only; exit 0; }
    state=$(gh pr view --json state -q .state 2>/dev/null || echo NONE)
    [ "$state" = MERGED ] || ask "PR for '$branch' is $state, not merged. Leave it anyway?" || exit 0
    git switch "$BASE"
    git pull --ff-only
    git branch -D "$branch"
    git push origin --delete "$branch" 2>/dev/null || true
    echo "Back on $BASE, up to date."
}

case "${1:-}" in
    setup) setup; exit 0 ;;
    done)  done_cmd; exit 0 ;;
esac

git rev-parse --git-dir >/dev/null 2>&1 || die "Not a git repo: $PWD"
need_gh

MESSAGE="${*:-Update $(date '+%Y-%m-%d %H:%M')}"
git fetch --quiet origin

# Stage everything except personal/private files.
stage() {
    git add -A
    git diff --cached --name-only | grep -E "$PERSONAL_PATTERN|$PRIVATE_PATTERN" | while IFS= read -r f; do
        git reset -q -- "$f"
    done || true
}

branch=$(git rev-parse --abbrev-ref HEAD)

if [ "$branch" = "$BASE" ]; then
    stage
    ahead=$(git rev-list --count "origin/$BASE..HEAD")
    if git diff --cached --quiet && [ "$ahead" = 0 ]; then
        git reset -q
        echo "Nothing to send."; exit 0
    fi
    slug=$(echo "$MESSAGE" | tr 'A-Z' 'a-z' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//' | cut -c1-40)
    branch="$(gh api user -q .login)/${slug:-update}"
    git switch -c "$branch"
    # Commits made on main by mistake go with the branch; main goes back to GitHub's.
    [ "$ahead" = 0 ] || git branch -f "$BASE" "origin/$BASE"
else
    stage
fi

if ! git diff --cached --quiet; then
    echo "Committing:"; git diff --cached --name-status | sed 's/^/  /'
    echo "Message: $MESSAGE"
    ask "Commit these to '$branch'?" || { git reset -q; echo "Cancelled."; exit 0; }
    git commit -q -m "$MESSAGE"
fi

git diff --quiet "origin/$BASE" HEAD 2>/dev/null && [ "$(git rev-list --count "origin/$BASE..HEAD")" = 0 ] \
    && { echo "Branch has nothing GitHub doesn't."; exit 0; }

# Catch up with main first, so the PR merges cleanly.
if [ "$(git rev-list --count "HEAD..origin/$BASE")" -gt 0 ]; then
    echo "main moved on GitHub - rebasing onto it."
    git rebase --autostash "origin/$BASE" || {
        git rebase --abort
        die "Conflict while rebasing. Fix by hand: git rebase origin/$BASE"
    }
fi

git push --force-with-lease -u origin "$branch"

url=$(gh pr view "$branch" --json url,state -q 'select(.state=="OPEN").url' 2>/dev/null || true)
if [ -n "$url" ]; then
    echo "PR updated: $url"
else
    gh pr create --base "$BASE" --head "$branch" --fill
fi
echo "After it's merged: ./pr.sh done"
