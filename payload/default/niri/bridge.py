"""Niri operations used by Omarchy; rendering and desktop services remain in QML."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import tomllib


def request(message):
  """Send one request; errors and missing sessions fail rather than become empty state."""
  with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(3)
    connection.connect(os.environ["NIRI_SOCKET"])
    connection.sendall((json.dumps(message) + "\n").encode())
    with connection.makefile("rb") as stream:
      reply = json.loads(stream.readline(16 * 1024 * 1024))
  if "Err" in reply:
    raise RuntimeError(reply["Err"])
  result = reply["Ok"]
  if isinstance(result, dict) and len(result) == 1:
    return next(iter(result.values()))
  return result


def atomic_write(path, content):
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".niri-")
  try:
    with os.fdopen(fd, "w") as file:
      file.write(content)
      file.flush()
      os.fsync(file.fileno())
    os.replace(temporary, path)
  finally:
    if os.path.exists(temporary):
      os.unlink(temporary)


def lock_marker():
  # Socket names change with compositor PID; a previous login's marker must
  # never be mistaken for a lock owned by this session.
  name = Path(os.environ["NIRI_SOCKET"]).name
  return Path(os.environ["XDG_RUNTIME_DIR"]) / ("omarchy-lock-" + name)


def find_window(windows, pattern):
  expression = re.compile(pattern, re.IGNORECASE)
  by_app = [w for w in windows if expression.search(w.get("app_id") or "")]
  matches = by_app or [w for w in windows if expression.search(w.get("title") or "")]
  return next(iter(matches), None)


def focus(pattern):
  window = find_window(request("Windows"), pattern)
  if window is None:
    return False
  request({"Action": {"FocusWindow": {"id": window["id"]}}})
  return True


def monitor_state():
  outputs = request("Outputs")
  focused = request("FocusedOutput") or {}
  name = focused.get("name", "")
  try:
    brightness = subprocess.run(["omarchy-brightness-display", "--monitor", name], capture_output=True, text=True, timeout=3)
    brightness_value = brightness.stdout.strip() if brightness.returncode == 0 else ""
  except subprocess.TimeoutExpired:
    # A stalled DDC probe must not discard the compositor's monitor state.
    brightness_value = ""
  print(brightness_value)
  values = list(outputs.values())
  internal = [o for o in values if re.match(r"^(eDP|LVDS|DSI)-", o["name"])]
  external = [o for o in values if o not in internal]
  print(internal[0]["name"] if internal else "")
  print(external[0]["name"] if external else "")
  print(next((o["name"] for o in internal if o.get("logical")), ""))
  print("")
  print(name)
  print((focused.get("logical") or {}).get("scale", ""))
  displays = []
  for output in values:
    index = output.get("current_mode")
    mode = output["modes"][index] if index is not None else {}
    displays.append({"name": output["name"], "enabled": output.get("logical") is not None,
      "focused": output["name"] == name, "width": mode.get("width", 0), "height": mode.get("height", 0)})
  print(json.dumps(displays))


def theme():
  home = Path.home()
  with (home / ".local/state/omarchy/current/theme/colors.toml").open("rb") as file:
    colors = tomllib.load(file)
  style_file = home / ".config/omarchy/niri-style.json"
  geometry = json.loads(style_file.read_text()) if style_file.exists() else {"radius": 10, "gaps": 10}
  radius, gaps = float(geometry["radius"]), float(geometry["gaps"])
  if not (0 <= radius <= 100 and 0 <= gaps <= 100):
    raise ValueError("Niri radius and gaps must be between 0 and 100")
  def color(name):
    value = colors[name]
    if not re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
      raise ValueError("Invalid theme color: " + name)
    return json.dumps(value)
  data = f'''layout {{
  gaps {gaps:g}
  focus-ring {{ off; }}
  border {{
    on
    width 2
    active-color {color("accent")}
    inactive-color {color("background")}
    urgent-color {color("red")}
  }}
}}
window-rule {{
  geometry-corner-radius {radius:g}
  clip-to-geometry true
}}
overview {{ backdrop-color {color("background")}; }}
'''
  atomic_write(home / ".config/niri/omarchy-theme.kdl", data)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  arities = {
    "input": (1, 2), "device": (1, 1), "internal": (0, 1), "mirror": (0, 1),
    "clamshell": (0, 1), "window-width": (1, 1), "webcam": (1, 1), "flag": (1, 2),
    "request": (1, 1), "focus": (1, 1), "monitor-state": (0, 0),
    "focused-output": (0, 0), "close-all": (0, 0), "output": (2, 2),
    "scale": (0, 1), "toggle-gaps": (0, 0), "theme": (0, 0),
    "lock-mark": (0, 0), "lock-clear": (0, 0), "lock-status": (0, 0),
  }
  parser.add_argument("operation", choices=arities)
  parser.add_argument("arguments", nargs="*")
  args = parser.parse_args()
  op, a = args.operation, args.arguments
  minimum, maximum = arities[op]
  if not minimum <= len(a) <= maximum:
    parser.error(f"{op} expects {minimum}" + (f" to {maximum}" if maximum != minimum else "") + " arguments")
  if op == "request":
    print(json.dumps(request(json.loads(a[0]))))
  elif op == "focus":
    return 0 if focus(a[0]) else 1
  elif op == "monitor-state":
    monitor_state()
  elif op == "focused-output":
    print((request("FocusedOutput") or {}).get("name", ""))
  elif op == "close-all":
    for window in request("Windows"):
      request({"Action": {"CloseWindow": {"id": window["id"]}}})
  elif op == "output":
    from desktop import set_output
    if a[1] not in ("on", "off"):
      raise ValueError("Expected on or off")
    set_output(a[0], a[1] == "on")
  elif op == "scale":
    from desktop import scale
    scale(*a)
  elif op in ("input", "device", "internal", "mirror", "clamshell", "window-width", "webcam", "flag"):
    from desktop import dispatch
    return dispatch(op, a)
  elif op == "toggle-gaps":
    path = Path.home() / ".config/omarchy/niri-style.json"
    geometry = json.loads(path.read_text())
    geometry["gaps"] = 10 if geometry["gaps"] == 0 else 0
    atomic_write(path, json.dumps(geometry) + "\n")
    theme()
  elif op == "theme":
    theme()
  elif op == "lock-mark":
    atomic_write(lock_marker(), "requested\n")
  elif op == "lock-clear":
    lock_marker().unlink(missing_ok=True)
  elif op == "lock-status":
    request("Version")
    return 0 if lock_marker().is_file() else 1
  else:
    parser.error("Unknown operation: " + op)
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
    print("omarchy-niri: " + str(error), file=sys.stderr)
    sys.exit(2)
