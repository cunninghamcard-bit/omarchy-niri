#!/bin/bash
# Local, unprivileged smoke checks for the plugin entry point and manager CLI.
# Real system installation is covered separately on an Omarchy host; this test
# must never write /etc, /usr, or the user's runtime state.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

manifest=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["entryPoints"]["service"])' "$here/manifest.json")
[[ "$manifest" == "plugin/Service.qml" ]] || { echo "FAIL: service entry point" >&2; exit 1; }
rg -q 'command: \["bash", extension, "notify"\]' "$here/plugin/Service.qml" || {
  echo "FAIL: service does not invoke notify" >&2
  exit 1
}

state="$tmp/state"
out=$(OMARCHY_NIRI_STATE="$state" python3 "$here/manage.py" status)
[[ "$out" == "Niri extension is not installed." ]] || {
  echo "FAIL: unexpected status output: $out" >&2
  exit 1
}

python3 "$here/manage.py" --help >/dev/null
echo "ok: plugin service and unprivileged manager smoke checks"
