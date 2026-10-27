#!/usr/bin/env bash
set -euo pipefail

"$VCPKG_ROOT/vcpkg" install tesseract --triplet="$TRIPLET" --disable-metrics
