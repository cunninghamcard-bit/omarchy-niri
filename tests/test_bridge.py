import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / "payload"
spec = importlib.util.spec_from_file_location("bridge", root / "default/niri/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class NiriBridgeTests(unittest.TestCase):
  def test_app_identity_precedes_title(self):
    windows = [{"id": 1, "title": "Firefox documentation", "app_id": "kitty"}, {"id": 2, "app_id": "firefox"}]
    self.assertEqual(bridge.find_window(windows, "firefox")["id"], 2)
    self.assertIsNone(bridge.find_window(windows, "unknown"))

  def test_lock_intent_is_scoped_to_the_compositor_socket(self):
    with patch.dict(os.environ, {"NIRI_SOCKET": "/run/user/1000/niri.wayland-1.42.sock", "XDG_RUNTIME_DIR": "/run/user/1000"}):
      first = bridge.lock_marker()
    with patch.dict(os.environ, {"NIRI_SOCKET": "/run/user/1000/niri.wayland-1.43.sock", "XDG_RUNTIME_DIR": "/run/user/1000"}):
      self.assertNotEqual(first, bridge.lock_marker())

  def test_atomic_state_can_be_replaced(self):
    with tempfile.TemporaryDirectory() as directory:
      target = Path(directory) / "nested/config.kdl"
      bridge.atomic_write(target, "first")
      bridge.atomic_write(target, "second")
      self.assertEqual(target.read_text(), "second")
      self.assertEqual(list(target.parent.iterdir()), [target])

  def test_monitor_state_survives_a_stalled_brightness_probe(self):
    output = {"name": "Virtual-1", "current_mode": 0,
      "modes": [{"width": 1920, "height": 1080}], "logical": {"scale": 1.5}}
    text = io.StringIO()
    with patch.object(bridge, "request", side_effect=[{"Virtual-1": output}, output]), \
         patch.object(bridge.subprocess, "run", side_effect=subprocess.TimeoutExpired("brightness", 3)), \
         redirect_stdout(text):
      bridge.monitor_state()
    lines = text.getvalue().splitlines()
    self.assertEqual(len(lines), 8)
    self.assertEqual(lines[0], "")
    self.assertEqual(lines[5:7], ["Virtual-1", "1.5"])
    self.assertEqual(json.loads(lines[7])[0]["width"], 1920)

  def test_invalid_theme_keeps_the_previous_generated_file(self):
    with tempfile.TemporaryDirectory() as directory:
      home = Path(directory)
      palette = home / ".local/state/omarchy/current/theme/colors.toml"
      palette.parent.mkdir(parents=True)
      palette.write_text('accent = "not a color"\nbackground = "#ffffff"\nred = "#ff0000"\n')
      generated = home / ".config/niri/omarchy-theme.kdl"
      bridge.atomic_write(generated, "previous valid theme")
      with patch.object(bridge.Path, "home", return_value=home):
        with self.assertRaisesRegex(ValueError, "Invalid theme color"):
          bridge.theme()
      self.assertEqual(generated.read_text(), "previous valid theme")

  def test_invalid_arguments_fail_before_contacting_the_compositor(self):
    for arguments in [["focus"], ["output", "DP-1"], ["lock-clear", "unexpected"]]:
      with self.subTest(arguments=arguments), patch.object(sys, "argv", ["omarchy-niri", *arguments]), \
           patch.object(bridge, "request") as request, redirect_stderr(io.StringIO()):
        with self.assertRaises(SystemExit) as error:
          bridge.main()
        self.assertEqual(error.exception.code, 2)
        request.assert_not_called()

  def test_ipc_request_and_error_contract(self):
    # A real local socket checks framing and error propagation without requiring a desktop.
    with tempfile.TemporaryDirectory(prefix="nr-", dir="/tmp") as directory:
      address = str(Path(directory) / "ipc")
      server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      server.bind(address)
      server.listen()
      seen=[]
      def respond():
        for response in [{"Ok": {"Windows": [{"id": 13}]}}, {"Err": "session locked"}]:
          connection, _ = server.accept()
          with connection, connection.makefile('rb') as stream:
            seen.append(json.loads(stream.readline()))
            connection.sendall((json.dumps(response)+'\n').encode())
      thread=threading.Thread(target=respond, daemon=True)
      thread.start()
      with patch.dict(os.environ, {"NIRI_SOCKET": address}):
        self.assertEqual(bridge.request("Windows"), [{"id": 13}])
        with self.assertRaisesRegex(RuntimeError, "session locked"):
          bridge.request({"Action": {"FocusWindow": {"id": 13}}})
      thread.join(timeout=3)
      server.close()
      self.assertEqual(seen[0], "Windows")
      self.assertEqual(seen[1]["Action"]["FocusWindow"]["id"], 13)

if __name__ == '__main__':
  unittest.main()
