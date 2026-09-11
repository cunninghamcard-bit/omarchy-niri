function emptyState() {
  return { workspaces: [], windows: [], keyboard: { names: [], current_idx: 0 }, configFailed: false }
}

function update(items, id, changes) {
  return items.map(function(item) { return item.id === id ? Object.assign({}, item, changes) : item })
}

// Niri sends complete snapshots first. Later events may temporarily refer to a
// workspace absent from the snapshot, so retain the window until it is closed.
function reduce(state, event) {
  var next = Object.assign({}, state)
  var value
  if ((value = event.WorkspacesChanged)) next.workspaces = value.workspaces
  else if ((value = event.WorkspaceActivated)) {
    var target = state.workspaces.find(function(w) { return w.id === value.id })
    next.workspaces = state.workspaces.map(function(w) {
      return Object.assign({}, w, {
        is_active: target && w.output === target.output ? w.id === value.id : w.is_active,
        is_focused: value.focused ? w.id === value.id : w.is_focused
      })
    })
  } else if ((value = event.WorkspaceUrgencyChanged)) next.workspaces = update(state.workspaces, value.id, { is_urgent: value.urgent })
  else if ((value = event.WorkspaceActiveWindowChanged)) next.workspaces = update(state.workspaces, value.workspace_id, { active_window_id: value.active_window_id })
  else if ((value = event.WindowsChanged)) next.windows = value.windows
  else if ((value = event.WindowOpenedOrChanged)) {
    next.windows = state.windows.filter(function(w) { return w.id !== value.window.id }).map(function(w) {
      return value.window.is_focused ? Object.assign({}, w, { is_focused: false }) : w
    }).concat([value.window])
  } else if ((value = event.WindowClosed)) next.windows = state.windows.filter(function(w) { return w.id !== value.id })
  else if ((value = event.WindowFocusChanged)) next.windows = state.windows.map(function(w) {
    return Object.assign({}, w, { is_focused: w.id === value.id })
  })
  else if ((value = event.WindowUrgencyChanged)) next.windows = update(state.windows, value.id, { is_urgent: value.urgent })
  else if ((value = event.WindowLayoutsChanged)) value.changes.forEach(function(change) {
    next.windows = update(next.windows, change[0], { layout: change[1] })
  })
  else if ((value = event.KeyboardLayoutsChanged)) next.keyboard = value.keyboard_layouts
  else if ((value = event.KeyboardLayoutSwitched)) next.keyboard = Object.assign({}, state.keyboard, { current_idx: value.idx })
  else if ((value = event.ConfigLoaded)) next.configFailed = value.failed
  else return state
  return next
}

function workspaceItems(state, output) {
  return state.workspaces.filter(function(w) { return !output || w.output === output }).map(function(w) {
    return Object.assign({}, w, { occupied: state.windows.some(function(window) { return window.workspace_id === w.id }) })
  }).sort(function(a, b) { return a.idx - b.idx })
}

if (typeof module !== "undefined") module.exports = { emptyState: emptyState, reduce: reduce, workspaceItems: workspaceItems }
