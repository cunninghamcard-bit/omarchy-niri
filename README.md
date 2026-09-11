# Omarchy Niri

将已有 Omarchy 的 Hyprland 会话替换为 Niri，保留原版 Quickshell 外壳、
常用快捷键，以及 Niri 的滚动布局和留白。直接安装，无需重装或制作镜像。

A Niri replacement for an existing Omarchy desktop. The bar, menus, notifications,
clipboard, themes and desktop services stay with Omarchy. This is an independent
extension, not an upstream Omarchy plugin or a separate distribution.

![Omarchy shell running on Niri](docs/evidence/final-desktop.png)

## Install

Requires **Omarchy 4.0.2** and **Niri 26.04+**. The installer installs dependencies,
checks the supported Omarchy files, and keeps the packaged installation intact.
Unknown upstream changes stop the installation or update.

```sh
git clone https://github.com/cunninghamcard-bit/omarchy-niri.git
cd omarchy-niri
./install.sh
```

Run as your desktop user; sudo handles system changes. From a root shell, use
`./install.sh --user YOUR_DESKTOP_USER`. Log out and select **Omarchy (Niri)**,
or reboot. The remembered Omarchy session also starts Niri.

## Shortcuts and configuration

Omarchy key positions remain the baseline. Only eight directional combinations
are adapted from [2725244134/dotfiles](https://github.com/2725244134/dotfiles/tree/4a96e1e36f4e19fd8d24d04ace95fa832a01c16e/niri/.config/niri):

| Keys | Action |
| --- | --- |
| Super + Left / Right | Focus the next column; at the end, continue to the adjacent monitor |
| Super + Up / Down | Focus the workspace above / below |
| Super + Ctrl + Left / Right | Move the current column left / right |
| Super + Ctrl + Up / Down | Move the column to the workspace above / below |

A column can contain several windows. No extra personal monitor-switch keys or
selectable binding profiles are added. Columns start at half width and keep
empty space; only explicit sizing or maximization changes their width.

`Super+W` closes, `Super+T` toggles floating, `Super+F` toggles fullscreen,
`Super+Alt+F` maximizes a column, and `Super+Shift+F` opens the file manager.
`Super+K` shows shortcuts. Personal settings live in `~/.config/niri/input.kdl`,
`outputs.kdl`, and `bindings.kdl`; updates preserve these files. Themes generate
Niri borders; radius and gaps live in `~/.config/omarchy/niri-style.json`.

Hyprland-specific layouts are not identical: tabbed columns handle grouping,
and pop-window toggles floating without pinning. Universal Super+C/V/X
forwarding, scratchpads and pseudo-tiling are not implemented. Normal application
clipboard shortcuts remain available. See [acceptance and limits](docs/acceptance.md).

## Update or restore

To update the extension itself, run from this checkout:

```sh
git pull --ff-only
sudo python3 manage.py refresh
```

The pacman hook reapplies the installed extension after an Omarchy package update;
it does not download extension updates. Refresh validates a new runtime before
switching it. Log out and in afterward.

```sh
omarchy-niri-extension status
sudo omarchy-niri-extension uninstall
```

Uninstall restores the original session and managed configuration. Reboot afterward.
Subsequent edits are archived; installed packages and user documents are retained.

## Code and verification

- `payload/`: new Niri code and complete replacements.
- `patches/`: small standard diffs against existing Omarchy files.
- `manifest.json`: supported source hashes and exact installed-file hashes.
- `manage.py`: assemble, validate, activate and restore the runtime.

Small upstream changes are stored as patches instead of copies of entire files.
Short compatibility commands stay as simple scripts. There is no runtime backend
selector or custom patch language. See the [design](docs/architecture.md) and
[controlled simplification experiments](docs/ablation.md).

```sh
python3 -m unittest discover -s tests -v
node tests/niri-model-test.cjs
python3 tests/check_payload.py --base /path/to/clean/omarchy-4.0.2
python3 tests/ablation.py --base /path/to/clean/omarchy-4.0.2
```

CI checks exact reconstruction and runs the ablation matrix. Desktop and hardware
validation have separate evidence in the [acceptance report](docs/acceptance.md).

## Credits

Omarchy and its Quickshell UI: David Heinemeier Hansson and contributors (MIT).
Niri: niri-wm contributors. Directional keybindings: 2725244134/dotfiles.
