import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


MODULE = Path(__file__).parents[1] / "manage.py"
SPEC = importlib.util.spec_from_file_location("omarchy_niri_manage", MODULE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class InstallerTests(unittest.TestCase):
  def setUp(self):
    self.tmp = Path(tempfile.mkdtemp(prefix="omarchy-niri-installer-test-"))
    self.addCleanup(shutil.rmtree, self.tmp, True)

  def test_restore_preflights_conflicts_without_partial_restore(self):
    state = self.tmp / "state"
    state.mkdir()
    (state / "generations").mkdir()
    left = self.tmp / "left"
    right = self.tmp / "right"
    left.write_text("old-left")
    right.write_text("old-right")
    changes = manager.Changes(state)
    changes.write(left, "managed-left")
    changes.write(right, "managed-right")
    left.write_text("user-left-edit")
    right.write_text("managed-right")

    conflicts = changes.restore()

    self.assertEqual(conflicts, [str(left)])
    self.assertEqual(left.read_text(), "user-left-edit")
    self.assertEqual(right.read_text(), "managed-right")

  def test_uninstall_archives_subsequent_edit_and_restores_original(self):
    state = self.tmp / "state"
    state.mkdir()
    prefix = self.tmp / "prefix"
    prefix.mkdir()
    (prefix / ".omarchy-niri-owner").write_text("test-owner\n")
    target = self.tmp / "config"
    target.write_text("original")
    changes = manager.Changes(state)
    changes.write(target, "managed")
    target.write_text("user edit")
    (state / "installed.json").write_text(json.dumps({"generation": "unused", "owner": "test-owner"}))
    old_state, old_prefix = manager.STATE, manager.PREFIX
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))

    manager.uninstall()

    self.assertEqual(target.read_text(), "original")
    archives = list((state.parent).glob("omarchy-niri-uninstalled-*"))
    self.assertEqual(len(archives), 1)
    self.assertEqual((archives[0] / "preserved-edits" / target.relative_to("/")).read_text(), "user edit")
    self.assertFalse(prefix.exists())

  def test_uninstall_without_install_marker_cannot_remove_prefix(self):
    state = self.tmp / "state"
    state.mkdir()
    prefix = self.tmp / "prefix"
    prefix.mkdir()
    (prefix / "sentinel").write_text("do not remove")
    old_state, old_prefix = manager.STATE, manager.PREFIX
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))

    with self.assertRaises(ValueError):
      manager.uninstall()

    self.assertEqual((prefix / "sentinel").read_text(), "do not remove")

  def test_refresh_state_write_failure_restores_old_pointer(self):
    state = self.tmp / "state"
    state.mkdir()
    (state / "generations").mkdir()
    old = self.tmp / "old"
    old.mkdir()
    (state / "current").symlink_to(old)
    home = self.tmp / "home"
    (home / ".config" / "niri").mkdir(parents=True)
    (home / ".config" / "niri" / "config.kdl").write_text("include \"omarchy.kdl\"\n")
    (state / "installed.json").write_text(json.dumps({
      "user": "testuser", "base": str(self.tmp), "generation": str(old)}))
    old_state = manager.STATE
    old_prefix = manager.PREFIX
    prefix = self.tmp / "prefix"
    prefix.mkdir()
    (prefix / "owner-sentinel").write_text("old runtime")
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))
    manager_copy = mock.Mock(side_effect=lambda _base, stage: (
      stage.mkdir(), (stage / "default" / "niri").mkdir(parents=True),
      (stage / "default" / "niri" / "config.kdl").write_text("")
    ))
    manager_user = mock.Mock()
    original_atomic = manager.atomic
    state_file = state / "installed.json"
    injected = False

    def fail_once(path, content, mode=0o644):
      nonlocal injected
      if Path(path) == state_file and not injected:
        injected = True
        raise OSError("injected state write failure")
      return original_atomic(path, content, mode)

    account = SimpleNamespace(pw_dir=str(home), pw_uid=os.getuid(), pw_gid=os.getgid())
    with mock.patch.object(manager, "copy_runtime", manager_copy), \
        mock.patch.object(manager, "as_user", manager_user), \
        mock.patch.object(manager, "atomic", side_effect=fail_once), \
        mock.patch.object(manager.pwd, "getpwnam", return_value=account):
      with self.assertRaises(OSError):
        manager.refresh(self.tmp)

    self.assertTrue(injected)
    self.assertEqual(os.readlink(state / "current"), str(old))
    self.assertEqual(json.loads((state / "installed.json").read_text())["generation"], str(old))
    self.assertFalse(list((state / "generations").iterdir()), "failed generation was not cleaned up")

  def test_refresh_prefix_publish_failure_restores_runtime_and_pointer(self):
    state = self.tmp / "state"
    state.mkdir()
    (state / "generations").mkdir()
    old = self.tmp / "old"
    old.mkdir()
    (state / "current").symlink_to(old)
    home = self.tmp / "home"
    (home / ".config" / "niri").mkdir(parents=True)
    (home / ".config" / "niri" / "config.kdl").write_text("include \"omarchy.kdl\"\n")
    (state / "installed.json").write_text(json.dumps({
      "user": "testuser", "base": str(self.tmp), "generation": str(old), "version": "old"}))
    prefix = self.tmp / "prefix"
    prefix.mkdir()
    (prefix / "owner-sentinel").write_text("old runtime")
    old_state, old_prefix = manager.STATE, manager.PREFIX
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))
    manager_copy = mock.Mock(side_effect=lambda _base, stage: (
      stage.mkdir(), (stage / "default" / "niri").mkdir(parents=True),
      (stage / "default" / "niri" / "config.kdl").write_text("")))
    account = SimpleNamespace(pw_dir=str(home), pw_uid=os.getuid(), pw_gid=os.getgid())
    original_rename = Path.rename
    staged = prefix.with_name(prefix.name + "-next")

    def fail_staged_rename(path, target):
      if path == staged:
        raise OSError("injected prefix publish failure")
      return original_rename(path, target)

    with mock.patch.object(manager, "copy_runtime", manager_copy), \
        mock.patch.object(manager, "as_user"), \
        mock.patch.object(manager.pwd, "getpwnam", return_value=account), \
        mock.patch.object(Path, "rename", autospec=True, side_effect=fail_staged_rename):
      with self.assertRaisesRegex(OSError, "prefix publish"):
        manager.refresh(self.tmp)

    self.assertEqual(os.readlink(state / "current"), str(old))
    self.assertEqual(json.loads((state / "installed.json").read_text())["generation"], str(old))
    self.assertEqual((prefix / "owner-sentinel").read_text(), "old runtime")
    self.assertFalse(list((state / "generations").iterdir()), "failed generation was not cleaned up")

  def test_recover_interrupted_refresh_restores_prepublication_state(self):
    state = self.tmp / "state"
    state.mkdir()
    old_generation = self.tmp / "old-generation"
    new_generation = state / "generations" / "new-generation"
    old_generation.mkdir()
    new_generation.mkdir(parents=True)
    (state / "current").symlink_to(new_generation)
    prefix = self.tmp / "prefix"
    archive = self.tmp / "prefix-previous"
    prefix.mkdir(); (prefix / "new").write_text("new")
    archive.mkdir(); (archive / "old").write_text("old")
    (state / "installed.json").write_text(json.dumps({"generation": str(old_generation)}))
    (state / "refresh-transaction.json").write_text(json.dumps({
      "previous": str(old_generation), "generation": str(new_generation)}))
    old_state, old_prefix = manager.STATE, manager.PREFIX
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))

    manager.recover_refresh()

    self.assertEqual(os.readlink(state / "current"), str(old_generation))
    self.assertTrue((prefix / "old").is_file())
    self.assertFalse(new_generation.exists())
    self.assertFalse((state / "refresh-transaction.json").exists())

  def test_recover_committed_refresh_keeps_new_publication(self):
    state = self.tmp / "state"
    state.mkdir()
    old_generation = self.tmp / "old-generation"
    new_generation = state / "generations" / "new-generation"
    old_generation.mkdir()
    new_generation.mkdir(parents=True)
    (state / "current").symlink_to(old_generation)
    prefix = self.tmp / "prefix"
    archive = self.tmp / "prefix-previous"
    prefix.mkdir(); (prefix / "new").write_text("new")
    archive.mkdir(); (archive / "old").write_text("old")
    (state / "installed.json").write_text(json.dumps({"generation": str(new_generation)}))
    (state / "refresh-transaction.json").write_text(json.dumps({
      "previous": str(old_generation), "generation": str(new_generation)}))
    old_state, old_prefix = manager.STATE, manager.PREFIX
    manager.STATE, manager.PREFIX = state, prefix
    self.addCleanup(lambda: setattr(manager, "STATE", old_state))
    self.addCleanup(lambda: setattr(manager, "PREFIX", old_prefix))

    manager.recover_refresh()

    self.assertEqual(os.readlink(state / "current"), str(new_generation))
    self.assertTrue((prefix / "new").is_file())
    self.assertFalse(archive.exists())
    self.assertTrue(new_generation.exists())
    self.assertFalse((state / "refresh-transaction.json").exists())

  def _runtime_fixture(self, base_content="base", payload_content="payload"):
    root = self.tmp / ("fixture-" + next(tempfile._get_candidate_names()))
    base = root / "base"
    here = root / "extension"
    (base / "bin").mkdir(parents=True)
    (base / "shell").mkdir()
    (base / "default" / "niri").mkdir(parents=True)
    (base / "config").mkdir()
    (base / "default" / "niri" / "config.kdl").write_text(base_content)
    (here / "payload" / "default" / "niri").mkdir(parents=True)
    (here / "payload" / "default" / "niri" / "config.kdl").write_text(payload_content)
    digest = hashlib.sha256(base_content.encode()).hexdigest()
    payload_digest = hashlib.sha256(payload_content.encode()).hexdigest()
    manifest = {"files": {"default/niri/config.kdl": {
      "baseSha256": [digest], "sha256": payload_digest}}}
    (here / "manifest.json").write_text(json.dumps(manifest))
    return base, here

  def test_damaged_payload_is_rejected(self):
    base, here = self._runtime_fixture()
    payload = here / "payload" / "default" / "niri" / "config.kdl"
    payload.write_text("tampered")
    old_here = manager.HERE
    manager.HERE = here
    self.addCleanup(lambda: setattr(manager, "HERE", old_here))
    with self.assertRaisesRegex(ValueError, "Damaged extension payload"):
      manager.copy_runtime(base, self.tmp / "generation")

  def test_nonmatching_base_is_rejected(self):
    base, here = self._runtime_fixture(base_content="expected", payload_content="payload")
    (base / "default" / "niri" / "config.kdl").write_text("changed upstream")
    old_here = manager.HERE
    manager.HERE = here
    self.addCleanup(lambda: setattr(manager, "HERE", old_here))
    with self.assertRaisesRegex(ValueError, "Unsupported upstream change"):
      manager.copy_runtime(base, self.tmp / "generation")


if __name__ == "__main__":
  unittest.main()
