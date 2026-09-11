#!/bin/bash
# List upstream files that talk to Hyprland and are neither replaced nor patched.
# Early warning when a new Omarchy release adds a compositor call we do not cover.
set -euo pipefail
upstream=${1:?usage: coverage.sh <omarchy checkout>}
here=$(cd "$(dirname "$0")/.." && pwd)
# Hyprland-only trees and files whose only hit is prose.
ignore='^(default/hypr/|config/hypr/|default/agents/|default/voxtype/|bin/omarchy-upgrade-to-quattro$|shell/plugins/bar/widgets/KeyboardLayoutModel\.js$)'
covered() { [[ -e $here/overlay/$1 || -e $here/patches/$1.patch ]]; }
status=0
# "hyprctl" as a command (not omarchy-restart-hyprctl), or the Quickshell Hyprland module.
for file in $(grep -rl -I -E '(^|[^[:alnum:]_-])hyprctl\b|Quickshell\.Hyprland|\bHyprland\.[a-z]' "$upstream"/{bin,shell,default,config} | sort); do
  rel=${file#"$upstream/"}
  [[ $rel =~ $ignore ]] && continue
  covered "$rel" && continue
  echo "uncovered: $rel"
  status=1
done
exit $status
