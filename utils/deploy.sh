#!/bin/sh
# Copies the mod into a game's game/ directory.
# Usage: utils/deploy.sh "<game directory, the one containing game/>"
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 \"<game directory, the one containing game/>\"" >&2
    exit 1
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$1/game/yomi"

mkdir -p "$DEST"
# Replace the data folder so files dropped from the build don't linger.
rm -rf "$DEST/data"
cp -r "$HERE/yomi/." "$DEST/"
rm -f "$DEST"/*.pyc "$DEST"/*.pyo
rm -rf "$DEST/__pycache__"
echo "Deployed to $DEST"
