#!/usr/bin/env bash
# Capture one Anki window straight into docs/images/ with the right filename.
#
#   ./docs/grab.sh home
#
# The cursor becomes a camera: hover the Anki window and click. Escape cancels.
set -euo pipefail
cd "$(dirname "$0")"

declare -a NAMES=(home stats settings reviewer session)
declare -a HINTS=(
  "the deck list, with the panel showing cards due and an ETA"
  "Tools > Pace Estimator, scrolled to the by-deck table"
  "the settings dialog, on the 'Speed & accuracy' tab"
  "a card that has run over its time, with the ! showing"
  "the deck list just after finishing a deck, showing the session summary"
)

name="${1:-}"
index=-1
for i in "${!NAMES[@]}"; do [ "${NAMES[$i]}" = "$name" ] && index=$i; done
if [ "$index" -lt 0 ]; then
  echo "usage: ./docs/grab.sh <name>"
  echo
  for i in "${!NAMES[@]}"; do printf "  %-9s %s\n" "${NAMES[$i]}" "${HINTS[$i]}"; done
  exit 1
fi

out="images/$name.png"
mkdir -p images
echo "Capturing: ${HINTS[$index]}"
echo "Click the Anki window when the cursor becomes a camera (Escape cancels)."
# -i interactive, -W start in window mode, -o drop the window shadow.
screencapture -i -W -o "$out"

if [ ! -f "$out" ]; then
  echo "cancelled - nothing saved."
  exit 1
fi
width=$(sips -g pixelWidth "$out" | awk '/pixelWidth/{print $2}')
if [ "$width" -gt 900 ]; then
  sips --resampleWidth 900 "$out" >/dev/null
  echo "saved $out (${width}px, scaled to 900px for AnkiWeb)"
else
  echo "saved $out (${width}px)"
fi
