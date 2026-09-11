# Maintenance boundary

The extension has one Niri session and uses Omarchy's existing Quickshell desktop.
It does not carry a Hyprland backend or its own distribution package set.

## Source and installation

`payload/` holds Niri-specific code and complete replacements. `patches/` holds
standard unified diffs for small changes to large Omarchy files. A patch is used
only when it is substantially smaller than the file and has one supported base.
Files with distinct official/ARM source variants remain complete replacements.

`manifest.json` maps each installed path to accepted base hashes and its final
SHA-256. `patch: true` selects `patches/<path>.patch`; otherwise the source is
`payload/<path>`. No custom patch interpreter or runtime dispatch layer is needed.

Installation follows one path:

1. Check the packaged Omarchy source against the manifest.
2. Copy it into a private generation, materializing `/usr/bin` command symlinks.
3. Copy replacements and apply standard patches with `git apply`, limited to
   their declared paths. Verify every resulting managed file's exact hash.
4. Validate Niri configuration and configure the session, recording original
   managed files for restoration.

The packaged `/usr/share/omarchy` and `/usr/bin/omarchy-*` files stay intact.
`/etc/omarchy.conf` selects the private runtime. UWSM launches the Niri session;
Quickshell reads compositor state from Niri's socket and event stream.

## Updates and restoration

`sudo python3 manage.py refresh` from a newer checkout publishes that extension
and a newly assembled runtime. The pacman hook invokes the installed manager to
reapply it to updated Omarchy packages. These are the same refresh operation;
the hook does not fetch a newer Git checkout.

Refresh validates the user's existing includes before activation. A publication
journal records previous/new generations. Both ordinary failures and a later
command recovering from interruption use the same recovery function. The command
wrapper can find the previous manager during the directory-rename gap.

Managed changes share one backup/link/write implementation. Uninstall archives
subsequent edits before restoring originals. Ownership checks prevent unrelated
files from being removed. Old generations remain archived; dependencies and user
documents are not deleted. The [ablation experiments](ablation.md) demonstrate
why rollback, conflict preflight and output validation are retained.

## Runtime scope

Simple legacy `omarchy-hyprland-*` command names remain because Omarchy calls
them. Their implementations invoke Niri; replacing these short scripts with a
registry would add another layer without simplifying their behavior.

Niri's scrolling layout is preserved. Hyprland Lua/submaps are not emulated:
configuration is KDL and screenshot interaction is native to Niri. Shared shell
UI remains upstream code plus the small patches. Full desktop/physical-device
coverage is described separately in [acceptance](acceptance.md).
