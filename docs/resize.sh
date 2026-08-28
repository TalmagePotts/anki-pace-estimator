#!/usr/bin/env bash
# Scale listing screenshots down to a width AnkiWeb can show.
#
# AnkiWeb strips width/height attributes, so the file's own dimensions are the
# only control there is. Retina captures are 2x and must be halved.
set -euo pipefail
cd "$(dirname "$0")/images"

MAX=900
shopt -s nullglob
for f in *.png; do
  w=$(sips -g pixelWidth "$f" | awk '/pixelWidth/{print $2}')
  if [ "$w" -gt "$MAX" ]; then
    sips --resampleWidth "$MAX" "$f" >/dev/null
    echo "resized $f  ${w}px -> ${MAX}px"
  else
    echo "kept    $f  ${w}px"
  fi
done
