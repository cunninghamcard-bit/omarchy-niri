# Upgrade validation

This document records the 0.3.1 complete-runtime manager acceptance on 2026-09-12.
It is separate from [the historical graphical acceptance record](acceptance.md).
The current design validates an entire candidate runtime, then atomically
publishes `state/current`; a failed candidate must leave the previous runtime
selected.

## Portable evidence

The [portable log](evidence/upgrade-0.3.1-portable.log) records:

- 49 passing Python tests, including rejected upgrades, source-symlink isolation,
  partial configuration rollback, interrupted journal creation, concurrent writers,
  legacy migration, edited-file preservation, and update-script handoff.
- 11 JavaScript model assertions and the plugin/CLI smoke check.
- Candidate preparation from the reviewed official Omarchy base, applying 26
  patches and 45 full replacements. The exported Try Omarchy ARM tree also passed
  preparation after explicit review of its screensaver, idle and shortcut variants.

These checks do not represent a graphical login or a hardware test.

The repository's current CI repeats candidate preparation against the pinned
Omarchy commit. A source hash change, rejected patch, or uncovered compositor
interface fails before `current` can change.

## Ablation evidence

[The ablation report](evidence/upgrade-0.3.1-ablation.json) records one passing
focused baseline with 29 tests and three
controlled removals, each failing its targeted contract:

1. Removing replacement-hash rejection accepted a changed reviewed file.
2. Removing the final composed-runtime scanner accepted injected Hyprland
   interfaces.
3. Removing activation recovery left partial configuration changes after a
   failed activation.

The respective altered runs failed 1/16, 3/16, and 3/13 checks. They ran in
temporary source copies before the final journal-initialization tests were added;
the manager tests also received the edited-file case during the experiment.
The final unmodified suite above is the release verification.

These are safety-guard checks, not a claim that every future Omarchy change is
automatically adapted.

## VM acceptance and hardware limits

The [VM log](evidence/upgrade-0.3.1-vm.log) and
[cold-boot screenshot](evidence/upgrade-0.3.1-desktop.png) come from a disposable
clone of Try Omarchy ARM with Niri 26.04. The original disk was not modified.

| Check | Result |
| --- | --- |
| Migrate the old 0.1 installation to 0.3.1 | Passed, original uninstall backups retained |
| Rebuild against the installed ARM source | Passed, Niri config validated before publication |
| Inject a changed upstream screensaver | Rejected, current runtime unchanged |
| Uninstall | Passed, original Omarchy environment and session entry restored |
| Fresh install and normal cold boot | Passed, Niri and Quickshell running |
| Shell ping, idle status and output IPC | Passed |
| Native desktop screenshot | Omarchy bar and background visible |

The VM already had the required packages, so install used `--skip-packages`.
The package hook's rebuild command was exercised directly; a real network-driven
pacman upgrade was not performed. The final journal-initialization recovery fix
was validated by portable failure tests after this graphical run.
The earlier broad shell/lock/portal/recording checks in [acceptance.md](acceptance.md)
remain historical evidence, not a new full desktop parity claim.

This VM had one virtual output and did not cover physical monitor
hotplug, lid handling, hardware brightness, camera capture, suspend/resume, or
GPU recording. Those remain target-hardware checks.

## Following Omarchy

The compatibility manifest is a reviewed contract for a particular Omarchy
source tree. When Omarchy changes, maintainers inspect the upstream diff,
update the affected replacement or patch, rerun pinned and scheduled upstream
checks, and only then publish a new plugin version. Updating a hash by itself
does not adapt behavior. The runtime snapshot covers Omarchy's scripts and
shell files; Niri, Qt, and other binaries remain host packages and can require
separate runtime validation. No finite check can guarantee compatibility with
an arbitrary future Omarchy version.
