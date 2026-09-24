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

## Now served by the shim

The shim (`overlay/bin/hyprctl` → `overlay/default/niri/hyprctl.py`) serves
`monitors` (plain and `all`, with `id`, `name`, `make`, `model`, `width`,
`height`, `refreshRate`, `x`, `y`, `activeWorkspace`, `scale`, `transform`,
`focused`, `vrr`, `disabled`, `mirrorOf` — physical mode dimensions and a
per-output `idx` as the workspace id), `clients` (`address` as `0x<id>`,
`class` from `app_id`, `title`, `pid`, `floating`, `workspace`, `size`),
`activewindow` (JSON and the plain `pid:` block), `activeworkspace`, `reload`,
`switchxkblayout all <n>`, and `dispatch focuswindow|workspace|focusmonitor`
plus the Lua `hl.dsp.focus` and `hl.dsp.window.close` forms. Not provided:
`dpmsStatus`, `solitaryBlockedBy`, `hidden`, `at`, `monitor`, `pinned`,
`fullscreen*`, `initialTitle`, `focusHistoryID`, `inhibitingIdle`, `tags`,
`availableModes`, `initialClass`/`initialTitle` distinction, and Niri has no
`devices`, `binds`, `getoption`, `keyword`, `eval`, `cursorpos` or compositor
`exec` equivalent at all. That is what keeps the files below replaced.

Dropped — the unmodified upstream file now runs against the shim:

| File | Was | Why it works |
| --- | --- | --- |
| bin/omarchy-hyprland-monitor-focused | replacement | `monitors -j` focused `name`, identical output |
| bin/omarchy-hyprland-monitor-laptop | replacement | `monitors all -j` internal `name` |
| bin/omarchy-hyprland-monitor-external-active | replacement | `monitors all -j` `name`/`disabled` |
| bin/omarchy-monitor-state | replacement | same eight-line output from `monitors all -j`; brightness and scale still come from the patched brightness-display and the replaced monitor-scaling |
| bin/omarchy-launch-or-focus | replacement | `clients -j` class/title match plus `dispatch focuswindow` (Lua and classic) |
| bin/omarchy-launch-signal | replacement | same pattern as launch-or-focus |
| bin/omarchy-launch-spotify | replacement | same pattern as launch-or-focus |
| bin/omarchy-cmd-terminal-cwd | patch | plain `activewindow` carries the `pid:` line; with no focused window it degrades to `$HOME` like the patched guard did |
| bin/omarchy-install-preinstalls | patch | `hyprctl reload` → `LoadConfigFile` |
| bin/omarchy-remove-preinstalls | patch | `hyprctl reload` → `LoadConfigFile` |
| bin/omarchy-launch-shell | patch | `-j monitors` exit status is the compositor-liveness check |
| bin/omarchy-system-lock | patch | `switchxkblayout all 0` → `SwitchLayout` index 0 |
| bin/omarchy-voxtype-install | patch | `hyprctl reload` → `LoadConfigFile` |
| bin/omarchy-voxtype-remove | patch | `hyprctl reload` → `LoadConfigFile` |
| bin/omarchy-windows-vm | patch | `monitors -j` focused `scale` |

Kept — the Niri version does something different on purpose, or the calls
cannot be served:

| File | Kind | Reason |
| --- | --- | --- |
| bin/omarchy-capture-region | replacement | `cursorpos` and eval cursor moves have no Niri IPC equivalent |
| bin/omarchy-capture-screenrecording | replacement | rewritten capture pipeline over Niri IPC |
| bin/omarchy-capture-screenshot | replacement | `getoption`/`keyword`/`eval` cursor toggles are Hyprland config |
| bin/omarchy-capture-webcam-resize | replacement | floating window `size`/`monitor` geometry and pixel move/resize dispatchers |
| bin/omarchy-hw-touchpad, -touchscreen | replacement | `devices` has no Niri IPC equivalent |
| bin/omarchy-hyprland-focus-app | replacement | matches agent terminals by `initialClass`/`initialTitle`, which Niri does not expose |
| bin/omarchy-hyprland-monitor-clamshell | replacement | config-file output state plus `Output` actions instead of `eval hl.monitor` |
| bin/omarchy-hyprland-monitor-focused-apple | replacement | deliberately broadened to any Apple make on the focused output; upstream requires specific Studio/Pro Display models |
| bin/omarchy-hyprland-monitor-internal | replacement | Lua `dpms` and config toggle files |
| bin/omarchy-hyprland-monitor-internal-mirror | replacement | wl-mirror service instead of Hyprland output mirroring |
| bin/omarchy-hyprland-monitor-modeless | replacement | deliberately repurposed to an all-disconnected check; Hyprland's 0x0 partial-EDID state does not exist in Niri |
| bin/omarchy-hyprland-monitor-scaling | replacement | mode/scale changes go through Niri config, not `eval hl.monitor` |
| bin/omarchy-hyprland-monitor-watch | replacement | Niri handles hotplug itself; the watcher is a no-op |
| bin/omarchy-hyprland-reload-guard | replacement | guards Hyprland autoreload across instances via `getoption`/`eval` |
| bin/omarchy-hyprland-session-locked | replacement | infers ext-session-lock from `solitaryBlockedBy`; Niri exposes no lock state |
| bin/omarchy-hyprland-toggle | replacement | Hyprland Lua flag files vs Niri flag semantics |
| bin/omarchy-hyprland-window-close-all | replacement | closes via `Windows`/`CloseWindow` without upstream's workspace-1 jump |
| bin/omarchy-hyprland-window-pop | replacement | toggle floating without pinning (no Niri pin) |
| bin/omarchy-hyprland-window-tiled-fullscreen-toggle | replacement | single windowed-fullscreen action; no internal/client split |
| bin/omarchy-hyprland-window-transparency-toggle | replacement | `toggle-window-rule-opacity`, no `setprop` |
| bin/omarchy-hyprland-window-width | replacement | direct `set-window-width` persistence, not probe-resize |
| bin/omarchy-hyprland-workspace-layout-toggle | replacement | tabbed columns; Hyprland workspace layouts do not apply |
| bin/omarchy-launch-about | replacement | sized by eval window rules and pixel resize of a floating window |
| bin/omarchy-launch-screensaver | replacement | needs the Hyprland event socket and compositor `exec`; Niri version moves windows by id |
| bin/omarchy-menu-keybindings | replacement | parses the Niri config; no `binds`/`devices`/`sendshortcut` IPC |
| bin/omarchy-refresh-hyprsunset, -restart-hyprsunset | replacement | gammastep nightlight instead of `hyprctl hyprsunset` |
| bin/omarchy-restart-hyprctl | replacement | regenerates the Niri theme include before reloading |
| bin/omarchy-restart-shell | replacement | lock-aware supervised restart; upstream compositor-spawns the shell |
| bin/omarchy-screensaver | replacement | focused-window check; cursor invisibility has no Niri IPC |
| bin/omarchy-toggle-input-device | replacement | input toggles are config-file state |
| bin/omarchy-toggle-nightlight | replacement | gammastep instead of hyprsunset |
| bin/omarchy-update-dev | replacement | the private runtime is not a git checkout |
| bin/omarchy-bar-text-color | patch | crops the wallpaper in logical pixels; the shim reports physical mode dimensions |
| bin/omarchy-brightness-display | patch | Lua `dpms` and per-monitor `dpmsStatus` semantics map to `power-on/off-monitors` |
| bin/omarchy-debug-idle | patch | idle inhibitors, tags and screensaver clients are Hyprland state |
| bin/omarchy-launch-browser | patch | guards on `HYPRLAND_INSTANCE_SIGNATURE`, an environment variable the shim cannot set |
| bin/omarchy-menu-herdr-keybindings, -tmux-keybindings | patch | menu height must be logical pixels for the Quickshell window |
| bin/omarchy-update, -update-restart | patch | runtime publication and `pgrep niri` reboot prompt, not hyprctl |
| shell/* replacements and patches | — | Quickshell/Niri QML ports, outside the shim's scope |
