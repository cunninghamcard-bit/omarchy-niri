import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import manage


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(os.path.realpath(self.tmp.name))
        self.state = root / "state"
        self.system = root / "system"
        self.prefix = root / "prefix"
        self.base = root / "base"
        self.home = root / "home"
        self.base.mkdir()
        (self.home / ".config/niri").mkdir(parents=True)
        self.account = pwd.struct_passwd(("tester", "x", 1000, 1000, "", str(self.home), "/bin/sh"))
        self.patchers = [
            mock.patch.object(manage, "STATE", self.state),
            mock.patch.object(manage, "SYSTEM", self.system),
            mock.patch.object(manage, "PREFIX", self.prefix),
            mock.patch.object(manage.pwd, "getpwnam", return_value=self.account),
            mock.patch.object(manage, "run"),
            mock.patch.object(manage, "as_user"),
            mock.patch.object(manage.os, "chown"),
            mock.patch.object(manage, "prepare", side_effect=self.prepare),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmp.cleanup()

    def prepare(self, base, runtime, source):
        """Supply the files consumed by configuration while retaining build's real transaction."""
        for directory in ("bin", "config/niri", "config/omarchy", "default/wayland-sessions", "default/niri"):
            (runtime / directory).mkdir(parents=True, exist_ok=True)
        (runtime / "manifest.json").write_text('{"version":"test"}\n')
        (runtime / "config/niri/config.kdl").write_text("include \"/var/lib/omarchy-niri/current\"\n")
        (runtime / "config/omarchy/niri-style.json").write_text("{}\n")
        (runtime / "default/wayland-sessions/omarchy-niri.desktop").write_text("[Desktop Entry]\n")
        (runtime / "bin/omarchy-apply-lock").write_text("#!/bin/bash\ncat <<'EOF'\nlock\nEOF\n")
        return {"base": "test"}

    def original_files(self):
        files = {
            "etc/omarchy.conf": "old conf\n",
            "etc/sudoers.d/omarchy-dev-path": "old sudoers\n",
            "usr/local/share/wayland-sessions/omarchy.desktop": "old desktop\n",
            "usr/local/share/wayland-sessions/omarchy-niri.desktop": "old niri desktop\n",
            "etc/sddm.conf.d/90-omarchy-niri.conf": "old sddm\n",
            "usr/local/bin/omarchy-niri-extension": "old wrapper\n",
            "etc/pacman.d/hooks/95-omarchy-niri.hook": "old hook\n",
            "etc/pam.d/omarchy-lock-password": "old pam\n",
        }
        for relative, text in files.items():
            path = manage.system("/" + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return {relative: text for relative, text in files.items()}

    def test_install_update_uninstall_preserves_original_global_files(self):
        originals = self.original_files()
        manage.install("tester", self.base, dependencies=False)
        old_runtime = (manage.STATE / "current").resolve()
        manage.refresh(self.base)
        self.assertNotEqual(old_runtime, (manage.STATE / "current").resolve())
        manage.uninstall()
        for relative, text in originals.items():
            self.assertEqual(manage.system("/" + relative).read_text(), text)

    def test_configure_system_failure_restores_originals(self):
        originals = self.original_files()
        real_configure = manage.configure_system

        def fail_after_writes(runtime, changes):
            real_configure(runtime, changes)
            raise RuntimeError("configuration failed")

        with mock.patch.object(manage, "configure_system", side_effect=fail_after_writes):
            with self.assertRaisesRegex(RuntimeError, "configuration failed"):
                manage.install("tester", self.base, dependencies=False)
        for relative, text in originals.items():
            self.assertEqual(manage.system("/" + relative).read_text(), text)
        self.assertFalse((manage.STATE / "current").exists())

    def test_niri_validation_failure_restores_user_and_system_files(self):
        originals = self.original_files()
        config = self.home / '.config/niri/config.kdl'
        config.write_text('personal config before installation')
        def fail_validation(user, runtime, command):
            if command[:2] == ['niri', 'validate']:
                raise subprocess.CalledProcessError(1, command)
        with mock.patch.object(manage, 'as_user', side_effect=fail_validation):
            with self.assertRaises(subprocess.CalledProcessError):
                manage.install('tester', self.base, dependencies=False)
        self.assertEqual(config.read_text(), 'personal config before installation')
        for relative, text in originals.items():
            self.assertEqual(manage.system('/' + relative).read_text(), text)
        self.assertIsNone(manage.release())

    def test_state_directory_alias_does_not_undo_a_committed_install(self):
        self.state.mkdir()
        alias = self.state.parent / 'state-alias'
        alias.symlink_to(self.state, target_is_directory=True)
        with mock.patch.object(manage, 'STATE', alias):
            manage.install('tester', self.base, dependencies=False)
            self.assertIsNotNone(manage.release())
            self.assertTrue((alias / 'current/.extension/manage.py').is_file())

    def test_uninstall_preserves_later_edits(self):
        originals = self.original_files()
        manage.install('tester', self.base, dependencies=False)
        config = manage.system('/etc/omarchy.conf')
        config.write_text('later user edit')
        manage.uninstall()
        self.assertEqual(config.read_text(), originals['etc/omarchy.conf'])
        archives = list(self.state.parent.glob('state-uninstalled-*'))
        preserved = [f for f in (archives[0] / 'preserved').rglob('*') if f.is_file()]
        self.assertEqual([f.read_text() for f in preserved], ['later user edit'])

    def test_fresh_install_uninstall_removes_new_files(self):
        manage.install("tester", self.base, dependencies=False)
        new_file = manage.system("/etc/omarchy.conf")
        self.assertTrue(new_file.exists())
        manage.uninstall()
        self.assertFalse(new_file.exists())

    def test_refresh_prepare_rejection_keeps_current_tree(self):
        manage.install("tester", self.base, dependencies=False)
        current = (manage.STATE / "current").resolve()
        with mock.patch.object(manage, "prepare", side_effect=ValueError("rejected")):
            with self.assertRaisesRegex(ValueError, "rejected"):
                manage.refresh(self.base)
        self.assertEqual((manage.STATE / "current").resolve(), current)
        self.assertIn("rejected", (manage.STATE / "upgrade-failed.txt").read_text())

    def test_refresh_current_rename_failure_keeps_old_tree(self):
        manage.install("tester", self.base, dependencies=False)
        current = (manage.STATE / "current").resolve()
        with mock.patch.object(manage, "switch", side_effect=OSError("rename failed")):
            with self.assertRaisesRegex(OSError, "rename failed"):
                manage.refresh(self.base)
        self.assertEqual((manage.STATE / "current").resolve(), current)

    def test_legacy_migration_preserves_backups_and_uninstalls(self):
        originals = self.original_files()
        manage.STATE.mkdir(parents=True)
        changes = manage.Changes(manage.STATE)
        for relative in originals:
            changes.remember(manage.system("/" + relative))
        changes.flush()
        (manage.STATE / "installed.json").write_text(json.dumps({"user": "tester", "version": "0.2", "owner": "tester"}))
        (self.home / ".config/niri/config.kdl").write_text("include ~/.config/niri/omarchy.kdl\n")
        self.prefix.mkdir(parents=True)
        (self.prefix / ".omarchy-niri-owner").write_text("tester\n")
        manage.refresh(self.base)
        for relative in originals:
            backup = manage.STATE / "backups" / str(manage.system("/" + relative)).lstrip("/")
            self.assertTrue(backup.exists())
        manage.uninstall()
        for relative, text in originals.items():
            self.assertEqual(manage.system("/" + relative).read_text(), text)
        self.assertFalse(self.prefix.exists())

    def test_refresh_does_not_overwrite_user_edited_system_configuration(self):
        self.original_files()
        manage.install('tester', self.base, dependencies=False)
        current = (self.state / 'current').resolve()
        config = manage.system('/etc/omarchy.conf')
        config.write_text('intentional user edit')
        with self.assertRaisesRegex(ValueError, 'Managed file was edited'):
            manage.refresh(self.base)
        self.assertEqual(config.read_text(), 'intentional user edit')
        self.assertEqual((self.state / 'current').resolve(), current)

    def test_restore_preflights_all_files_before_mutating(self):
        path = self.system / "etc/example"
        path.parent.mkdir(parents=True)
        path.write_text("original\n")
        changes = manage.Changes(self.state)
        changes.remember(path)
        changes.write(path, "edited\n")
        directory = self.system / "etc/conflict"
        directory.mkdir()
        changes.items[str(directory)] = {"before": None, "after": None}
        changes.flush()
        with self.assertRaisesRegex(ValueError, "Managed path is not a file"):
            manage.Changes(self.state).restore()
        self.assertEqual(path.read_text(), "edited\n")

    def test_recover_before_and_after_current_publication(self):
        old = self.state / "runtimes/old"
        new = self.state / "runtimes/new"
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        self.state.mkdir(parents=True, exist_ok=True)
        changed = self.system / "changed"
        changed.parent.mkdir(parents=True)
        changed.write_text("new\n")
        journal = self.state / "pending"
        pending_changes = manage.Changes(journal)
        pending_changes.write(changed, "new\n")
        manage.atomic(journal / "operation.json", json.dumps({"runtime": str(new), "changes": {}}))
        manage.recover()
        self.assertFalse(new.exists())
        self.assertFalse((self.state / "pending").exists())

        new.mkdir()
        pending = self.state / "pending"
        pending.mkdir()
        manage.atomic(pending / "operation.json", json.dumps({"runtime": str(new), "changes": {}}))
        (self.state / "current-next").symlink_to(new)
        (self.state / "current-next").replace(self.state / "current")
        manage.recover()
        self.assertTrue(new.exists())
        self.assertFalse((self.state / "pending").exists())

    def test_restart_after_journal_initialization_interrupted(self):
        for partial_write in (False, True):
            with self.subTest(partial_write=partial_write):
                pending = self.state / 'pending'
                pending.mkdir(parents=True)
                if partial_write:
                    (pending / '.operation.json-interrupted').write_text('{')
                with manage.writer():
                    self.assertFalse(pending.exists())

    def test_journal_write_failure_removes_unpublished_candidate(self):
        originals = self.original_files()
        real_atomic = manage.atomic
        def fail_journal(path, *args, **kwargs):
            if path.name == 'operation.json':
                raise OSError('journal write failed')
            return real_atomic(path, *args, **kwargs)
        with mock.patch.object(manage, 'atomic', side_effect=fail_journal):
            with self.assertRaisesRegex(OSError, 'journal write failed'):
                manage.install('tester', self.base, dependencies=False)
        self.assertFalse((self.state / 'pending').exists())
        self.assertEqual(list((self.state / 'runtimes').iterdir()), [])
        for relative, text in originals.items():
            self.assertEqual(manage.system('/' + relative).read_text(), text)

    def test_writer_collision_is_real_fcntl_lock(self):
        script = "import manage,time;\nwith manage.writer():\n print('locked',flush=True); time.sleep(2)"
        env = {**os.environ, "OMARCHY_NIRI_STATE": str(self.state)}
        first = subprocess.Popen([sys.executable, "-c", script], cwd=str(Path(manage.__file__).parent), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(first.stdout.readline().strip(), "locked")
            second = subprocess.run([sys.executable, "-c", "import manage;\nwith manage.writer(): pass"],
                                    cwd=str(Path(manage.__file__).parent), env=env, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("Another Niri installation", second.stderr)
        finally:
            first.wait(timeout=5)
            first.stdout.close()
            first.stderr.close()


if __name__ == "__main__":
    unittest.main()
