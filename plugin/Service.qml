import QtQuick
import Quickshell.Io

// The compositor swap needs root and runs in a terminal; the shell's part is to
// say when setup or an update is due. All of that logic lives in the installer.
Item {
  readonly property string extension: decodeURIComponent(
    String(Qt.resolvedUrl("../omarchy-niri-extension")).replace(/^file:\/\//, ""))

  Process {
    running: true
    command: ["bash", extension, "notify"]
  }
}
