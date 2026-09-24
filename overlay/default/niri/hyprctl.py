"""Translate the hyprctl calls Omarchy makes into Niri IPC for the private runtime.

SUPPORTED is the reviewed surface from docs/hyprctl-inventory.md; compat.py
reads it when scanning prepared runtimes. Queries answer with Hyprland-shaped
JSON, but only the fields upstream reads. Anything else fails loudly instead
of pretending to succeed.
"""
import json
import re
import sys

from bridge import request

SUPPORTED = {
  "monitors": None, "clients": None, "activewindow": None, "activeworkspace": None,
  "reload": None, "switchxkblayout": None,
  "dispatch": {"focuswindow", "workspace", "focusmonitor", "hl.dsp.focus", "hl.dsp.window.close"},
}

TRANSFORMS = {"Normal": 0, "90": 1, "180": 2, "270": 3, "Flipped": 4, "Flipped90": 5, "Flipped180": 6, "Flipped270": 7}
ADDRESS = re.compile(r"^address:0x([0-9a-f]+)$", re.IGNORECASE)
LUA = re.compile(r"^(hl\.[a-z_.]+?)\s*\(")
LUA_FIELD = re.compile(r"([a-z]+)\s*=\s*\"([^\"]*)\"")


def unsupported(tokens):
  print("hyprctl (niri shim): unsupported: " + " ".join(tokens), file=sys.stderr)
  return 1


def action(name):
  request({"Action": name})
  return 0


def window_id(address):
  match = ADDRESS.match(address or "")
  return int(match.group(1), 16) if match else None


def focus_or_close(kind, address, arguments):
  identifier = window_id(address)
  if identifier is None:
    return unsupported(["dispatch"] + arguments)
  return action({kind: {"id": identifier}})


def focus_workspace(reference):
  # Hyprland numbers its workspaces; Niri resolves an index on the focused output.
  if re.fullmatch(r"\d+", reference):
    return action({"FocusWorkspace": {"reference": {"Index": int(reference)}}})
  return action({"FocusWorkspace": {"reference": {"Name": reference}}})


def workspace_ref(workspace):
  # Hyprland numbers workspaces by name; Niri indices are per-output.
  return {"id": workspace["idx"], "name": workspace.get("name") or str(workspace["idx"])}


def workspace_entry(workspace):
  return {**workspace_ref(workspace), "monitor": workspace.get("output") or ""}


def client_entry(window, workspaces):
  workspace = workspaces.get(window.get("workspace_id"))
  return {
    "address": "0x%x" % window["id"],
    "class": window.get("app_id") or "",
    "title": window.get("title") or "",
    "pid": window.get("pid"),
    "floating": window.get("is_floating", False),
    "workspace": workspace_ref(workspace) if workspace else {"id": 0, "name": ""},
    "size": list(window["layout"]["window_size"]),
  }


def monitor_entry(index, output, focused, active):
  mode = output["modes"][output["current_mode"]] if output["current_mode"] is not None else None
  logical = output.get("logical") or {}
  workspace = active.get(output["name"])
  return {
    "id": index, "name": output["name"], "make": output["make"], "model": output["model"],
    "width": mode["width"] if mode else 0, "height": mode["height"] if mode else 0,
    "refreshRate": mode["refresh_rate"] / 1000 if mode else 0,
    "x": logical.get("x"), "y": logical.get("y"),
    "activeWorkspace": workspace_ref(workspace) if workspace else {"id": 0, "name": ""},
    "scale": logical.get("scale"), "transform": TRANSFORMS.get(logical.get("transform")),
    "focused": output["name"] == focused, "vrr": output["vrr_enabled"],
    "disabled": output["logical"] is None, "mirrorOf": "none",
  }


def query_monitors(arguments):
  if arguments not in ([], ["all"]):
    return unsupported(["monitors"] + arguments)
  outputs = request("Outputs")
  focused = request("FocusedOutput") or {}
  active = {w["output"]: w for w in request("Workspaces") if w.get("is_active") and w.get("output")}
  rows = [monitor_entry(index, output, focused.get("name", ""), active) for index, output in enumerate(outputs.values())]
  if "all" not in arguments:
    rows = [row for row in rows if not row["disabled"]]
  print(json.dumps(rows))
  return 0


def query_clients(arguments):
  if arguments:
    return unsupported(["clients"] + arguments)
  workspaces = {w["id"]: w for w in request("Workspaces")}
  print(json.dumps([client_entry(window, workspaces) for window in request("Windows")]))
  return 0


def query_activewindow(arguments, json_output):
  if arguments:
    return unsupported(["activewindow"] + arguments)
  window = request("FocusedWindow")
  if window is None:
    print("Invalid")
    return 1
  if not json_output:
    # Hyprland's plain block, trimmed to the fields upstream greps out of it.
    print("Window 0x%x -> %s:" % (window["id"], window.get("app_id") or ""))
    print("\ttitle: %s" % (window.get("title") or ""))
    print("\tpid: %s" % (window.get("pid") or ""))
    print("\tfloating: %d" % window.get("is_floating", False))
    return 0
  workspaces = {w["id"]: w for w in request("Workspaces")}
  print(json.dumps(client_entry(window, workspaces)))
  return 0


def query_activeworkspace(arguments):
  if arguments:
    return unsupported(["activeworkspace"] + arguments)
  workspace = next((w for w in request("Workspaces") if w.get("is_focused")), None)
  if workspace is None:
    print("Invalid")
    return 1
  print(json.dumps(workspace_entry(workspace)))
  return 0


def run_reload(arguments):
  if arguments:
    return unsupported(["reload"] + arguments)
  return action({"LoadConfigFile": {"path": None}})


def run_switchxkblayout(arguments):
  # Niri keeps one global keyboard layout, so only the every-device form applies.
  if len(arguments) != 2 or arguments[0] != "all" or not re.fullmatch(r"\d+", arguments[1]):
    return unsupported(["switchxkblayout"] + arguments)
  return action({"SwitchLayout": {"layout": {"Index": int(arguments[1])}}})


def run_dispatch(arguments):
  if not arguments:
    return unsupported(["dispatch"])
  lua = LUA.match(arguments[0])
  name = lua.group(1) if lua else arguments[0]
  fields = dict(LUA_FIELD.findall(arguments[0])) if lua else {}
  if name not in SUPPORTED["dispatch"]:
    return unsupported(["dispatch"] + arguments)
  if name == "focuswindow" and len(arguments) == 2:
    return focus_or_close("FocusWindow", arguments[1], arguments)
  if name == "workspace" and len(arguments) == 2:
    return focus_workspace(arguments[1])
  if name == "focusmonitor" and len(arguments) == 2:
    return action({"FocusMonitor": {"output": arguments[1]}})
  if name == "hl.dsp.focus":
    if "window" in fields:
      return focus_or_close("FocusWindow", fields["window"], arguments)
    if "monitor" in fields:
      return action({"FocusMonitor": {"output": fields["monitor"]}})
    if "workspace" in fields:
      return focus_workspace(fields["workspace"])
  if name == "hl.dsp.window.close" and "window" in fields:
    return focus_or_close("CloseWindow", fields["window"], arguments)
  return unsupported(["dispatch"] + arguments)


def main(argv):
  json_output, positionals, terminated = False, [], False
  for argument in argv:
    if terminated:
      positionals.append(argument)
    elif argument == "-j":
      json_output = True
    elif argument == "--":
      terminated = True
    elif argument.startswith("-"):
      return unsupported(argv)
    else:
      positionals.append(argument)
  if not positionals or positionals[0] not in SUPPORTED:
    return unsupported(argv)
  command, arguments = positionals[0], positionals[1:]
  if command == "monitors":
    return query_monitors(arguments) if json_output else unsupported(argv)
  if command == "clients":
    return query_clients(arguments) if json_output else unsupported(argv)
  if command == "activewindow":
    return query_activewindow(arguments, json_output)
  if command == "activeworkspace":
    return query_activeworkspace(arguments) if json_output else unsupported(argv)
  if command == "reload":
    return run_reload(arguments)
  if command == "switchxkblayout":
    return run_switchxkblayout(arguments)
  if command == "dispatch":
    return run_dispatch(arguments)
  return unsupported(argv)


if __name__ == "__main__":
  try:
    sys.exit(main(sys.argv[1:]))
  except (OSError, RuntimeError, KeyError, ValueError) as error:
    print("hyprctl (niri shim): " + str(error), file=sys.stderr)
    sys.exit(1)
