# Design

## One switch, one runtime

Omarchy already has the switch: `/etc/omarchy.conf` sets `OMARCHY_PATH`,
`default/bash/env-bootstrap` puts `$OMARCHY_PATH/bin` first on `PATH`, and
`/etc/sudoers.d/omarchy-dev-path` does the same for sudo. `omarchy dev link`
writes those two files for a source checkout; this extension writes the same
two files for a private runtime instead:

```
/var/lib/omarchy-niri/current -> /var/lib/omarchy-niri/runtimes/<release-id>
```

`compat.prepare()` copies the installed Omarchy tree into staging, materializes
package symlinks, applies every patch, installs Niri replacements, and scans the
final tree for uncovered compositor calls. The staging directory is renamed
into `runtimes/` only after all checks pass. One atomic replacement of `current`
publishes the runtime used by new sessions.

## What this removes

The previous installer tracked a large managed-file set and the overlayfs design
added a second mutable layer. The current design has one complete candidate
tree and one publication pointer. It costs a copy per update, but keeps the
input visible, makes validation deterministic, and avoids mutating overlayfs
lower layers while they are mounted.

## Patch or replace

A file is patched when the diff is much smaller than the file. The screensaver
and idle service have different Hyprland recovery logic in Try Omarchy ARM, so
they use one Niri replacement with two explicitly reviewed source hashes. The
ARM differences are captured in `tests/fixtures/try-omarchy-cursor-idle.patch`. Files that are
mostly rewritten for Niri (the `omarchy-hyprland-*` commands, capture scripts,
Workspaces widget) are replaced outright. Changes that only existed because a
replaced file had a new name were dropped: callers keep calling
`omarchy-hyprland-focus-app` and get the Niri implementation from the private runtime.

## Prepare and publish

`update` and the pacman post-transaction hook call the same preparation path.
The candidate gets a unique runtime ID and is validated before `current`
changes. A failed candidate writes `upgrade-failed.txt` and leaves the prior
pointer and runtime intact. A lock prevents concurrent operations; retired
runtimes remain available for recovery.

## System files and uninstall

System files written outside the runtime go through a ledger: the pre-existing
file is backed up once, and the digest of what was written is recorded.
Uninstall restores the backups, deletes what had no predecessor, and copies
any file changed since we wrote it to `preserved/` rather than discarding it.
Installation replaces the Niri entry config after backing it up; existing personal
input, output and binding overrides are left untouched. Files created by installation
are removed on uninstall; subsequent edits are preserved in the uninstall archive.

## Updates and compatibility

After the package hook succeeds, the `omarchy update` command reloads the
published runtime path before running migrations and post-update hooks. A
compatibility failure stops those steps instead of running migrations from the
old source tree against the new package.

The package upgrade still owns `/usr/share/omarchy`. Its post-transaction hook
prepares a candidate against that new tree; it never edits the active runtime.
If compatibility fails, the hook records the concrete file or call that needs
review. External Niri and Qt packages remain outside this snapshot.

The surface this extension owns is exactly the set of upstream files that talk
to the compositor: `hyprctl` callers in `bin/`, `Quickshell.Hyprland` users in
`shell/`, and the session entry. Each release can change it in three ways:

| Change upstream | Mechanical effect | Where it shows |
| --- | --- | --- |
| Edits a file we patch | The patch must still apply, and the final file is scanned for remaining compositor calls | prepare output, `status`, CI compatibility check |
| Edits a file we replace | The candidate still builds with the reviewed replacement; the drift is recorded in the release report | `status`, one desktop notification, `tools/review-drift` |
| Adds a compositor call in a file we do not cover | Candidate preparation fails before publication | `compat.prepare`, run on the pinned base and weekly upstream main |

A replacement whose upstream file disappeared still fails preparation: the
interface it adapts has changed shape, which needs a port, not a warning.

Keybindings, menu entries and the Niri config are ported by hand. Hash changes
and added or removed files in `default/hypr/bindings/*.lua` are recorded as
drift in the same report, so new Omarchy shortcuts cannot silently diverge from
the Niri defaults. Review that diff and preserve the eight user-selected
directional bindings.

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

The bar widgets stay in the runtime rather than becoming plugin widgets: as
`omarchy.workspaces` they need no per-user `shell.json` change, and the first-
party files that need a Niri singleton (Bar.qml, idle) can only reach it through
`qs.Commons`.

## Following upstream

Every push checks the reviewed base. A weekly job also prepares against Omarchy
main; drift alone passes that job, while its artifact still records the drift
list and the full diff from the reviewed commit. Hard failures — a rejected
patch, a disappeared replacement, a new compositor call — keep it red.
Maintainers review the changed source with `tools/review-drift <checkout>`,
which prints the upstream diff and the accepted hashes, and accept a hash only
after that review with `tools/review-drift --accept`. Update the affected
adapter or patch when the change is more than cosmetic; accepting a hash is not
an adaptation. Run the portable checks plus an Omarchy VM session before
releasing a new plugin version.

These checks detect known source interfaces; they are not proof of arbitrary
future behavioral compatibility. Niri and Quickshell/Qt binaries are still
updated by the package manager, so a binary API change also needs runtime testing.
