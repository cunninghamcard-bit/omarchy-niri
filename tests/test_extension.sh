#!/bin/bash
# Smallest check that fails if rebuild breaks: a patch lands on a copy of the
# base file (materialized through the package's symlink) and the base is untouched.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/base/bin" "$tmp/prefix/patches/bin" "$tmp/state"
printf '#!/bin/bash\necho hyprland\n' >"$tmp/real-command"
ln -s "$tmp/real-command" "$tmp/base/bin/example"
cp "$here/omarchy-niri-extension" "$tmp/prefix/"
cat >"$tmp/prefix/patches/bin/example.patch" <<'PATCH'
--- a/bin/example
+++ b/bin/example
@@ -1,2 +1,2 @@
 #!/bin/bash
-echo hyprland
+echo niri
PATCH
export OMARCHY_NIRI_PREFIX=$tmp/prefix OMARCHY_NIRI_STATE=$tmp/state OMARCHY_NIRI_BASE=$tmp/base OMARCHY_NIRI_NO_MOUNT=1
"$tmp/prefix/omarchy-niri-extension" rebuild
[[ $(cat "$tmp/state/patched/bin/example") == $'#!/bin/bash\necho niri' ]] || { echo "FAIL: patch not applied"; exit 1; }
[[ ! -L $tmp/state/patched/bin/example ]] || { echo "FAIL: symlink not materialized"; exit 1; }
[[ $(cat "$tmp/real-command") == $'#!/bin/bash\necho hyprland' ]] || { echo "FAIL: base modified"; exit 1; }
[[ ! -e $tmp/state/rebuild-failed ]] || { echo "FAIL: spurious failure record"; exit 1; }
echo "ok: rebuild applies patches onto a copy of the base"
