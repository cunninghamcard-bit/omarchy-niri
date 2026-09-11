# Omarchy Niri

将已有 Omarchy 的 Hyprland 会话替换为 Niri，保留原版 Quickshell 外壳、
原版常用快捷键、少量方向键调整和 Niri 原生滚动留白。独立扩展，无需重装或制作镜像。

A one-way Niri replacement for Omarchy, retaining Omarchy's Quickshell desktop.
Install this extension on an existing Omarchy machine. No custom ISO or separate
Linux distribution is required. This is a managed replacement layer, not an
upstream Omarchy shell `manifest.json` plugin: installing a compositor requires
system packages, a login session, and changes to compositor-dependent services.

The repository contains only the replacement files, installer, and tests. The
installer assembles a private runtime from the packaged Omarchy installation;
it does not overwrite `/usr/share/omarchy` or `/usr/bin/omarchy-*`.

![Omarchy shell running on Niri](docs/evidence/final-desktop.png)

## Install

Requires an existing Omarchy 4.0.2 desktop and Niri 26.04 or newer. The manifest
pins the expected upstream files, including the tested Try Omarchy ARM variant.
An unknown upstream change is rejected before switching the active runtime.

```sh
git clone https://github.com/cunninghamcard-bit/omarchy-niri.git
cd omarchy-niri
./install.sh
```

Run as the desktop user. Sudo is used for packages, session configuration and
root-owned runtime generations. When invoked from a root shell, pass
`./install.sh --user YOUR_DESKTOP_USER`.

Log out and select **Omarchy (Niri)**, or reboot. Both the remembered Omarchy
session and the explicit Niri session launch Niri after installation.

## What stays

The original Omarchy bar, menus, notifications, clipboard, wallpaper, theme
system, audio, network, Bluetooth, lock screen, idle handling, and other shell
services remain. Compositor state and operations use Niri IPC. No Hyprland
backend is kept in the replacement runtime paths. Existing `omarchy-hyprland-*`
command names used by Omarchy scripts are thin Niri aliases.

Omarchy key positions remain the baseline. Only eight directional combinations
are adapted from [2725244134/dotfiles](https://github.com/2725244134/dotfiles/tree/4a96e1e36f4e19fd8d24d04ace95fa832a01c16e/niri/.config/niri):

| Keys | Action |
| --- | --- |
| Super + Left / Right | Focus the adjacent column; at the end, focus the adjacent monitor |
| Super + Up / Down | Focus the workspace above / below |
| Super + Ctrl + Left / Right | Move the current column left / right |
| Super + Ctrl + Up / Down | Move the current column to the workspace above / below |

Horizontal focus uses Niri's `focus-column-or-monitor-left/right`, so monitor
focus does not require a separate shortcut. Moving a column is a different
action from focusing another monitor. A column may contain several windows.
No Noctalia, application choices, autostart or device settings are imported.

Other common bindings use Omarchy positions: `Super+W` closes, `Super+T`
toggles floating, `Super+F` toggles fullscreen, `Super+Alt+F` maximizes a column,
and `Super+Shift+F` opens the file manager. `Super+1..0` selects a workspace;
`Super+Shift+1..0` moves a window there. `Super+Ctrl+1..9` opens bar panels.
`Super+Tab` changes workspace. Resize keys use Omarchy's pixel steps, not the
personal width/height presets. Hyprland-specific layouts/grouping do not have
identical Niri semantics: tabbed columns provide the grouping/layout toggle,
and the pop-window adapter toggles floating without Hyprland pinning. Universal
Super+C/V/X forwarding, scratchpads and pseudo-tiling are not provided by this
binding translation; normal application clipboard shortcuts remain available.

Niri keeps its scrolling layout and empty space. Columns start at half width
and are never automatically stretched to fill an output. Only explicit sizing
or maximization actions change that behavior.

## Configure

Personal overrides live in `~/.config/niri/input.kdl`, `outputs.kdl`, and
`bindings.kdl`. `Super+K` opens the shortcut overlay; `Super+/` keeps Omarchy's monitor
scaling action. The Omarchy setup menu
opens these Niri files. Radius and gaps are in
`~/.config/omarchy/niri-style.json`; themes update Niri borders automatically.

Screen capture uses Niri's native screenshot actions and slurp/grim for regions.
Screen recording uses wf-recorder with CPU encoding, with optional desktop and
microphone mixing. Portal sharing for browsers/meeting apps uses Niri and
xdg-desktop-portal-gnome. Advanced recording can opt into gpu-screen-recorder
with `OMARCHY_SCREENRECORD_USE_PORTAL=true` after installing that optional tool.
Niri's native screenshot UI replaces Hyprland's temporary capture keymap.

Nightlight uses Gammastep. Mirroring uses wl-mirror. Gamma adjustment, physical
input devices, camera availability, suspend, and GPU encoding depend on the
host hardware; see [the acceptance report](docs/acceptance.md) for what was tested.
Chromium screen sharing passed; the tested GStreamer client could not negotiate
Niri DMA-BUF streams. The default wf-recorder path works independently.

## Update

```sh
git pull --ff-only
sudo python3 manage.py refresh
```

Refresh builds and validates a new generation, then switches the pointer. Log
out and back in to load it. User overrides are not rewritten. A pacman hook
attempts the same refresh after an Omarchy package upgrade. If upstream changes
a managed file unexpectedly, the extension retains the previous generation and
records a failed-refresh status instead of guessing how to merge it.

```sh
omarchy-niri-extension status
```

This is a versioned extension: compatibility with arbitrary future Omarchy
releases is not promised. Porting consists of reviewing changed upstream files,
updating the small payload and its hashes, and rerunning acceptance tests.

## Restore

```sh
sudo omarchy-niri-extension uninstall
```

Reboot to restore the original Omarchy session. The installer restores original
managed configuration files. Subsequent edits are first archived alongside the
backups under `/var/lib/omarchy-niri-uninstalled-*`; added packages are retained.
The extension does not delete applications or user documents.

## Verification

```sh
python3 -m unittest discover -s tests -v
node tests/niri-model-test.cjs
python3 tests/check_payload.py
```

These tests run on macOS and Linux and check adapters and installer failure
paths. They do not replace real Wayland acceptance. Runtime evidence and limits
are documented in `docs/acceptance.md`.

## Credits

Omarchy and its Quickshell UI: David Heinemeier Hansson and contributors (MIT).
Niri: niri-wm contributors. Window-management keybindings: 2725244134/dotfiles.
This project is an independent extension and is not an official Omarchy release.
