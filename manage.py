#!/usr/bin/env python3
"""Build a private runtime, then publish runtime, installer and metadata together."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from compat import prepare

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('OMARCHY_NIRI_STATE', '/var/lib/omarchy-niri'))
BASE = Path(os.environ.get('OMARCHY_NIRI_BASE', '/usr/share/omarchy'))
PREFIX = Path('/usr/local/lib/omarchy-niri')  # Only used when retiring a 0.2 installation.
SYSTEM = Path('/')
DEPENDENCIES = ('niri', 'xwayland-satellite', 'xdg-desktop-portal-gnome',
                'xdg-desktop-portal-gtk', 'wf-recorder', 'gammastep', 'wl-mirror',
                'python', 'git', 'jq', 'slurp', 'grim', 'wl-clipboard')
MARKER = '# Managed by omarchy-niri'


def system(path):
    return SYSTEM / path.lstrip('/')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def atomic(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def digest(path):
    if path.is_symlink():
        return 'link:' + os.readlink(path)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.exists():
        raise ValueError('Managed path is not a file: ' + str(path))
    return None


def switch(runtime):
    """A single rename commits the runtime, its manager, and its release metadata."""
    target = STATE / '.current-next'
    target.unlink(missing_ok=True)
    target.symlink_to(runtime)
    os.replace(target, STATE / 'current')


class Changes:
    """Keep the original contents and preserve later user edits when restoring."""
    def __init__(self, directory):
        self.directory = directory
        self.file = directory / 'changes.json'
        self.items = json.loads(self.file.read_text()) if self.file.exists() else {}

    def flush(self):
        atomic(self.file, json.dumps(self.items, indent=2) + '\n')

    def remember(self, path):
        key = str(path)
        if key in self.items:
            return
        before = digest(path)
        item = {'before': before}
        if before is not None:
            info = path.lstat()
            item.update(mode=info.st_mode & 0o777, uid=info.st_uid, gid=info.st_gid)
            backup = self.directory / 'backups' / key.lstrip('/')
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup, follow_symlinks=False)
        self.items[key] = item
        self.flush()

    def record(self, path):
        self.items[str(path)]['after'] = digest(path)
        self.flush()

    def write(self, path, text, mode=0o644):
        self.remember(path)
        atomic(path, text, mode)
        self.record(path)

    def link(self, path, target):
        self.remember(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name('.' + path.name + '.niri-next')
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target)
        os.replace(temporary, path)
        self.record(path)

    def _settle(self, key, item):
        path = Path(key)
        actual = digest(path)
        if actual == item['before']:
            if actual is not None:
                if not path.is_symlink():
                    path.chmod(item['mode'])
                os.chown(path, item['uid'], item['gid'], follow_symlinks=False)
            return
        if actual not in (None, item.get('after')):
            saved = self.directory / 'preserved' / uuid.uuid4().hex / key.lstrip('/')
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved, follow_symlinks=False)
        path.unlink(missing_ok=True)
        if item['before'] is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.directory / 'backups' / key.lstrip('/'), path, follow_symlinks=False)
            os.chown(path, item['uid'], item['gid'], follow_symlinks=False)

    def _preflight(self, key, item):
        digest(Path(key))
        if item['before'] is not None:
            backup = self.directory / 'backups' / key.lstrip('/')
            if digest(backup) != item['before']:
                raise ValueError('Original backup is missing or changed: ' + key)

    def restore(self):
        # Preflight every path before changing anything: a directory is not an editable file.
        for key, item in self.items.items():
            self._preflight(key, item)
        for key, item in reversed(list(self.items.items())):
            self._settle(key, item)

    def release(self, path):
        """Stop managing one path the way uninstall restores it, then drop it from the ledger."""
        key = str(path)
        item = self.items.get(key)
        if item is None:
            return
        self._preflight(key, item)
        self._settle(key, item)
        del self.items[key]
        self.flush()


class Transaction:
    def __init__(self):
        self.original = Changes(STATE)
        self.operation = Changes(STATE / 'pending')

    def check(self, path):
        previous = self.original.items.get(str(path))
        if previous and digest(path) not in (previous['before'], previous.get('after', previous['before'])):
            raise ValueError('Managed file was edited; left untouched: ' + str(path))

    def write(self, path, text, mode=0o644):
        self.check(path)
        self.original.remember(path)
        self.operation.write(path, text, mode)
        self.original.record(path)

    def link(self, path, target):
        self.check(path)
        self.original.remember(path)
        self.operation.link(path, target)
        self.original.record(path)

    def remember(self, path):
        self.original.remember(path)
        self.operation.remember(path)

    def record(self, path):
        self.operation.record(path)
        self.original.record(path)

    def release(self, path):
        self.original.release(path)
        self.operation.release(path)

    def adopt(self, path):
        """Accept a machine-generated rewrite (omarchy dev link) as managed state again."""
        for ledger in (self.original, self.operation):
            item = ledger.items.get(str(path))
            if item and digest(path) not in (item['before'], item.get('after', item['before'])):
                item['after'] = digest(path)
                ledger.flush()


def release():
    metadata = STATE / 'current/.extension/release.json'
    if metadata.exists():
        return json.loads(metadata.read_text())
    legacy = STATE / 'installed.json'
    if legacy.exists():
        try:
            result = json.loads(legacy.read_text())
        except PermissionError:
            return {'version': 'legacy', 'user': None}
        result['legacy_owner'] = result.get('owner')
        return result
    return None


def recover():
    pending = STATE / 'pending'
    journal = pending / 'operation.json'
    if not journal.exists():
        # No managed file is written before this journal commits; only its temp file can remain.
        if pending.exists():
            shutil.rmtree(pending)
        return
    info = json.loads(journal.read_text())
    if not (STATE / 'current').is_symlink() or (STATE / 'current').resolve() != Path(info['runtime']).resolve():
        Changes(pending).restore()
        atomic(STATE / 'changes.json', json.dumps(info['changes']) + '\n')
        shutil.rmtree(info['runtime'], ignore_errors=True)
    if (pending / 'preserved').exists():
        pending.rename(STATE / ('operation-' + uuid.uuid4().hex))
    else:
        shutil.rmtree(pending)


def as_user(user, runtime, command):
    account = pwd.getpwnam(user)
    return run('runuser', '-u', user, '--', 'env', 'HOME=' + account.pw_dir,
               'OMARCHY_PATH=' + str(runtime), 'PATH=' + str(runtime / 'bin') + ':/usr/local/bin:/usr/bin',
               'XDG_RUNTIME_DIR=/run/user/' + str(account.pw_uid), *command)


def validate_user(user, runtime):
    """Validate personal overrides against the candidate without changing the active include."""
    account = pwd.getpwnam(user)
    config = Path(account.pw_dir) / '.config/niri/config.kdl'
    text = config.read_text().replace(str(STATE / 'current'), str(runtime))
    # Version 0.2 used these two per-user symlinks into current.
    for name, target in [('omarchy.kdl', 'config.kdl'), ('window-management.kdl', 'window-management.kdl')]:
        text = text.replace('~/.config/niri/' + name, str(runtime / 'default/niri' / target))
    fd, name = tempfile.mkstemp(prefix='.niri-validate-', suffix='.kdl', dir=config.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chown(name, account.pw_uid, account.pw_gid)
        as_user(user, runtime, ['niri', 'validate', '--config', name])
    finally:
        Path(name).unlink(missing_ok=True)


def configure_user(user, runtime, changes):
    account = pwd.getpwnam(user)
    home = Path(account.pw_dir)
    directory = home / '.config/niri'
    for path in (directory, home / '.config/omarchy'):
        if not path.exists():
            path.mkdir(parents=True)
            os.chown(path, account.pw_uid, account.pw_gid)
    config = (runtime / 'config/niri/config.kdl').read_text().replace('/var/lib/omarchy-niri/current', str(STATE / 'current'))
    files = {directory / 'config.kdl': config}
    for name in ('input', 'outputs', 'bindings'):
        path = directory / (name + '.kdl')
        if not path.exists():
            files[path] = '// Personal Niri overrides.\n'
    style = home / '.config/omarchy/niri-style.json'
    if not style.exists():
        files[style] = (runtime / 'config/omarchy/niri-style.json').read_text()
    for path, text in files.items():
        changes.write(path, text)
        os.chown(path, account.pw_uid, account.pw_gid)
    theme = directory / 'omarchy-theme.kdl'
    changes.remember(theme)
    as_user(user, runtime, ['omarchy-niri', 'theme'])
    changes.record(theme)


def sourced(conf):
    """The OMARCHY_PATH a conf file yields to a plain shell, outside any session."""
    result = subprocess.run(['bash', '-c',
                             'unset XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP; . "$1"; printf %s "$OMARCHY_PATH"',
                             'bash', str(conf)], capture_output=True, text=True)
    return result.stdout.strip() or None


def session_conf(default):
    """Only the Niri session points OMARCHY_PATH at the private runtime."""
    current = shlex.quote(str(STATE / 'current'))
    return (MARKER + '. Only the Niri session uses the private runtime.\n'
            'OMARCHY_PATH=' + shlex.quote(default) + '\n'
            'case ":${XDG_CURRENT_DESKTOP:-}:${XDG_SESSION_DESKTOP:-}:" in\n'
            '  *:niri:*) [ -d ' + current + ' ] && OMARCHY_PATH="$(readlink -f ' + current + ')" ;;\n'
            'esac\n'
            'export OMARCHY_PATH\n')


def non_niri_default(changes, conf):
    """The OMARCHY_PATH non-Niri sessions keep: the pre-install value, or an adopted dev link."""
    item = changes.original.items.get(str(conf))
    if conf.exists() and (MARKER in conf.read_text() or not item
                          or digest(conf) != item.get('after', item['before'])):
        return sourced(conf) or str(BASE)
    if item and item['before'] is not None:
        return sourced(changes.original.directory / 'backups' / str(conf).lstrip('/')) or str(BASE)
    return str(BASE)


def configure_system(runtime, changes, autologin=False):
    conf = system('/etc/omarchy.conf')
    default = non_niri_default(changes, conf)
    if not conf.exists() or MARKER not in conf.read_text():
        # omarchy dev link/unlink rewrote or removed this machine-generated file; take it back.
        changes.adopt(conf)
    changes.write(conf, session_conf(default))
    changes.release(system('/etc/sudoers.d/omarchy-dev-path'))
    desktop = (runtime / 'default/wayland-sessions/omarchy-niri.desktop').read_text()
    changes.write(system('/usr/local/share/wayland-sessions/omarchy-niri.desktop'), desktop)
    changes.release(system('/usr/local/share/wayland-sessions/omarchy.desktop'))
    autologin_file = system('/etc/sddm.conf.d/90-omarchy-niri.conf')
    if autologin:
        changes.write(autologin_file, '[Autologin]\nSession=omarchy-niri.desktop\n')
    else:
        changes.release(autologin_file)
    # During a 0.2 migration the old manager remains available until the single pointer commits.
    wrapper = '#!/bin/bash\nmanager="$(readlink -f ' + shlex.quote(str(STATE / 'current/.extension/manage.py')) + ')"\n'
    wrapper += '[[ -f $manager ]] || manager=' + shlex.quote(str(PREFIX / 'manage.py')) + '\nexec python3 "$manager" "$@"\n'
    changes.write(system('/usr/local/bin/omarchy-niri-extension'), wrapper, 0o755)
    # The unmasked hooks run /usr/bin/omarchy-hyprland-reload-guard, a no-op without a running Hyprland.
    for name in ('10-omarchy-hyprland-reload-pause.hook', '90-omarchy-hyprland-reload-resume.hook'):
        changes.release(system('/etc/pacman.d/hooks/' + name))
    changes.write(system('/etc/pacman.d/hooks/95-omarchy-niri.hook'), '''[Trigger]
Operation = Upgrade
Type = Package
Target = omarchy
Target = try-omarchy-runtime

[Action]
Description = Check the Niri adaptation (keep the previous runtime on failure)
When = PostTransaction
Exec = /usr/local/bin/omarchy-niri-extension rebuild
''')
    pam = system('/etc/pam.d/omarchy-lock-password')
    if not pam.exists():
        helper = (runtime / 'bin/omarchy-apply-lock').read_text()
        content = helper.split("<<'EOF'\n", 1)[1].split('\nEOF', 1)[0] + '\n'
        changes.write(pam, content)


def build(user, base, previous, autologin=False):
    runtime = STATE / 'runtimes' / uuid.uuid4().hex
    runtime.parent.mkdir(parents=True, exist_ok=True)
    source = runtime.with_name('.source-' + runtime.name)
    try:
        shutil.copytree(HERE, source, ignore=shutil.ignore_patterns('.git', '__pycache__', 'test-artifacts'))
        report = prepare(base, runtime, source)
        extension = runtime / '.extension'
        source.rename(extension)
        metadata = {'user': user, 'version': json.loads((extension / 'manifest.json').read_text())['version'],
                    'base': str(base), 'built_at': time.time(), 'compatibility': report,
                    'legacy_owner': (previous or {}).get('legacy_owner'), 'autologin': autologin}
        atomic(extension / 'release.json', json.dumps(metadata, indent=2) + '\n', 0o644)
        return runtime
    except BaseException:
        shutil.rmtree(runtime, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(source, ignore_errors=True)


def activate(user, base, previous, dependencies=False, autologin=False):
    autologin = (previous or {}).get('autologin', autologin)
    runtime = build(user, base, previous, autologin)
    pending = STATE / 'pending'
    try:
        pending.mkdir(mode=0o700)
        atomic(pending / 'operation.json', json.dumps({'runtime': str(runtime), 'changes': Changes(STATE).items}))
        if dependencies:
            run(str(base / 'bin/omarchy-pkg-add'), *DEPENDENCIES,
                env={**os.environ, 'OMARCHY_PATH': str(base), 'PATH': str(base / 'bin') + ':' + os.environ['PATH']})
        changes = Transaction()
        if previous is None:
            configure_user(user, runtime, changes)
        configure_system(runtime, changes, autologin)
        validate_user(user, runtime)
        switch(runtime)
    except BaseException:
        recover()
        if (STATE / 'current').resolve() != runtime.resolve():
            shutil.rmtree(runtime, ignore_errors=True)
        raise
    try:
        recover()
        (STATE / 'upgrade-failed.txt').unlink(missing_ok=True)
    except OSError as error:
        print('Runtime committed; cleanup will be retried: ' + str(error), file=sys.stderr)
    print('Niri runtime ready. Log out and back in to use it. Previous runtimes are retained.')


def install(user, base, dependencies=True, autologin=False):
    if release():
        raise ValueError('Already installed; use update.')
    if (STATE / 'ledger').exists():
        raise ValueError('Uninstall the experimental overlayfs version before installing this version.')
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError('Specify your desktop account with --user.')
    activate(user, base, None, dependencies, autologin)


def refresh(base):
    previous = release()
    if not previous:
        raise ValueError('Not installed; use install.')
    try:
        activate(previous['user'], base, previous)
    except Exception as error:
        atomic(STATE / 'upgrade-failed.txt', str(error) + '\n', 0o644)
        raise


def uninstall():
    info = release()
    if not info:
        raise ValueError('Not installed.')
    Changes(STATE).restore()
    marker = PREFIX / '.omarchy-niri-owner'
    if info.get('legacy_owner') and marker.exists() and marker.read_text().strip() == info['legacy_owner']:
        shutil.rmtree(PREFIX)
    archive = STATE.with_name(STATE.name + '-uninstalled-' + str(time.time_ns()))
    STATE.rename(archive)
    print('Original session restored; reboot. Backups and edits: ' + str(archive))


def session_lost():
    """True when the installed runtime is no longer selected by /etc/omarchy.conf."""
    conf = system('/etc/omarchy.conf')
    return not conf.exists() or MARKER not in conf.read_text()


def status():
    info = release()
    print(json.dumps(info, indent=2) if info else 'Niri extension is not installed.')
    failed = STATE / 'upgrade-failed.txt'
    if failed.exists():
        print('Omarchy upgrade needs review; previous runtime retained:\n' + failed.read_text())
        return 1
    if info and session_lost():
        print('The Niri session is not using the runtime: /etc/omarchy.conf was rewritten or removed.')
        print('Fix it with: sudo omarchy-niri-extension update')
    return 0


def notify():
    wanted = json.loads((HERE / 'manifest.json').read_text())['version']
    installed = release()
    if (STATE / 'upgrade-failed.txt').exists():
        run('omarchy-notification-send', 'Omarchy Niri',
            'Omarchy compatibility review needed. The previous Niri runtime is retained.',
            '--exec', 'omarchy-launch-floating-terminal-with-presentation',
            shlex.quote(str(HERE / 'omarchy-niri-extension')) + ' status')
        return
    if installed and session_lost():
        run('omarchy-notification-send', 'Omarchy Niri',
            'The Niri session is not using the runtime. Click to update it',
            '--exec', 'omarchy-launch-floating-terminal-with-presentation',
            'sudo ' + shlex.quote(str(HERE / 'omarchy-niri-extension')) + ' update')
        return
    if installed and installed['version'] == wanted:
        return
    action = 'update' if installed else 'install'
    run('omarchy-notification-send', 'Omarchy Niri', 'Click to ' + action + ' the Niri session',
        '--exec', 'omarchy-launch-floating-terminal-with-presentation',
        'sudo ' + shlex.quote(str(HERE / 'omarchy-niri-extension')) + ' ' + action)


@contextlib.contextmanager
def writer():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock = STATE.parent / ('.' + STATE.name + '.lock')
    with lock.open('a') as stream:
        os.chmod(lock, 0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another Niri installation or update is running.') from None
        STATE.mkdir(mode=0o755, exist_ok=True)
        recover()
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'update', 'rebuild', 'refresh', 'uninstall', 'status', 'notify'])
    parser.add_argument('--user', default=os.environ.get('SUDO_USER'))
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--skip-packages', action='store_true')
    parser.add_argument('--autologin', action='store_true',
                        help='write the SDDM autologin selection (kept by later updates)')
    args = parser.parse_args()
    if args.action == 'status':
        return status()
    if args.action == 'notify':
        notify(); return 0
    if os.geteuid() != 0:
        parser.error('Run with sudo.')
    with writer():
        if args.action == 'install':
            if not args.user:
                parser.error('Pass --user NAME for the desktop account.')
            install(args.user, args.base, not args.skip_packages, args.autologin)
        elif args.action == 'uninstall':
            uninstall()
        else:
            refresh(args.base)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('omarchy-niri-extension: ' + str(error), file=sys.stderr)
        sys.exit(1)
