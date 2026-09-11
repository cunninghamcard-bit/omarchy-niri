pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "NiriModel.js" as Model

QtObject {
  id: root
  readonly property bool active: Quickshell.env("NIRI_SOCKET") !== ""
  property bool connected: false
  property var state: Model.emptyState()
  readonly property var workspaces: state.workspaces
  readonly property var windows: state.windows
  readonly property var keyboard: state.keyboard
  readonly property string focusedOutput: {
    var workspace = workspaces.find(function(w) { return w.is_focused })
    return workspace ? workspace.output || "" : ""
  }
  signal eventReceived(var event)

  function workspaceItems(output) { return Model.workspaceItems(state, output) }
  function focusWorkspace(id) {
    Quickshell.execDetached(["omarchy-niri", "request", JSON.stringify({ Action: { FocusWorkspace: { reference: { Id: id } } } })])
  }
  function cycleLayout() { Quickshell.execDetached(["niri", "msg", "action", "switch-layout", "next"]) }

  property Process events: Process {
    command: ["niri", "msg", "--json", "event-stream"]
    running: root.active
    stdout: SplitParser {
      onRead: function(data) {
        try {
          var event = JSON.parse(data)
          root.state = Model.reduce(root.state, event)
          root.connected = true
          root.eventReceived(event)
        } catch (error) { console.warn("Invalid niri event:", error) }
      }
    }
    onExited: {
      root.connected = false
      root.state = Model.emptyState()
      if (root.active) reconnect.restart()
    }
  }
  property Timer reconnect: Timer {
    id: reconnect
    interval: 1000
    onTriggered: root.events.running = true
  }
  property IpcHandler inspector: IpcHandler {
    target: "niri"
    function status(): string {
      return JSON.stringify({ connected: root.connected, focusedOutput: root.focusedOutput, state: root.state })
    }
  }
}
