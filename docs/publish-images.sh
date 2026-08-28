#!/usr/bin/env bash
# Push the screenshots so the AnkiWeb listing's image URLs resolve.
set -euo pipefail
cd "$(dirname "$0")/.."

missing=()
for n in home stats reviewer; do
  [ -f "docs/images/$n.png" ] || missing+=("$n")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "still missing: ${missing[*]}"
  echo "take them with:  ./docs/grab.sh <name>"
  exit 1
fi

git add docs/images
git commit -m "Add listing screenshots" || echo "(nothing new to commit)"
git push
echo
echo "Live. The listing's images now resolve at:"
for n in home stats reviewer; do
  echo "  https://raw.githubusercontent.com/TalmagePotts/anki-pace-estimator/main/docs/images/$n.png"
done
