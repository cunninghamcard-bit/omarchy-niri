# Maintenance boundary

The extension replaces the compositor once. It has no Hyprland/Niri backend
switch and carries no alternate distribution package set. The original package
installation remains the source for unmodified Omarchy files.

`payload/` contains the adapted Omarchy files. `manifest.json` records their
payload SHA-256 and accepted source SHA-256 values. The alternate source hashes
were measured on Try Omarchy's packaged 4.0.2 ARM runtime; its packaged scripts
are symlinks into `/usr/bin`, and its idle service differs from the Git tag.

Installation materializes packaged command links into an immutable private
runtime, validates Niri configuration, then selects the new runtime through
`/etc/omarchy.conf`. Login uses UWSM and the packaged Niri session. The Omarchy
Quickshell framework, plugins and UI remain in that runtime, with Niri state
provided through the official event stream and JSON socket.

An upgrade creates a new generation. A publication journal lets the next
management command recover if a process dies between manager and runtime
publication; the command wrapper can find the previous manager during that gap. Unknown source changes fail before pointer
activation. User includes are validated against the new defaults. Existing
processes should be restarted by logging out and in. Old generations remain
available until uninstall; this intentionally trades local disk space for
recoverability.

The update package hook is scoped to Omarchy. It disables the two packaged
Hyprland reload-guard hooks through `/etc/pacman.d/hooks` overrides while this
extension is installed. Uninstall restores those overrides as well as the old
session, environment, sudo path and owned user configuration.

The installer records each original file and intended replacement hash before
writing it. Uninstall first archives later edits, then restores the original.
It retains dependencies and archived generations; it never removes applications
or user documents. Tests exercise interrupted writes and conflict detection.

Niri's scrolling model is deliberately preserved. Hyprland-specific temporary
capture submaps and Lua configuration files are not emulated; Niri supplies its
own screenshot interaction and KDL configuration. Legacy command names that
Omarchy itself calls delegate directly to Niri implementations.
