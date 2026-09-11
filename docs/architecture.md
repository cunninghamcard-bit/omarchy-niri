# Design

## One switch, one view

Omarchy already has the switch: `/etc/omarchy.conf` sets `OMARCHY_PATH`,
`default/bash/env-bootstrap` puts `$OMARCHY_PATH/bin` first on `PATH`, and
`/etc/sudoers.d/omarchy-dev-path` does the same for sudo. `omarchy dev link`
writes those two files for a source checkout; this extension writes the same
two files for a merged view instead:

```
mount -t overlay overlay -o lowerdir=/usr/local/lib/omarchy-niri/overlay:/var/lib/omarchy-niri/patched:/usr/share/omarchy,ro /run/omarchy/niri
```

Left wins. `overlay/` is this repository's Niri code plus complete
replacements. `patched/` holds upstream files with a small diff applied, built by
`rebuild`. `/usr/share/omarchy` is the package and stays byte-identical. The
mount is a systemd unit ordered before the display manager.

## What this removes

The previous installer copied the whole runtime into a generation, hashed all
87 managed files against a pinned Omarchy version, and journaled the switch
between generations. Every upstream change to any managed file blocked updates.
With a view there is no copy to maintain: replacements shadow whatever the
package ships, and only the patched files depend on upstream content — each
independently, so one stale patch costs one file, not the installation.

## Patch or replace

A file is patched when the diff is much smaller than the file. Files that are
mostly rewritten for Niri (the `omarchy-hyprland-*` commands, capture scripts,
Workspaces widget) are replaced outright. Changes that only existed because a
replaced file had a new name were dropped: callers keep calling
`omarchy-hyprland-focus-app` and get the Niri version through the view.

## Rebuild

`rebuild` copies each patch's target out of the package (dereferencing the
package's `/usr/bin` symlinks), applies the patch with `git apply`, swaps the
`patched/` directory and remounts. The pacman hook runs it after `omarchy`
upgrades; `update` runs it after copying a newer checkout into place. A lazy
unmount lets processes started from the old view finish while new lookups see
the rebuilt one.

## System files and uninstall

Everything written outside the view goes through a ledger: the pre-existing
file is backed up once, and the digest of what was written is recorded.
Uninstall restores the backups, deletes what had no predecessor, and copies
any file changed since we wrote it to `preserved/` rather than discarding it.
Personal Niri files (`input.kdl`, `outputs.kdl`, `bindings.kdl`,
`niri-style.json`) are created once and never tracked.

## Updates and compatibility

`omarchy update` runs, in order: snapshot, `omarchy-update-dev` (a `git pull`
of `$OMARCHY_PATH` when dev-linked — the view is not a checkout, so the overlay
replaces this with a no-op), `pacman -Syu --overwrite '/usr/share/omarchy/*'`,
per-user migrations from `$OMARCHY_PATH/migrations`, hooks, and a restart
prompt. The package upgrade replaces `/usr/share/omarchy` wholesale; our
PostTransaction hook rebuilds `patched/` and remounts. Migrations run from the
view, i.e. upstream's; the two that call `hyprctl` guard it with `|| true`.

The surface this extension owns is exactly the set of upstream files that talk
to the compositor: `hyprctl` callers in `bin/`, `Quickshell.Hyprland` users in
`shell/`, and the session entry. Each release can change it in three ways:

| Change upstream | Mechanical effect | Where it shows |
| --- | --- | --- |
| Edits a file we patch | `git apply` fails for that file; the rest of the view is unaffected | `rebuild` output, `status`, CI patch check |
| Edits a file we replace | None — the replacement shadows it; a changed calling convention is a behavior bug, not an install failure | Manual review of the upstream diff |
| Adds a compositor call in a file we do not cover | Hyprland behavior leaks into the Niri session | `tests/coverage.sh`, run weekly against upstream main |

Keybindings, menu entries and the Niri config are ported by hand; there is no
mechanism that keeps them in step with `default/hypr/bindings/*.lua`. Reviewing
that directory's diff is the release checklist.

## Distributed as an Omarchy plugin

Omarchy's plugin system installs a git repository into
`~/.config/omarchy/plugins/<id>/` and loads its QML entry points inside
`omarchy-shell`. It cannot install packages, write `/etc`, register a session or
replace `bin/` scripts — everything the compositor swap consists of. So the
plugin is the delivery channel and the prompt, not the mechanism: its one
`service` entry point runs `omarchy-niri-extension notify`, which raises a
notification when the system layer is missing or older than the checkout. The
click opens a terminal running the installer with sudo, exactly what a user
would type by hand. `omarchy plugin update` pulls the repository and the shell
reloads the service, so the update prompt follows automatically.

The bar widgets stay in the overlay rather than becoming plugin widgets: as
`omarchy.workspaces` they need no per-user `shell.json` change, and the first-
party files that need a Niri singleton (Bar.qml, idle) can only reach it through
`qs.Commons`.
