# hyprctl inventory

Every `hyprctl` invocation in `bin/` of the pinned Omarchy base
(`346e69e1cec6c4e8924531874af6ba010a1bc99e`), obtained by grepping the checkout
and following the `jq` filters to the JSON fields each caller actually reads.
Status is what this repository does to the file today: **replaced**
(`overlay/bin`), **patched** (`patches/bin`), or unmodified upstream.
"Shim-servable" means the calls could be served by `overlay/bin/hyprctl`
without the replacement/patch; the decision for each file is in
[Now served by the shim](#now-served-by-the-shim).

## `monitors` (`-j`; `all` adds disabled outputs)

| File | Status | Args | JSON fields read |
| --- | --- | --- | --- |
| omarchy-bar-text-color | patched | `monitors -j` | `.[0].width`, `.[0].height` |
| omarchy-brightness-display | patched | `monitors -j` | `.disabled`, `.dpmsStatus` (both removed by the patch) |
| omarchy-capture-region | replaced | `monitors -j` | `.focused`, `.activeWorkspace.id`, `.x`, `.y`, `.width`, `.height`, `.scale`, `.transform` |
| omarchy-capture-screenrecording | replaced | `monitors -j` | `.focused`, `.width`, `.height` |
| omarchy-capture-webcam-resize | replaced | `monitors -j` | `.id` (matched against clients `.monitor`) |
| omarchy-hyprland-monitor-clamshell | replaced | `monitors all -j` | `.name`, `.disabled`, `.scale` |
| omarchy-hyprland-monitor-external-active | replaced | `monitors all -j` | `.name`, `.disabled` |
| omarchy-hyprland-monitor-focused | replaced | `monitors -j` | `.focused`, `.name` |
| omarchy-hyprland-monitor-focused-apple | replaced | `monitors -j` | `.focused`, `.name`, `.make`, `.model` |
| omarchy-hyprland-monitor-internal-mirror | replaced | `monitors -j` | `.name` |
| omarchy-hyprland-monitor-laptop | replaced | `monitors all -j` | `.name` |
| omarchy-hyprland-monitor-modeless | replaced | `monitors all -j` | `.disabled`, `.width`, `.height` |
| omarchy-hyprland-monitor-scaling | replaced | `monitors -j` | `.focused`, `.name`, `.scale`, `.width`, `.height`, `.refreshRate` |
| omarchy-hyprland-session-locked | replaced | `-j monitors` (flag first) | `.solitaryBlockedBy` |
| omarchy-launch-screensaver | replaced | `monitors -j` | `.name` |
| omarchy-launch-shell | patched | `-j monitors` (flag first) | none (exit status as a compositor-liveness check) |
| omarchy-menu-herdr-keybindings | patched | `monitors -j` | `.focused`, `.height` |
| omarchy-menu-tmux-keybindings | patched | `monitors -j` | `.focused`, `.height` |
| omarchy-monitor-state | replaced | `monitors all -j` | `.name`, `.focused`, `.disabled`, `.mirrorOf`, `.width`, `.height` |
| omarchy-windows-vm | patched | `monitors -j` | `.focused`, `.scale` |

## `clients` (`-j`)

| File | Status | JSON fields read |
| --- | --- | --- |
| omarchy-capture-screenrecording | replaced | `.title` |
| omarchy-capture-webcam-resize | replaced | `.title`, `.address`, `.size[0]`, `.size[1]`, `.monitor` |
| omarchy-debug-idle | patched (queries removed by the patch) | `.pid`, `.class`, `.initialClass`, `.title`, `.focusHistoryID`, `.inhibitingIdle`, `.tags` |
| omarchy-hyprland-focus-app | replaced | `.class`, `.initialClass`, `.initialTitle`, `.address` |
| omarchy-hyprland-window-close-all | replaced | `.address` |
| omarchy-hyprland-window-width | replaced | `.address`, `.size[0]` |
| omarchy-launch-about | replaced | `.class`, `.address`, `.size[0]`, `.size[1]` |
| omarchy-launch-or-focus | replaced | `.class`, `.title`, `.address` |
| omarchy-launch-signal | replaced | `.class`, `.title`, `.address` |
| omarchy-launch-spotify | replaced | `.class`, `.title`, `.address` |

## `activewindow`

| File | Status | Form | Fields read |
| --- | --- | --- | --- |
| omarchy-cmd-terminal-cwd | patched | plain text | `pid:` line (awk) |
| omarchy-hyprland-window-pop | replaced | `-j` | `.pinned`, `.address` |
| omarchy-hyprland-window-tiled-fullscreen-toggle | replaced | `-j` | `.fullscreenClient` |
| omarchy-hyprland-window-transparency-toggle | replaced | `-j` | `.address` |
| omarchy-hyprland-window-width | replaced | `-j` | `.class`, `.initialClass`, `.title`, `.workspace.id`, `.address`, `.size[0]` |
| omarchy-screensaver | replaced | `-j` | `.class` |

## `activeworkspace`

| File | Status | Form | Fields read |
| --- | --- | --- | --- |
| omarchy-hyprland-workspace-layout-toggle | replaced | `-j` | `.id`, `.tiledLayout` |

## `dispatch`

Upstream tries the new Lua dispatcher first and falls back to the classic name
(`hyprctl dispatch "$lua" >/dev/null 2>&1 || hyprctl dispatch "$@"`), except
where noted. A shim that rejects the Lua form makes the fallback run.

| File | Status | Lua form | Classic fallback |
| --- | --- | --- | --- |
| omarchy-brightness-display | patched (both removed) | `hl.dsp.dpms({ action = enable/disable })` | none |
| omarchy-capture-webcam-resize | replaced | `hl.dsp.window.resize/move({ window, x, y })` | `resizewindowpixel "exact W H,address:X"`, `movewindowpixel "exact X Y,address:X"` |
| omarchy-hyprland-focus-app | replaced | `hl.dsp.focus({ window = address })` | `focuswindow address:X` |
| omarchy-hyprland-monitor-clamshell | replaced | `hl.dsp.dpms({ action, monitor })` | none (`|| true`) |
| omarchy-hyprland-monitor-internal | replaced | `hl.dsp.dpms({ action = "enable" })` | none (`|| true`) |
| omarchy-hyprland-window-close-all | replaced | `hl.dsp.window.close({ window })`; `hl.dsp.focus({ workspace = "1" })` | none for close; `workspace 1` |
| omarchy-hyprland-window-pop | replaced | `hl.dsp.window.pin/float/resize/move/center/alter_zorder/tag` | `pin`, `togglefloating`, `tagwindow`, `resizeactive exact W H X`, `moveactive X Y X`, `centerwindow X`, `alterzorder top X` |
| omarchy-hyprland-window-tiled-fullscreen-toggle | replaced | `hl.dsp.window.fullscreen_state({ internal, client })` | `fullscreenstate 0 0\|0 2` |
| omarchy-hyprland-window-transparency-toggle | replaced | `hl.dsp.window.set_prop({ window, prop = "opaque", value = "toggle" })` | `setprop address:X opaque toggle` |
| omarchy-hyprland-window-width | replaced | `hl.dsp.window.resize({ window, x, y, relative = true })` | `resizeactive <delta> 0 address:X` |
| omarchy-launch-about | replaced | `hl.dsp.window.resize/center` | `resizewindowpixel exact W H,address:X`, `centerwindow` |
| omarchy-launch-or-focus | replaced | `hl.dsp.focus({ window = address })` | `focuswindow address:X` |
| omarchy-launch-screensaver | replaced | `hl.dsp.focus({ monitor })`; `hl.dsp.exec_cmd([[cmd]])` | `focusmonitor $1`; `exec -- bash -lc cmd` |
| omarchy-launch-signal | replaced | `hl.dsp.focus({ window = address })` | `focuswindow address:X` |
| omarchy-launch-spotify | replaced | `hl.dsp.focus({ window = address })` | `focuswindow address:X` |
| omarchy-menu-keybindings | replaced | dynamic | `"$expression"` (Lua), `exec`, `sendshortcut`, `"$arg"`, `"$dispatcher" ["$arg"]` |
| omarchy-restart-shell | replaced | `hl.dsp.exec_cmd("omarchy-launch-shell")` | none |

## Other subcommands

| Subcommand | File | Status | Usage |
| --- | --- | --- | --- |
| `reload` | omarchy-hyprland-monitor-clamshell, -internal, -internal-mirror, -monitor-watch, -toggle, -reload-guard (via `--instance`), -restart-hyprctl | replaced | re-read Hyprland config after toggle-file writes |
| `reload` | omarchy-install-preinstalls, omarchy-remove-preinstalls, omarchy-voxtype-install, omarchy-voxtype-remove | patched | bare `hyprctl reload` after setup changes |
| `switchxkblayout` | omarchy-system-lock | patched | `switchxkblayout all 0` (default layout on lock) |
| `getoption` | omarchy-capture-screenshot | replaced | `cursor:no_hardware_cursors -j`, `.int` |
| `getoption` | omarchy-hyprland-reload-guard | replaced | `--instance SIG -j getoption <option>`, `.bool` |
| `keyword` | omarchy-capture-screenshot, -screensaver, omarchy-hyprland-workspace-layout-toggle | replaced | `cursor:no_hardware_cursors`, `cursor:invisible`, `workspace N, layout:X` |
| `eval` | omarchy-capture-region (cursor move), -screenshot (hl.config), -monitor-clamshell/-scaling (hl.monitor), -reload-guard (autoreload), -workspace-layout-toggle (hl.workspace_rule), -launch-about (window rule), -screensaver (cursor), -toggle-input-device (hl.device) | replaced | Hyprland Lua configuration API |
| `eval` | omarchy-upgrade-to-quattro | setup-only, unscanned | `/usr/bin/hyprctl` in the legacy-session upgrader |
| `devices` | omarchy-hw-touchpad | replaced | `-j`, `.mice[].name` |
| `devices` | omarchy-hw-touchscreen | replaced | `-j`, `.touch[]?.name`, `.tablets[]?.name` |
| `devices` | omarchy-menu-keybindings | replaced | plain, `active keymap:` line |
| `binds` | omarchy-menu-keybindings | replaced | plain text keybind table |
| `cursorpos` | omarchy-capture-region | replaced | plain `X, Y` |
| `hyprsunset` | omarchy-toggle-nightlight | replaced | `hyprsunset temperature [K]` (query + set) |

`omarchy-theme-set` has no direct `hyprctl` call; it reaches the compositor
through `omarchy-restart-hyprctl`.

## Dispatchers used

Classic: `focuswindow`, `workspace`, `focusmonitor`, `exec`, `sendshortcut`,
`pin`, `togglefloating`, `tagwindow`, `resizeactive`, `moveactive`,
`centerwindow`, `alterzorder`, `resizewindowpixel`, `movewindowpixel`,
`setprop`, `fullscreenstate`.
Lua: `hl.dsp.focus`, `hl.dsp.window.close`, `hl.dsp.window.{pin, float,
resize, move, center, alter_zorder, tag, fullscreen_state, set_prop}`,
`hl.dsp.exec_cmd`, `hl.dsp.dpms`, plus `hl.monitor`, `hl.config`, `hl.device`
and `hl.workspace_rule` through `eval`/`keyword`.
