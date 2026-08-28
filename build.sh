#!/usr/bin/env bash
# Build the .ankiaddon file AnkiWeb accepts.
#
# AnkiWeb requires the zip to contain the add-on's files at the top level --
# not the folder itself -- and rejects any archive containing __pycache__.
set -euo pipefail

cd "$(dirname "$0")"
SRC=review_pace
OUT=dist/review_pace.ankiaddon

# A placeholder LICENSE is worse than none, so the content is checked, not
# just the file's existence.
if ! grep -q 'GNU AFFERO GENERAL PUBLIC LICENSE' LICENSE 2>/dev/null; then
  echo "error: LICENSE does not contain the licence text." >&2
  echo "       run:  curl -o LICENSE https://www.gnu.org/licenses/agpl-3.0.txt" >&2
  exit 1
fi

echo "==> running tests"
# Uses whichever python has pytest. Packaging is not blocked by a missing dev
# tool, but you are told loudly, because shipping untested code is worse.
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import pytest' 2>/dev/null; then
  .venv/bin/python -m pytest tests -q
elif command -v pytest >/dev/null 2>&1; then
  pytest tests -q
elif python3 -c 'import pytest' 2>/dev/null; then
  python3 -m pytest tests -q
else
  echo "!! pytest not found - the test suite did NOT run."
  echo "!! install it with:  python3 -m pip install --user pytest"
  [ "${SKIP_TESTS:-0}" = "1" ] || { echo "   or re-run as: SKIP_TESTS=1 ./build.sh"; exit 1; }
fi

echo "==> cleaning build leftovers"
find "$SRC" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SRC" -name '*.pyc' -delete
# Anki writes meta.json into an installed add-on's folder; it holds this
# machine's config and must never be shipped.
rm -f "$SRC/meta.json"

echo "==> packaging"
rm -rf dist && mkdir -p dist
cp LICENSE "$SRC/LICENSE"
trap 'rm -f "$SRC/LICENSE"' EXIT
( cd "$SRC" && zip -q -r "../$OUT" . -x '*.DS_Store' )

echo "==> verifying"
# Captured once rather than piped into grep: under `set -o pipefail` a `grep -q`
# that exits early makes unzip die on SIGPIPE, and the check then lies.
LISTING=$(unzip -l "$OUT")

if grep -q '__pycache__\|meta\.json' <<<"$LISTING"; then
  echo "error: archive contains files AnkiWeb rejects" >&2
  exit 1
fi
if ! grep -qE '(^| )__init__\.py$' <<<"$LISTING"; then
  echo "error: __init__.py is not at the top level of the archive" >&2
  exit 1
fi
if ! grep -q 'manifest\.json' <<<"$LISTING"; then
  echo "error: manifest.json is missing from the archive" >&2
  exit 1
fi

echo "$LISTING"
echo
echo "built $OUT  ($(du -h "$OUT" | cut -f1))"
