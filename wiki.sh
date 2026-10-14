#!/usr/bin/env bash
#
# Copy docs/ to the GitHub wiki and push it.
#
#   ./wiki.sh                  -> "Sync from docs/ 2026-10-14 21:05"
#   ./wiki.sh new knowledge    -> that, as the commit message
#   ./wiki.sh -n               -> show what would change, push nothing
#
# The wiki is its own git repo (<this repo>.wiki.git), kept in
# ~/luna-wiki (or $WIKI_DIR) and cloned the first time. GitHub wants it
# a little different from docs/: the front page is Home.md, and links
# between pages have no .md on the end. This takes care of both, so
# docs/ stays the one place you edit.
#
# The wiki has to exist first: open the Wiki tab on GitHub once and save
# any page, or the clone has nothing to clone.
#
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
REPO="$PWD"
WIKI_DIR="${WIKI_DIR:-$HOME/luna-wiki}"

DRY=0
if [ "${1:-}" = "-n" ] || [ "${1:-}" = "--dry-run" ]; then
    DRY=1
    shift
fi

MESSAGE="${*:-Sync from docs/ $(date '+%Y-%m-%d %H:%M')}"

# The wiki's address, from this repo's own remote, so a fork syncs to
# its own wiki rather than this one.
ORIGIN="$(git -C "$REPO" remote get-url origin)"
WIKI_URL="${ORIGIN%.git}.wiki.git"

if [ ! -d "$WIKI_DIR/.git" ]; then
    echo "Cloning the wiki into $WIKI_DIR"
    git clone "$WIKI_URL" "$WIKI_DIR"
fi

git -C "$WIKI_DIR" pull --quiet --rebase

python3 - "$REPO/docs" "$WIKI_DIR" <<'EOF'
import os, re, sys
src, dst = sys.argv[1], sys.argv[2]
# [text](page.md) and [text](page.md#part) -> [text](page) / (page#part);
# web links, mail links and #anchors are left alone.
link = re.compile(r"\]\((?!https?://|mailto:|#)([A-Za-z0-9_\-]+)\.md(#[^)]*)?\)")
for name in sorted(os.listdir(src)):
    if not name.endswith(".md"):
        continue
    with open(os.path.join(src, name), encoding="utf-8") as f:
        text = f.read()
    text = link.sub(lambda m: "](" + ("Home" if m.group(1) == "README" else m.group(1)) + (m.group(2) or "") + ")", text)
    with open(os.path.join(dst, "Home.md" if name == "README.md" else name), "w", encoding="utf-8") as f:
        f.write(text)
EOF

cd "$WIKI_DIR"

if [ -z "$(git status --porcelain)" ]; then
    echo "The wiki already matches docs/."
    exit 0
fi

git status --short

if [ "$DRY" = 1 ]; then
    echo "(dry run: nothing committed)"
    git checkout --quiet -- .        # new pages stay as untracked files until a real run
    exit 0
fi

git add -A
git commit --quiet -m "$MESSAGE"
git push --quiet
echo "Wiki updated: ${WIKI_URL%.wiki.git}/wiki"
