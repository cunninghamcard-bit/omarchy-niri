import QtQuick
import Quickshell.Io

// The compositor swap needs root and runs in a terminal; the shell's part is to
// refresh the user-owned Niri defaults without root and to say when the
// one-time setup or a runtime update is due. All of that logic lives in the
// installer, which this service invokes unprivileged.
Item {
  readonly property string extension: decodeURIComponent(
    String(Qt.resolvedUrl("../omarchy-niri-extension")).replace(/^file:\/\//, ""))

  Process {
    running: true
    command: ["bash", "-c", "\"$0\" sync; \"$0\" notify", extension]
  }
}
