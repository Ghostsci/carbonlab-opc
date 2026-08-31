#!/bin/sh
set -eu

PACKAGE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0

"$PYTHON_BIN" "$PACKAGE_ROOT/generator/generate.py" --verify "$PACKAGE_ROOT"

if [ "$#" -gt 1 ]; then
  echo "usage: ./scripts/replay_g1_b_v2.sh [empty-output-directory]" >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  OUTPUT_ROOT=$1
  mkdir -p "$OUTPUT_ROOT"
else
  OUTPUT_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/g1-b-v2-replay.XXXXXX")
fi

"$PYTHON_BIN" "$PACKAGE_ROOT/generator/generate.py" \
  --build \
  --source "$PACKAGE_ROOT" \
  --output "$OUTPUT_ROOT"
"$PYTHON_BIN" "$OUTPUT_ROOT/generator/generate.py" --verify "$OUTPUT_ROOT"

echo "G1-B-v2.0.2 replay PASS: $OUTPUT_ROOT"
