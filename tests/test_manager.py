import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
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
        for directory in ("bin", "default/wayland-sessions"):
            (runtime / directory).mkdir(parents=True, exist_ok=True)
        (runtime / "default/wayland-sessions/omarchy-niri.desktop").write_text("[Desktop Entry]\n")
        (runtime / "bin/omarchy-apply-lock").write_text("#!/bin/bash\ncat <<'EOF'\nlock\nEOF\n")
        return {"base": "test"}

    def user_commands(self, name):
        return [call.args[2] for call in manage.as_user.call_args_list if call.args[2][-1] == name]

    def sourced(self, conf, desktop=None):
        """What a plain shell resolves OMARCHY_PATH to after sourcing the conf."""
        environment = dict(os.environ)
        environment.pop("XDG_CURRENT_DESKTOP", None)
        environment.pop("XDG_SESSION_DESKTOP", None)
        if desktop is not None:
            environment["XDG_CURRENT_DESKTOP"] = desktop
        result = subprocess.run(["bash", "-c", '. "$1"; printf %s "$OMARCHY_PATH"', "bash", str(conf)],
                                capture_output=True, text=True, env=environment)
        return result.stdout.strip()

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

        def fail_after_writes(runtime, changes, autologin=False):
            real_configure(runtime, changes, autologin)
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
        hook = manage.system('/etc/pacman.d/hooks/95-omarchy-niri.hook')
        hook.write_text('intentional user edit')
        with self.assertRaisesRegex(ValueError, 'Managed file was edited'):
            manage.refresh(self.base)
        self.assertEqual(hook.read_text(), 'intentional user edit')
        self.assertEqual((self.state / 'current').resolve(), current)
        # Only a marker-less rewrite of omarchy.conf is adopted; edits inside the managed file still fail.
        conf = manage.system('/etc/omarchy.conf')
        conf.write_text(conf.read_text().replace('/usr/share/omarchy', '/opt/other'))
        with self.assertRaisesRegex(ValueError, 'Managed file was edited'):
            manage.refresh(self.base)
        self.assertIn('/opt/other', conf.read_text())

    def test_update_adopts_a_dev_link_rewritten_conf(self):
        self.original_files()
        manage.install('tester', self.base, dependencies=False)
        conf = manage.system('/etc/omarchy.conf')
        conf.write_text('export OMARCHY_PATH="/opt/omarchy"\n')  # what omarchy dev link writes
        manage.refresh(self.base)  # must not fail with "Managed file was edited"
        self.assertIn(manage.MARKER, conf.read_text())
        self.assertEqual(self.sourced(conf, desktop='Hyprland'), '/opt/omarchy')
        self.assertEqual(self.sourced(conf, desktop='niri'), os.path.realpath(self.state / 'current'))
        # dev unlink resets the packaged default; the next update keeps that instead.
        conf.write_text('export OMARCHY_PATH="/usr/share/omarchy"\n')
        manage.refresh(self.base)
        self.assertIn(manage.MARKER, conf.read_text())
        self.assertEqual(self.sourced(conf, desktop='Hyprland'), '/usr/share/omarchy')

    def test_install_conf_falls_back_to_packaged_omarchy(self):
        manage.install('tester', self.base, dependencies=False)
        conf = manage.system('/etc/omarchy.conf')
        self.assertIn(manage.MARKER, conf.read_text())
        self.assertEqual(self.sourced(conf, desktop='niri'), os.path.realpath(self.state / 'current'))
        self.assertEqual(self.sourced(conf, desktop='Hyprland'), '/usr/share/omarchy')
        self.assertEqual(self.sourced(conf), '/usr/share/omarchy')

    def test_install_preserves_preexisting_dev_link_default(self):
        conf = manage.system('/etc/omarchy.conf')
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text('export OMARCHY_PATH="/opt/omarchy"\n')
        manage.install('tester', self.base, dependencies=False)
        self.assertIn(manage.MARKER, conf.read_text())
        self.assertEqual(self.sourced(conf, desktop='Hyprland'), '/opt/omarchy')
        self.assertEqual(self.sourced(conf, desktop='niri'), os.path.realpath(self.state / 'current'))
        self.assertEqual(self.sourced(conf, desktop='GNOME'), '/opt/omarchy')

    def test_unmanaged_system_files_are_never_written(self):
        originals = self.original_files()
        manage.install('tester', self.base, dependencies=False)
        for relative in ('etc/sudoers.d/omarchy-dev-path', 'usr/local/share/wayland-sessions/omarchy.desktop',
                         'etc/sddm.conf.d/90-omarchy-niri.conf'):
            self.assertEqual(manage.system('/' + relative).read_text(), originals[relative])
        ledger = json.loads((self.state / 'changes.json').read_text())
        for relative in ('etc/sudoers.d/omarchy-dev-path', 'usr/local/share/wayland-sessions/omarchy.desktop',
                         'etc/sddm.conf.d/90-omarchy-niri.conf', 'etc/pacman.d/hooks/10-omarchy-hyprland-reload-pause.hook',
                         'etc/pacman.d/hooks/90-omarchy-hyprland-reload-resume.hook'):
            self.assertNotIn(str(manage.system('/' + relative)), ledger)
        self.assertIn(str(manage.system('/usr/local/share/wayland-sessions/omarchy-niri.desktop')), ledger)

    def test_autologin_only_with_flag_and_kept_by_update(self):
        manage.install('tester', self.base, dependencies=False, autologin=True)
        sddm = manage.system('/etc/sddm.conf.d/90-omarchy-niri.conf')
        self.assertEqual(sddm.read_text(), '[Autologin]\nSession=omarchy-niri.desktop\n')
        self.assertTrue(json.loads((self.state / 'current/.extension/release.json').read_text())['autologin'])
        manage.refresh(self.base)
        self.assertEqual(sddm.read_text(), '[Autologin]\nSession=omarchy-niri.desktop\n')

    def test_without_autologin_an_existing_entry_is_released(self):
        self.original_files()
        manage.install('tester', self.base, dependencies=False)
        sddm = manage.system('/etc/sddm.conf.d/90-omarchy-niri.conf')
        self.assertEqual(sddm.read_text(), 'old sddm\n')
        manage.refresh(self.base)
        self.assertEqual(sddm.read_text(), 'old sddm\n')
        self.assertNotIn(str(sddm), json.loads((self.state / 'changes.json').read_text()))

    def test_update_releases_files_the_03_install_still_managed(self):
        manage.install('tester', self.base, dependencies=False)
        changes = manage.Changes(self.state)
        sudoers = manage.system('/etc/sudoers.d/omarchy-dev-path')
        sudoers.parent.mkdir(parents=True, exist_ok=True)
        changes.remember(sudoers)  # a 0.3 install had no predecessor for this file
        sudoers.write_text('Defaults secure_path="/var/lib/omarchy-niri/current/bin:/usr/bin"\n')
        changes.record(sudoers)
        desktop = manage.system('/usr/local/share/wayland-sessions/omarchy.desktop')
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text('old desktop\n')
        changes.remember(desktop)  # 0.3 shadowed a pre-existing Hyprland entry
        desktop.write_text('[Desktop Entry 0.3]\n')
        changes.record(desktop)
        hooks = []
        for name in ('10-omarchy-hyprland-reload-pause.hook', '90-omarchy-hyprland-reload-resume.hook'):
            hook = manage.system('/etc/pacman.d/hooks/' + name)
            hook.parent.mkdir(parents=True, exist_ok=True)
            changes.remember(hook)  # 0.3 masked the upstream hook with a symlink
            hook.symlink_to('/dev/null')
            changes.record(hook)
            hooks.append(hook)
        desktop.write_text('user edited desktop\n')  # edited after the 0.3 install
        manage.refresh(self.base)
        self.assertFalse(sudoers.exists())  # no predecessor: removed
        for hook in hooks:
            self.assertFalse(hook.exists())  # mask removed, upstream hook dir untouched
        self.assertEqual(desktop.read_text(), 'old desktop\n')  # predecessor restored
        preserved = [f for f in (self.state / 'preserved').rglob('*') if f.is_file()]
        self.assertEqual([f.read_text() for f in preserved], ['user edited desktop\n'])
        ledger = json.loads((self.state / 'changes.json').read_text())
        for path in [sudoers, desktop, *hooks, manage.system('/etc/sddm.conf.d/90-omarchy-niri.conf')]:
            self.assertNotIn(str(path), ledger)

    def test_status_and_notify_report_when_the_conf_is_not_managed(self):
        manage.install('tester', self.base, dependencies=False)
        conf = manage.system('/etc/omarchy.conf')
        conf.write_text('export OMARCHY_PATH="/opt/omarchy"\n')
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(manage.status(), 0)
        self.assertIn('not using the runtime', out.getvalue())
        manage.notify()
        self.assertIn('update', manage.run.call_args[0][2])

    def test_notify_is_quiet_while_the_managed_conf_matches(self):
        manage.install('tester', self.base, dependencies=False)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(manage.status(), 0)
        manage.notify()  # installed runtime matches the manifest and the conf still has the marker
        manage.run.assert_not_called()

    def test_notify_ignores_a_version_only_change(self):
        manage.install('tester', self.base, dependencies=False)
        metadata = json.loads((self.state / 'current/.extension/release.json').read_text())
        metadata['version'] = '9.9.9'  # only the plugin version moved on; the runtime did not
        (self.state / 'current/.extension/release.json').write_text(json.dumps(metadata))
        manage.notify()
        manage.run.assert_not_called()

    def test_notify_prompts_when_the_runtime_version_changes(self):
        manage.install('tester', self.base, dependencies=False)
        metadata = json.loads((self.state / 'current/.extension/release.json').read_text())
        metadata['runtimeVersion'] = '0.3.0'
        (self.state / 'current/.extension/release.json').write_text(json.dumps(metadata))
        manage.notify()
        self.assertIn('update', manage.run.call_args[0][2])

    def test_activate_runs_the_user_step_on_install_and_update(self):
        manage.install('tester', self.base, dependencies=False)
        self.assertTrue(self.user_commands('sync'))
        manage.as_user.reset_mock()
        manage.refresh(self.base)
        self.assertTrue(self.user_commands('sync'))

    def test_no_home_path_is_recorded_in_the_root_ledger(self):
        manage.install('tester', self.base, dependencies=False)
        manage.refresh(self.base)
        ledger = json.loads((self.state / 'changes.json').read_text())
        self.assertFalse([key for key in ledger if key.startswith(str(self.home) + '/')])

    def test_uninstall_runs_the_user_level_unsync(self):
        manage.install('tester', self.base, dependencies=False)
        manage.uninstall()
        self.assertTrue(self.user_commands('unsync'))

    def test_update_hands_the_03_home_ledger_to_the_user_step(self):
        manage.install('tester', self.base, dependencies=False)
        changes = manage.Changes(self.state)
        config = self.home / '.config/niri/config.kdl'
        config.write_text('original user config\n')
        changes.remember(config)  # 0.3 backed up the user's original before overwriting it
        config.write_text('include "/var/lib/omarchy-niri/current/default/niri/config.kdl"\n')
        changes.record(config)
        style = self.home / '.config/omarchy/niri-style.json'
        style.parent.mkdir(parents=True, exist_ok=True)
        for path in (style, *[self.home / '.config/niri' / (name + '.kdl')
                              for name in ('input', 'outputs', 'bindings', 'omarchy-theme')]):
            changes.remember(path)  # 0.3 created these from root: no predecessor
            path.write_text('// created by 0.3\n')
            changes.record(path)
        manage.refresh(self.base)
        ledger = json.loads((self.state / 'changes.json').read_text())
        self.assertFalse([key for key in ledger if key.startswith(str(self.home) + '/')])
        self.assertEqual(config.read_text(), 'include "/var/lib/omarchy-niri/current/default/niri/config.kdl"\n')
        self.assertEqual(style.read_text(), '// created by 0.3\n')
        self.assertEqual(config.with_name('config.kdl.pre-omarchy-niri').read_text(), 'original user config\n')

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


class SyncTests(unittest.TestCase):
    """The unprivileged sync/unsync step, run against a temporary home with fake tools."""
    root = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home = base / 'home'
        self.tools = base / 'bin'
        self.home.mkdir()
        self.tools.mkdir()
        self.tool('omarchy-niri', ': > "$HOME/.config/niri/omarchy-theme.kdl"')
        # The test host has no real niri; fakes on PATH decide whether validation passes.
        self.environment = mock.patch.dict(os.environ,
                                           {**os.environ, 'PATH': str(self.tools) + os.pathsep + os.environ['PATH']})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def tool(self, name, body):
        path = self.tools / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
        return path

    def snapshots(self):
        return {str(path.relative_to(self.home)): (path.stat().st_ino, path.stat().st_mtime_ns)
                for path in self.home.rglob('*') if path.is_file()}

    def test_sync_refuses_root(self):
        for action in (manage.sync, manage.unsync):
            with self.subTest(action=action.__name__):
                with mock.patch.object(manage.os, 'geteuid', return_value=0):
                    with self.assertRaisesRegex(ValueError, 'desktop user'):
                        action(self.home)

    def test_sync_creates_the_block_and_defaults(self):
        self.tool('niri', 'exit 0')
        manage.sync(self.home)
        self.assertEqual((self.home / '.config/niri/config.kdl').read_text(), manage.block() + '\n')
        for name in ('config.kdl', 'window-management.kdl'):
            self.assertEqual((self.home / '.config/niri/omarchy' / name).read_text(),
                             (self.root / 'niri' / name).read_text())
        version = json.loads((self.root / 'manifest.json').read_text())['version']
        self.assertEqual((self.home / '.config/niri/omarchy/.version').read_text(), version + '\n')
        for name in ('input', 'outputs', 'bindings'):
            self.assertEqual((self.home / ('.config/niri/' + name + '.kdl')).read_text(),
                             '// Personal Niri overrides.\n')
        self.assertEqual((self.home / '.config/omarchy/niri-style.json').read_text(),
                         (self.root / 'overlay/config/omarchy/niri-style.json').read_text())
        self.assertTrue((self.home / '.config/niri/omarchy-theme.kdl').is_file())

    def test_sync_prepends_the_block_to_an_existing_config(self):
        self.tool('niri', 'exit 0')
        config = self.home / '.config/niri/config.kdl'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('layout { gaps 20 }\n')
        manage.sync(self.home)
        self.assertEqual(config.read_text(), manage.block() + '\n\nlayout { gaps 20 }\n')
        self.assertEqual(config.with_name('config.kdl.pre-omarchy-niri').read_text(), 'layout { gaps 20 }\n')
        before = self.snapshots()
        manage.sync(self.home)  # a second run with unchanged sources rewrites nothing
        self.assertEqual(self.snapshots(), before)

    def test_sync_migrates_the_03_absolute_includes(self):
        self.tool('niri', 'exit 0')
        config = self.home / '.config/niri/config.kdl'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('// managed header\n'
                          'include "/var/lib/omarchy-niri/current/default/niri/config.kdl"\n'
                          'include "/var/lib/omarchy-niri/current/default/niri/window-management.kdl"\n'
                          'include optional=true "~/.config/niri/omarchy-theme.kdl"\n'
                          'layout { gaps 20 }\n')
        manage.sync(self.home)
        self.assertEqual(config.read_text(),
                         '// managed header\n' + manage.block() + '\n'
                         'include optional=true "~/.config/niri/omarchy-theme.kdl"\n'
                         'layout { gaps 20 }\n')

    def test_sync_migrates_the_02_symlink_includes(self):
        self.tool('niri', 'exit 0')
        config = self.home / '.config/niri/config.kdl'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('include ~/.config/niri/omarchy.kdl\n'
                          'include ~/.config/niri/window-management.kdl\n'
                          'layout { gaps 20 }\n')
        manage.sync(self.home)
        self.assertEqual(config.read_text(), manage.block() + '\nlayout { gaps 20 }\n')

    def test_sync_rolls_back_when_niri_rejects_the_config(self):
        self.tool('niri', 'echo "config error" >&2; exit 1')
        config = self.home / '.config/niri/config.kdl'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('layout { gaps 20 }\n')
        managed = self.home / '.config/niri/omarchy/config.kdl'
        managed.parent.mkdir(parents=True)
        managed.write_text('old defaults\n')
        with self.assertRaisesRegex(ValueError, 'config error'):
            manage.sync(self.home)
        self.assertEqual(config.read_text(), 'layout { gaps 20 }\n')
        self.assertEqual(managed.read_text(), 'old defaults\n')
        self.assertFalse((self.home / '.config/niri/input.kdl').exists())
        self.assertFalse((self.home / '.config/niri/omarchy/.version').exists())

    def test_unsync_strips_only_the_block(self):
        config = self.home / '.config/niri/config.kdl'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(manage.block() + '\nlayout { gaps 20 }\n')
        for name in ('input', 'outputs', 'bindings'):
            (self.home / ('.config/niri/' + name + '.kdl')).write_text('my overrides\n')
        (self.home / '.config/niri/omarchy-theme.kdl').write_text('edited theme\n')
        (self.home / '.config/omarchy').mkdir(parents=True)
        (self.home / '.config/omarchy/niri-style.json').write_text('{"radius": 0}\n')
        (self.home / '.config/niri/omarchy').mkdir()
        (self.home / '.config/niri/omarchy/config.kdl').write_text('defaults\n')
        manage.unsync(self.home)
        self.assertEqual(config.read_text(), 'layout { gaps 20 }\n')
        self.assertFalse((self.home / '.config/niri/omarchy').exists())
        for name in ('input', 'outputs', 'bindings'):
            self.assertEqual((self.home / ('.config/niri/' + name + '.kdl')).read_text(), 'my overrides\n')
        self.assertEqual((self.home / '.config/niri/omarchy-theme.kdl').read_text(), 'edited theme\n')
        self.assertEqual((self.home / '.config/omarchy/niri-style.json').read_text(), '{"radius": 0}\n')


if __name__ == "__main__":
    unittest.main()
