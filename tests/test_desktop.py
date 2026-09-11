#!/usr/bin/env python3
"""Pure contract checks for the Niri desktop adapter.

These tests mock the IPC and file-writing edges.  They are deliberately safe to
run on macOS or on a packaged Omarchy host without changing the user's Niri
configuration or display state.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("OMARCHY_NIRI_SOURCE", ROOT / "overlay"))
sys.path.insert(0, str(SOURCE / "default" / "niri"))

import desktop  # noqa: E402


class DesktopContracts(unittest.TestCase):
  def test_enabled_action_uses_current_state(self):
    self.assertTrue(desktop.enabled_action("on", False))
    self.assertFalse(desktop.enabled_action("off", True))
    self.assertFalse(desktop.enabled_action("toggle", True))
    self.assertTrue(desktop.enabled_action("toggle", False))

  def test_enabled_action_rejects_unknown_value(self):
    with self.assertRaises(ValueError):
      desktop.enabled_action("reload", False)

  def test_set_output_refuses_disabling_last_logical_output(self):
    outputs = {
      "eDP-1": {"name": "eDP-1", "logical": {"scale": 1}},
    }
    with patch.object(desktop, "request", return_value=outputs), \
        patch.object(desktop, "outputs_write") as write:
      with self.assertRaisesRegex(ValueError, "last output"):
        desktop.set_output("eDP-1", False)
      write.assert_not_called()

  def test_set_output_persists_a_toggle_without_touching_ipc(self):
    outputs = {
      "eDP-1": {"name": "eDP-1", "logical": {"scale": 1}},
      "DP-1": {"name": "DP-1", "logical": {"scale": 1}},
    }
    with patch.object(desktop, "request", return_value=outputs), \
        patch.object(desktop, "outputs_write") as write:
      desktop.set_output("eDP-1", False)
    write.assert_called_once()
    payload = write.call_args.args[0]
    self.assertTrue(payload["outputs"]["eDP-1"]["off"])

  def test_set_output_rejects_unknown_output(self):
    with patch.object(desktop, "request", return_value={}):
      with self.assertRaisesRegex(ValueError, "Unknown output"):
        desktop.set_output("DP-404", True)

  def test_scale_rejects_missing_focused_output(self):
    with patch.object(desktop, "request", return_value=None):
      with self.assertRaisesRegex(ValueError, "focused output"):
        desktop.scale()

  def test_scale_rejects_out_of_range_value_before_persisting(self):
    output = {"name": "DP-1", "logical": {"scale": 1}}
    with patch.object(desktop, "request", return_value=output), \
        patch.object(desktop, "outputs_write") as write:
      with self.assertRaisesRegex(ValueError, "between 0.5 and 5"):
        desktop.scale("9")
      write.assert_not_called()

  def test_input_toggle_requires_a_detected_device(self):
    with patch.object(desktop, "input_devices", return_value=iter(())):
      with self.assertRaisesRegex(ValueError, "No touchpad"):
        desktop.input_toggle("touchpad", "toggle")

  def test_window_width_rejects_unknown_mode(self):
    with patch.object(desktop, "request", return_value={"id": 7, "app_id": "foot"}):
      with self.assertRaisesRegex(ValueError, "Expected save or restore"):
        desktop.window_width("resize")


if __name__ == "__main__":
  unittest.main(verbosity=2)
