#!/usr/bin/env bash
set -euo pipefail

installed="$VCPKG_ROOT/installed/$TRIPLET"
binary="$(find "$installed" -type f -name tesseract -print -quit)"
if [[ -z "$binary" ]]; then
  echo "Could not find the Tesseract executable in $installed" >&2
  exit 1
fi

mkdir -p bundle dist
cp "$binary" bundle/
# Include runtime libraries installed alongside the executable.
if [[ -d "$installed/bin" ]]; then
  cp -a "$installed/bin/." bundle/
fi
tar -C bundle -czf "dist/tesseract-${TRIPLET}.tar.gz" .
