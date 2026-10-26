#!/bin/sh
# Builds dist/yomi-<version>.zip containing the "yomi" folder to drop into game/.
# Usage: utils/package.sh [version]
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-0.1}"
STAGE="$HERE/dist/stage"

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r "$HERE/yomi" "$STAGE/yomi"

# Remove generated and per-install files.
find "$STAGE/yomi" \( -name "*.pyc" -o -name "*.pyo" -o -name "*.rpyc" -o -name "yomi_log.txt" \) -delete
rm -rf "$STAGE/yomi/__pycache__"

OUT="$HERE/dist/yomi-$VERSION.zip"
rm -f "$OUT"
(cd "$STAGE" && python -c "
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk('yomi'):
        for f in files:
            z.write(os.path.join(root, f))
" "$OUT")
rm -rf "$STAGE"
ls -la "$OUT"
