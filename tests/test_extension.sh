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
grep -Fq 'command: ["bash", "-c", "\"$0\" sync; \"$0\" notify", extension]' "$here/plugin/Service.qml" || {
  echo "FAIL: service does not invoke sync and notify" >&2
  exit 1
}

state="$tmp/state"
out=$(OMARCHY_NIRI_STATE="$state" python3 "$here/manage.py" status)
[[ "$out" == "Niri extension is not installed." ]] || {
  echo "FAIL: unexpected status output: $out" >&2
  exit 1
}

python3 "$here/manage.py" --help >/dev/null

# The unprivileged user step: fresh home, second run rewrites nothing, unsync strips only the block.
mkdir -p "$tmp/bin"
printf '#!/bin/sh\n: > "$HOME/.config/niri/omarchy-theme.kdl"\n' > "$tmp/bin/omarchy-niri"
chmod +x "$tmp/bin/omarchy-niri"
home="$tmp/home"
snapshot() {
  python3 - "$home" <<'PY'
import sys
from pathlib import Path
home = Path(sys.argv[1])
for path in sorted(p for p in home.rglob('*') if p.is_file()):
    info = path.stat()
    print(path.relative_to(home), info.st_ino, info.st_mtime_ns)
PY
}
HOME="$home" PATH="$tmp/bin:$PATH" python3 "$here/manage.py" sync
[[ ! -e "$home/.config/niri" ]] || { echo "FAIL: sync touched Niri config before installation" >&2; exit 1; }
HOME="$home" PATH="$tmp/bin:$PATH" python3 "$here/manage.py" sync --force
[[ -f "$home/.config/niri/config.kdl" && -f "$home/.config/niri/omarchy/config.kdl" ]] || {
  echo "FAIL: sync did not create the Niri config" >&2
  exit 1
}
before=$(snapshot)
HOME="$home" PATH="$tmp/bin:$PATH" python3 "$here/manage.py" sync --force
after=$(snapshot)
[[ "$before" == "$after" ]] || { echo "FAIL: second sync rewrote files" >&2; exit 1; }
HOME="$home" PATH="$tmp/bin:$PATH" python3 "$here/manage.py" unsync
[[ ! -e "$home/.config/niri/omarchy" && -f "$home/.config/niri/input.kdl" ]] || {
  echo "FAIL: unsync did not strip only the managed files" >&2
  exit 1
}

echo "ok: plugin service and unprivileged manager smoke checks"
