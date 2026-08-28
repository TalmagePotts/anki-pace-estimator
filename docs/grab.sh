#!/usr/bin/env bash
# Capture one Anki window straight into docs/images/ with the right filename.
#
#   ./docs/grab.sh home
#
# The cursor becomes a camera: hover the Anki window and click. Escape cancels.
set -euo pipefail
cd "$(dirname "$0")"

declare -a NAMES=(home stats reviewer session settings)
declare -a HINTS=(
  "the deck list, with the panel showing cards due and an ETA"
  "Tools > Pace Estimator, scrolled to the by-deck table"
  "a card over its time, with the heads-up box and the ! both showing"
  "the deck list just after finishing a deck, showing the session summary"
  "the settings dialog (optional, not used in the listing)"
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
echo "Drag a box around just the part you want."
echo "  space  = switch to whole-window mode instead"
echo "  escape = cancel"
# Region mode by default: a whole-window shot of the deck list would put every
# deck name on a public listing page.
screencapture -i -o "$out"

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
