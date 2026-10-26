#!/bin/sh
# Builds dist/yomi-<version>.zip containing the "yomi" folder to drop into game/.
# Usage: utils/package.sh [version]
# Runs in Git Bash, WSL or Linux; needs Python (as python or python3).
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-0.1}"
STAGE="$HERE/dist/stage"
OUT="$HERE/dist/yomi-$VERSION.zip"

# Python is "python" on Windows and "python3" on most Linux systems (WSL
# included). Each candidate is tried, because Windows can have a "python3"
# that only opens the Microsoft Store.
PYTHON=""
for candidate in python python3; do
    if "$candidate" -c "" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Python not found (tried python and python3). Install it, or run this from Git Bash." >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r "$HERE/yomi" "$STAGE/yomi"

# Remove generated and per-install files.
find "$STAGE/yomi" \( -name "*.pyc" -o -name "*.pyo" -o -name "*.rpyc" -o -name "yomi_log.txt" \) -delete
rm -rf "$STAGE/yomi/__pycache__"

rm -f "$OUT"
(cd "$STAGE" && "$PYTHON" -c "
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk('yomi'):
        for f in files:
            z.write(os.path.join(root, f))
" "$OUT")
rm -rf "$STAGE"
ls -la "$OUT"
