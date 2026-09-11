# Acceptance — Omarchy Niri 0.1.0

Test date: 2026-09-11. This is an independently installable replacement layer;
its scope is the existing Omarchy 4.0.2 desktop and first-party shell services.
It is not a claim of compatibility with every third-party Hyprland plugin or
with arbitrary future Omarchy versions.

## Environment

- Apple Silicon Mac host, separate APFS clone of the Try Omarchy 0.3 test disk.
  The original Try Omarchy application and disk were retained.
- Arch Linux ARM, packaged Omarchy 4.0.2; upstream source baseline
  `346e69e1cec6c4e8924531874af6ba010a1bc99e`.
- Niri 26.04 (`8ed0da4`), Quickshell 0.3.1, GNOME portal 50.0,
  wf-recorder 0.6.0, VirGL virtual GPU, one active 816×510 output.
- Tests used a disposable account for password/lock recovery, then reinstalled
  for the original `aa` desktop account. No original account password changed.
- Final cold boot passed without the debug shell, disposable account or
  temporary test sudo rule; the installed runtime matched every payload hash.
- Guest virtual mouse/keyboard input and native screenshots provided visual
  evidence. Source checks and mocked tests are listed separately below.

## Automated and independent review

- 25 Python contract/failure tests: IPC errors, app identity, atomic state,
  invalid theme retention, lock scope, display/input validation, last-output
  protection, payload/base mismatch, update pointer/state rollback, installer
  publication rollback, edited-file preservation, safe uninstall preflight and recovery after interrupted update publication.
- 11 JavaScript assertions: workspace IDs/output filtering, focus, window
  occupancy, keyboard layout events, unknown events and reconnect snapshots.
- Payload inventory, all 87 SHA-256 checks, and Bash syntax passed.
- Two independent acceptance agents reviewed compositor/shell contracts and
  installer failure paths. Their findings were fixed and rechecked.
- CI repeats the portable checks; CI alone does not prove a graphical session.

## Runtime results

| Area | Evidence and result |
| --- | --- |
| Installation and restore | Installed and refreshed in the VM. Actual uninstall restored the Hyprland session entry and original environment. Every managed packaged source hash remained unchanged. Reinstall for `aa` launched `niri --session`; no Hyprland process was running. |
| Window management | Real windows verified half-width columns, scrolling/focus, explicit centering/resize, floating, workspace moves and application identity focus. The 69 imported bindings retain their source actions; representative runtime actions were exercised, not every possible physical key combination. |
| Shell and workspaces | Original Omarchy Quickshell bar, workspace state and active-window information run against Niri events. Normal shell restart passed. |
| Menus and tray | Real StatusNotifier/DBusMenu fixture opened, invoked its action, and dismissed using Escape and an empty-desktop click. Popup cards reuse the shell's existing layer-shell dismissal surfaces. |
| Locking | Real lock UI rejected a wrong password and accepted the disposable account's correct password. Restart while securely locked was refused. Killing the locker caused supervision to relaunch and reacquire the lock. |
| Screenshot | Native full-display screenshot saved successfully. Region capture uses slurp/grim, focused-window capture uses Niri; native Niri screenshot selection replaces Hyprland temporary capture submaps. |
| Recording | A real H.264 816×510 MP4 with AAC audio was recorded and finalized; recording status transitioned on/off and owned audio mix modules were cleaned up. This tests virtual audio transport, not a physical microphone. |
| Screensaver | Real full-display Foot screensaver appeared and exited on virtual keyboard input. |
| Clipboard | wl-copy/wl-paste round trip passed. Original shell clipboard UI is retained. |
| Output scale | Applied 1.25 scale, verified Niri's reported scale, and returned to 1.0. Last-output safety also has a contract test. |
| Nightlight | The virtual output lacks gamma adjustment. The adapter reports unsupported/disabled, stops the unsuccessful backend, and does not falsely show the feature as active. |
| Screen sharing | Chromium 152 used the real GNOME portal and Entire Screen chooser. Five WebRTC video frames reached a canvas at 816×510, with 256 distinct sampled color values; the stream was then stopped. |
| Theme and monitor UI | A full theme switch regenerated the Niri accent border; shell IPC remained live and monitor state reported the active output. Original theme was restored. |
| Webcam window controls | A synthetic WebcamOverlay window verified medium/smaller/larger geometry. Physical camera capture is outside this VM. |

## Hardware boundaries

This VM has one active virtual output and no physical lid, touchpad, touchscreen,
camera, battery, Bluetooth radio, or usable gamma control. Multi-output mirroring,
physical hotplug/lid behavior, camera capture, hardware brightness, fingerprint
PAM, suspend/resume and GPU recording therefore need a target hardware check.
Adapters and validation exist; those device-level results are not claimed.

The standalone GStreamer probe could not negotiate Niri's DMA-BUF stream
(`no more input formats`), even though the Chromium WebRTC acceptance passed.
This is a client compatibility limit, not a blanket failure of screen sharing.
The Niri maintainer discusses the pipewire-gstreamer limitation in
[the upstream issue comments](https://github.com/niri-wm/niri/issues/3145).

The default recorder uses CPU encoding. Optional gpu-screen-recorder is not a
requirement for installation and was not available from the tested ARM mirror.
The extension does not substitute a different shell to avoid these checks.

## Reproduction

Run portable checks from the checkout:

```sh
python3 -m unittest discover -s tests -v
node tests/niri-model-test.cjs
python3 tests/check_payload.py
```

Inside a disposable graphical Niri login, run
`python3 tests/manual/window_smoke.py`. It opens and closes three temporary Foot
windows. `tests/manual/tray_fixture.py` publishes a local test tray menu.
`tests/manual/browser_screen_share.py` serves a local-only page: open it in
Chromium, choose Entire Screen, and inspect `~/niri-browser-capture-result.json`.
The separate `portal_gstreamer_probe.py` diagnoses the known GStreamer client
limitation; it requires GObject/GStreamer and is not the release acceptance gate.
These are acceptance fixtures, not startup services or production dependencies.

Selected logs, the browser frame result and UI captures are in [evidence/](evidence/).

The screen-sharing fixture follows the public
[ScreenCast portal lifecycle](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html).
VM credentials, machine images, private sockets and debug consoles are not
included in this repository.
