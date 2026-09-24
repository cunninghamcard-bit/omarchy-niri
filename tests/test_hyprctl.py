import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
shim = root / "overlay/default/niri/hyprctl.py"

OUTPUT = {
  "name": "Virtual-1", "make": "Some Maker", "model": "Model 15", "serial": "SN-1",
  "physical_size": [600, 340],
  "modes": [{"width": 1920, "height": 1080, "refresh_rate": 59951, "is_preferred": True}],
  "current_mode": 0, "is_custom_mode": False, "vrr_supported": True, "vrr_enabled": False,
  "logical": {"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0, "transform": "Normal"},
}
DISABLED = {
  "name": "eDP-1", "make": "Apple Computer Inc", "model": "Studio Display", "serial": None,
  "physical_size": None,
  "modes": [{"width": 2560, "height": 1600, "refresh_rate": 60000, "is_preferred": True},
            {"width": 1920, "height": 1200, "refresh_rate": 59995, "is_preferred": False}],
  "current_mode": 1, "is_custom_mode": False, "vrr_supported": False, "vrr_enabled": False,
  "logical": None,
}
WORKSPACES = [
  {"id": 71, "idx": 1, "name": None, "output": "Virtual-1", "is_urgent": False, "is_active": True, "is_focused": True, "active_window_id": 6},
  {"id": 90, "idx": 2, "name": "web", "output": "Virtual-1", "is_urgent": False, "is_active": False, "is_focused": False, "active_window_id": None},
  {"id": 3, "idx": 1, "name": None, "output": "eDP-1", "is_urgent": False, "is_active": True, "is_focused": False, "active_window_id": None},
]
WINDOWS = [
  {"id": 6, "title": "Inbox - Hey", "app_id": "hey", "pid": 4242, "workspace_id": 71, "is_focused": True, "is_floating": False, "is_urgent": False,
   "layout": {"window_size": [800, 600]}},
  {"id": 7, "title": "WebcamOverlay", "app_id": "webcam", "pid": None, "workspace_id": 90, "is_focused": False, "is_floating": True, "is_urgent": False,
   "layout": {"window_size": [320, 360]}},
]


class FakeNiri:
  """One socket answering every request line like the compositor would."""

  def __init__(self, directory):
    self.path = str(Path(directory) / "niri.sock")
    self.requests = []
    self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    self.server.bind(self.path)
    self.server.listen()
    self.reply = self.respond
    threading.Thread(target=self._serve, daemon=True).start()

  def _serve(self):
    while True:
      try:
        connection, _ = self.server.accept()
      except OSError:
        return
      with connection, connection.makefile("rb") as stream:
        message = json.loads(stream.readline())
        self.requests.append(message)
        connection.sendall((json.dumps(self.reply(message)) + "\n").encode())

  def respond(self, message):
    if message == "Outputs": return {"Ok": {"Outputs": {"Virtual-1": OUTPUT, "eDP-1": DISABLED}}}
    if message == "Workspaces": return {"Ok": {"Workspaces": WORKSPACES}}
    if message == "Windows": return {"Ok": {"Windows": WINDOWS}}
    if message == "FocusedOutput": return {"Ok": {"FocusedOutput": OUTPUT}}
    if message == "FocusedWindow": return {"Ok": {"FocusedWindow": WINDOWS[0]}}
    if isinstance(message, dict) and "Action" in message: return {"Ok": "Handled"}
    return {"Err": "unknown request"}


class HyprctlShimTests(unittest.TestCase):
  def run_shim(self, *arguments, wrapper=False):
    command = ["bash", str(root / "overlay/bin/hyprctl")] if wrapper else [sys.executable, str(shim)]
    environment = {**os.environ, "NIRI_SOCKET": self.niri.path}
    if wrapper: environment["OMARCHY_PATH"] = str(root / "overlay")
    return subprocess.run(command + list(arguments), capture_output=True, text=True, env=environment)

  def json_shim(self, *arguments):
    result = self.run_shim(*arguments)
    self.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)

  def actions(self):
    return [message["Action"] for message in self.niri.requests if isinstance(message, dict) and "Action" in message]

  def setUp(self):
    directory = tempfile.mkdtemp(prefix="hypr-", dir="/tmp")
    self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
    self.niri = FakeNiri(directory)
    self.addCleanup(self.niri.server.close)

  def test_monitors_reports_the_fields_upstream_reads(self):
    rows = self.json_shim("monitors", "-j")
    self.assertEqual(len(rows), 1)  # plain monitors excludes the disabled panel
    row = rows[0]
    self.assertEqual(row["name"], "Virtual-1")
    self.assertEqual((row["width"], row["height"]), (1920, 1080))
    self.assertEqual(row["refreshRate"], 59.951)
    self.assertEqual((row["x"], row["y"]), (0, 0))
    self.assertEqual(row["scale"], 1.0)
    self.assertEqual(row["transform"], 0)
    self.assertTrue(row["focused"])
    self.assertFalse(row["disabled"])
    self.assertEqual(row["mirrorOf"], "none")
    self.assertEqual(row["make"], "Some Maker")
    self.assertEqual(row["activeWorkspace"], {"id": 1, "name": "1"})

  def test_monitors_all_keeps_disabled_outputs(self):
    rows = self.json_shim("monitors", "all", "-j")
    self.assertEqual([row["name"] for row in rows], ["Virtual-1", "eDP-1"])
    panel = rows[1]
    self.assertTrue(panel["disabled"])
    self.assertIsNone(panel["scale"])
    self.assertIsNone(panel["transform"])
    self.assertEqual((panel["width"], panel["height"]), (1920, 1200))
    self.assertFalse(panel["focused"])
    self.assertEqual(panel["activeWorkspace"], {"id": 1, "name": "1"})

  def test_json_flag_is_accepted_before_the_subcommand(self):
    self.assertEqual(len(self.json_shim("-j", "monitors")), 1)

  def test_clients_shape_matches_upstream_queries(self):
    rows = self.json_shim("clients", "-j")
    self.assertEqual(rows[0], {"address": "0x6", "class": "hey", "title": "Inbox - Hey", "pid": 4242,
                               "floating": False, "workspace": {"id": 1, "name": "1"}, "size": [800, 600]})
    self.assertEqual(rows[1]["address"], "0x7")
    self.assertEqual(rows[1]["class"], "webcam")
    self.assertTrue(rows[1]["floating"])
    self.assertEqual(rows[1]["workspace"], {"id": 2, "name": "web"})
    self.assertIsNone(rows[1]["pid"])

  def test_activewindow_json_and_plain_forms(self):
    row = self.json_shim("activewindow", "-j")
    self.assertEqual(row["address"], "0x6")
    self.assertEqual(row["class"], "hey")
    result = self.run_shim("activewindow")
    self.assertEqual(result.returncode, 0, result.stderr)
    pid = [line for line in result.stdout.splitlines() if re.match(r"\s*pid:", line)][0].split()[1]
    self.assertEqual(pid, "4242")  # what omarchy-cmd-terminal-cwd greps out

  def test_activewindow_and_workspace_without_a_focus_target(self):
    self.niri.reply = lambda message: {"Ok": {"FocusedWindow": None}} if message == "FocusedWindow" else self.niri.respond(message)
    self.assertEqual(self.run_shim("activewindow", "-j").returncode, 1)
    self.assertEqual(self.run_shim("activewindow").stdout, "Invalid\n")
    self.niri.reply = lambda message: {"Ok": {"Workspaces": [WORKSPACES[1]]}} if message == "Workspaces" else self.niri.respond(message)
    self.assertEqual(self.run_shim("activeworkspace", "-j").returncode, 1)

  def test_activeworkspace_reports_index_name_and_output(self):
    self.assertEqual(self.json_shim("activeworkspace", "-j"), {"id": 1, "name": "1", "monitor": "Virtual-1"})

  def test_dispatchers_translate_to_niri_actions(self):
    for arguments, expected in [
      (["focuswindow", "address:0x7"], {"FocusWindow": {"id": 7}}),
      (["workspace", "1"], {"FocusWorkspace": {"reference": {"Index": 1}}}),
      (["workspace", "web"], {"FocusWorkspace": {"reference": {"Name": "web"}}}),
      (["focusmonitor", "eDP-1"], {"FocusMonitor": {"output": "eDP-1"}}),
      (["hl.dsp.focus({ window = \"address:0x7\" })"], {"FocusWindow": {"id": 7}}),
      (["hl.dsp.focus({ workspace = \"1\" })"], {"FocusWorkspace": {"reference": {"Index": 1}}}),
      (["hl.dsp.focus({ workspace = \"web\" })"], {"FocusWorkspace": {"reference": {"Name": "web"}}}),
      (["hl.dsp.focus({ monitor = \"eDP-1\" })"], {"FocusMonitor": {"output": "eDP-1"}}),
      (["hl.dsp.window.close({ window = \"address:0x6\" })"], {"CloseWindow": {"id": 6}}),
    ]:
      with self.subTest(arguments=arguments):
        self.niri.requests.clear()
        result = self.run_shim("dispatch", *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.actions(), [expected])

  def test_reload_and_switchxkblayout(self):
    self.run_shim("reload")
    self.run_shim("switchxkblayout", "all", "0")
    self.assertEqual(self.actions(), [{"LoadConfigFile": {"path": None}}, {"SwitchLayout": {"layout": {"Index": 0}}}])

  def test_unsupported_calls_fail_loudly(self):
    for arguments in [["devices", "-j"], ["binds"], ["cursorpos"], ["getoption", "cursor:no_hardware_cursors", "-j"],
                      ["keyword", "cursor:invisible", "true"], ["eval", "hl.config()"], ["hyprsunset", "temperature", "4000"],
                      ["dispatch", "exec", "bash", "-lc", "true"], ["dispatch", "togglefloating", "address:0x1"],
                      ["dispatch", "hl.dsp.dpms({ action = \"disable\" })"], ["dispatch", "$lua"], ["dispatch"],
                      ["-i", "1", "monitors", "-j"], ["monitors", "eDP-1", "-j"], ["monitors"], ["clients"],
                      ["activeworkspace"], ["activewindow", "extra"], ["reload", "now"], ["switchxkblayout", "all", "next"],
                      ["switchxkblayout", "event0", "0"], []]:
      with self.subTest(arguments=arguments):
        result = self.run_shim(*arguments)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("hyprctl (niri shim): unsupported: "), result.stderr)
        self.niri.requests.clear()

  def test_compositor_errors_are_reported_not_swallowed(self):
    self.niri.reply = lambda message: {"Err": "window with id 7 not found"} if isinstance(message, dict) and "Action" in message else self.niri.respond(message)
    result = self.run_shim("dispatch", "focuswindow", "address:0x7")
    self.assertEqual(result.returncode, 1)
    self.assertIn("window with id 7 not found", result.stderr)

  def test_bash_wrapper_execs_the_translation(self):
    result = self.run_shim("monitors", "-j", wrapper=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout)[0]["name"], "Virtual-1")


if __name__ == "__main__":
  unittest.main()
