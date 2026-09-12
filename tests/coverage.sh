#!/bin/bash
# Build the same complete candidate used by install/update and scan its final
# contents. A grep over the repository can pass while a patch leaves a call in
# the materialized runtime, so compatibility checking belongs in compat.py.
set -euo pipefail
upstream=${1:?usage: coverage.sh <omarchy checkout>}
here=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" python3 - "$upstream" "$here" "$tmp/runtime" <<'PY'
import sys
from pathlib import Path
from compat import prepare

base, source, destination = map(Path, sys.argv[1:])
try:
    report = prepare(base, destination, source)
except Exception as error:
    print(f"compatibility check failed: {error}", file=sys.stderr)
    raise SystemExit(1)
print(f"compatibility ok: {report['patches']} patches; runtime={destination}")
PY
