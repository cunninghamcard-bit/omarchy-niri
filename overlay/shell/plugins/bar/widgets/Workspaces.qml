import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"

  readonly property string outputName: root.QsWindow.window && root.QsWindow.window.screen
    ? root.QsWindow.window.screen.name : Niri.focusedOutput
  readonly property var displayWorkspaces: Niri.workspaceItems(outputName)

  function focusWorkspace(id) { Niri.focusWorkspace(id) }

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)

  implicitWidth: grid.implicitWidth + trailingGap
  implicitHeight: grid.implicitHeight

  GridLayout {
    id: grid
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    columns: root.vertical ? 1 : root.displayWorkspaces.length
    columnSpacing: root.vertical ? 0 : Style.space(1)
    rowSpacing: root.vertical ? Style.space(2) : 0

    Repeater {
      model: root.displayWorkspaces

      WidgetButton {
        required property var modelData

        readonly property var workspace: modelData
        readonly property bool occupied: workspace !== null && workspace.occupied
        readonly property bool focused: workspace !== null && workspace.is_focused

        bar: root.bar
        text: focused ? "\uDB85\uDCFB" : String(workspace.name || workspace.idx)
        opacity: occupied || focused ? 1 : 0.5
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical ? root.barSize : Style.space(20)
        fixedHeight: root.barSize
        onPressed: function() { root.focusWorkspace(workspace.id) }
      }
    }
  }
}
