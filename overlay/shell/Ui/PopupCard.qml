import QtQuick
import qs.Commons

// Reuse the existing layer-shell dismissal surfaces so empty-desktop clicks
// and clicks on another output close menus consistently.
KeyboardPanel {
  id: root
  property string triggerMode: "click"
  property color borderColor: Color.popups.border
  clickDismissal: triggerMode === "click"
  focusTarget: clickDismissal ? escapeCatcher : null
  borderSpec: Border.localOrSurfaceSpec("popups", "border", borderColor,
    Color.popups.border, Math.max(1, Style.space(2)))
  Item {
    id: escapeCatcher
    focus: true
    Keys.onEscapePressed: root.close()
  }
}
