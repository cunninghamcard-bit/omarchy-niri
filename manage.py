#!/usr/bin/python3
"""Install a Niri replacement layer over the packaged Omarchy runtime.

Package files are never overwritten. A root-owned generation is assembled and
validated before the session pointer changes. Uninstall restores saved files;
conflicting subsequent edits are preserved and reported instead of discarded.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
STATE = Path('/var/lib/omarchy-niri')
PREFIX = Path('/usr/local/lib/omarchy-niri')


def run(*command, **kwargs):
  return subprocess.run(command, check=True, **kwargs)


def digest(path):
  if path.is_symlink():
    return 'link:' + os.readlink(path)
  return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def atomic(path, content, mode=0o644):
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, name = tempfile.mkstemp(prefix='.niri-', dir=path.parent)
  try:
    with os.fdopen(fd, 'w') as stream:
      stream.write(content)
      stream.flush()
      os.fsync(stream.fileno())
    os.chmod(name, mode)
    os.replace(name, path)
  finally:
    if os.path.exists(name):
      os.unlink(name)


def switch(target):
  temporary = STATE / '.next'
  temporary.unlink(missing_ok=True)
  temporary.symlink_to(target)
  temporary.replace(STATE / 'current')


def apply_payload(stage, manifest):
  """Apply replacements and small upstream patches, then verify exact output bytes."""
  for name, entry in manifest['files'].items():
    target = stage / name
    if entry.get('patch'):
      run('git', 'apply', '--no-index', '--whitespace=nowarn', '--include=' + name,
        str(HERE / 'patches' / (name + '.patch')), cwd=stage)
    else:
      target.parent.mkdir(parents=True, exist_ok=True)
      target.unlink(missing_ok=True)
      shutil.copy2(HERE / 'payload' / name, target)
    if digest(target) != entry['sha256']:
      raise ValueError('Damaged extension payload: ' + name)


def copy_runtime(base, stage):
  for name in ('bin', 'shell', 'default', 'config'):
    if not (base / name).is_dir():
      raise ValueError(f'{base} is not an Omarchy runtime: missing {name}')
  manifest = json.loads((HERE / 'manifest.json').read_text())
  for name, entry in manifest['files'].items():
    original = base / name
    actual = hashlib.sha256(original.read_bytes()).hexdigest() if original.is_file() else None
    if actual not in entry['baseSha256']:
      raise ValueError('Unsupported upstream change in ' + name + '; current generation will be retained')
  shutil.copytree(base, stage, symlinks=True, ignore=shutil.ignore_patterns('.git', 'test', 'node_modules'))
  # Packaged command symlinks point into /usr/bin; materialize before patching
  # so both patching and later package upgrades leave the base untouched.
  for path in (stage / 'bin').iterdir():
    if path.is_symlink() and path.is_file():
      content, mode = path.read_bytes(), path.stat().st_mode & 0o777
      path.unlink(); path.write_bytes(content); path.chmod(mode)
  apply_payload(stage, manifest)
  run('niri', 'validate', '--config', str(stage / 'default/niri/config.kdl'))
  for directory, dirs, files in os.walk(stage):
    os.chown(directory, 0, 0)
    for name in dirs + files:
      os.chown(Path(directory) / name, 0, 0, follow_symlinks=False)


class Changes:
  def __init__(self, directory):
    self.directory = directory
    self.file = directory / 'changes.json'
    self.items = json.loads(self.file.read_text()) if self.file.exists() else {}

  def remember(self, path):
    key = str(path)
    if key in self.items:
      return
    if path.is_dir() and not path.is_symlink():
      raise ValueError('Managed file is a directory: ' + str(path))
    item = {'before': digest(path), 'mode': None}
    if path.exists() or path.is_symlink():
      backup = self.directory / 'backups' / key.lstrip('/')
      backup.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(path, backup, follow_symlinks=False)
      item['mode'] = path.lstat().st_mode & 0o777
      item['uid'], item['gid'] = path.lstat().st_uid, path.lstat().st_gid
    self.items[key] = item
    self.flush()

  def write(self, path, text, mode=0o644):
    self.remember(path)
    self.items[str(path)]['after'] = hashlib.sha256(text.encode()).hexdigest()
    self.flush()
    atomic(path, text, mode)

  def link(self, path, target):
    self.remember(path)
    self.items[str(path)]['after'] = 'link:' + str(target)
    self.flush()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    path.symlink_to(target)

  def record(self, path):
    self.items[str(path)]['after'] = digest(path)
    self.flush()

  def conflicts(self):
    return [key for key, item in self.items.items()
      if digest(Path(key)) not in (item.get('after', item['before']), item['before'])]

  def flush(self):
    atomic(self.file, json.dumps(self.items, indent=2) + '\n', 0o600)

  def restore(self, force=False):
    conflicts = self.conflicts()
    if conflicts and not force:
      return conflicts
    conflicts = []
    for key, item in reversed(list(self.items.items())):
      path = Path(key)
      if not force and digest(path) not in (item.get('after', item['before']), item['before']):
        conflicts.append(key)
        continue
      path.unlink(missing_ok=True)
      if item['before'] is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.directory / 'backups' / key.lstrip('/'), path, follow_symlinks=False)
        os.chown(path, item['uid'], item['gid'], follow_symlinks=False)
    return conflicts


def as_user(user, runtime, command):
  account = pwd.getpwnam(user)
  return run('runuser', '-u', user, '--', 'env', 'HOME=' + account.pw_dir,
    'OMARCHY_PATH=' + str(runtime), 'PATH=' + str(runtime / 'bin') + ':/usr/local/bin:/usr/bin',
    'XDG_RUNTIME_DIR=/run/user/' + str(account.pw_uid), *command)


def configure_user(user, runtime, changes):
  account = pwd.getpwnam(user)
  home = Path(account.pw_dir)
  directory = home / '.config/niri'
  created = not directory.exists()
  directory.mkdir(parents=True, exist_ok=True)
  if created: os.chown(directory, account.pw_uid, account.pw_gid)
  # The replacement owns only named files. Personal overrides and the entire
  # former config are retained; the original entry point is recoverable.
  templates = {'config.kdl': runtime / 'config/niri/config.kdl',
    'omarchy.kdl': runtime / 'default/niri/config.kdl',
    'window-management.kdl': runtime / 'default/niri/window-management.kdl'}
  for name, source in templates.items():
    path = directory / name
    if name == 'config.kdl':
      changes.write(path, source.read_text())
    else:
      target = STATE / 'current/default/niri' / source.name
      changes.link(path, target)
    os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
  for name in ('input.kdl', 'outputs.kdl', 'bindings.kdl'):
    path = directory / name
    if not path.exists():
      changes.write(path, '// Personal Niri overrides.\n')
      os.chown(path, account.pw_uid, account.pw_gid)
  style = home / '.config/omarchy/niri-style.json'
  if not style.exists():
    changes.write(style, (runtime / 'config/omarchy/niri-style.json').read_text())
    os.chown(style, account.pw_uid, account.pw_gid)
  theme_file = directory / 'omarchy-theme.kdl'
  changes.remember(theme_file)
  as_user(user, runtime, ['omarchy-niri', 'theme'])
  changes.record(theme_file)
  as_user(user, runtime, ['niri', 'validate', '--config', str(directory / 'config.kdl')])


def install(user, base, dependencies=True):
  account = pwd.getpwnam(user)
  if account.pw_uid == 0:
    raise ValueError('Specify the non-root desktop account with --user')
  if (STATE / 'installed.json').exists():
    raise ValueError('Already installed. Use refresh to update the replacement.')
  if (STATE / 'transaction.json').exists():
    interrupted = json.loads((STATE / 'transaction.json').read_text())
    conflicts = Changes(STATE).restore()
    if conflicts:
      raise ValueError('Interrupted install has subsequent edits: ' + ', '.join(conflicts))
    if interrupted.get('previous'):
      switch(interrupted['previous'])
    else:
      (STATE / 'current').unlink(missing_ok=True)
    shutil.rmtree(Path(interrupted['generation']), ignore_errors=True)
    if HERE != PREFIX:
      shutil.rmtree(PREFIX, ignore_errors=True)
    (STATE / 'transaction.json').unlink()
  if PREFIX.exists() and HERE != PREFIX:
    raise ValueError('Existing installation files: ' + str(PREFIX))
  if dependencies:
    run(str(base / 'bin/omarchy-pkg-add'), 'niri', 'xwayland-satellite', 'xdg-desktop-portal-gnome',
      'xdg-desktop-portal-gtk', 'wf-recorder', 'gammastep', 'wl-mirror', 'python', 'git', 'jq', 'slurp', 'grim', 'wl-clipboard',
      env={**os.environ, 'OMARCHY_PATH': str(base), 'PATH': str(base / 'bin') + ':' + os.environ['PATH']})
  generation = STATE / 'generations' / str(time.time_ns())
  generation.parent.mkdir(parents=True, exist_ok=True)
  changes = Changes(STATE)
  previous = os.readlink(STATE / 'current') if (STATE / 'current').is_symlink() else None
  try:
    copy_runtime(base, generation)
    atomic(STATE / 'transaction.json', json.dumps({'operation': 'install', 'generation': str(generation), 'previous': previous}))
    switch(generation)
    configure_user(user, generation, changes)
    pam = Path('/etc/pam.d/omarchy-lock-password')
    if not pam.exists():
      helper = (generation / 'bin/omarchy-apply-lock').read_text()
      content = helper.split("<<'EOF'\n", 1)[1].split('\nEOF', 1)[0] + '\n'
      changes.write(pam, content)
    changes.write(Path('/etc/omarchy.conf'), 'export OMARCHY_PATH="$(readlink -f /var/lib/omarchy-niri/current)"\n')
    desktop = (generation / 'default/wayland-sessions/omarchy-niri.desktop').read_text()
    changes.write(Path('/usr/local/share/wayland-sessions/omarchy-niri.desktop'), desktop)
    # The existing Omarchy session name also launches Niri, including SDDM's
    # remembered selection. The packaged desktop remains available on restore.
    changes.write(Path('/usr/local/share/wayland-sessions/omarchy.desktop'), desktop)
    changes.write(Path('/etc/sddm.conf.d/90-omarchy-niri.conf'), '[Autologin]\nSession=omarchy-niri.desktop\n')
    sudoers = 'Defaults secure_path="/var/lib/omarchy-niri/current/bin:/usr/local/sbin:/usr/local/bin:/usr/bin"\n'
    with tempfile.NamedTemporaryFile(mode='w') as file:
      file.write(sudoers); file.flush(); run('visudo', '-cf', file.name)
    changes.write(Path('/etc/sudoers.d/omarchy-dev-path'), sudoers, 0o440)
    if HERE != PREFIX:
      if PREFIX.exists():
        raise ValueError('Refusing to overwrite existing ' + str(PREFIX))
      shutil.copytree(HERE, PREFIX, ignore=shutil.ignore_patterns('.git', '__pycache__', 'test-artifacts'))
    changes.write(Path('/usr/local/bin/omarchy-niri-extension'), '#!/bin/bash\nmanager=/usr/local/lib/omarchy-niri/manage.py\n[[ -f $manager ]] || manager=/usr/local/lib/omarchy-niri-previous/manage.py\nexec python3 "$manager" "$@"\n', 0o755)
    for name in ('10-omarchy-hyprland-reload-pause.hook', '90-omarchy-hyprland-reload-resume.hook'):
      changes.link(Path('/etc/pacman.d/hooks') / name, '/dev/null')
    changes.write(Path('/etc/pacman.d/hooks/95-omarchy-niri.hook'), '''[Trigger]
Operation = Upgrade
Type = Package
Target = omarchy
Target = try-omarchy-runtime

[Action]
Description = Reapply the Niri replacement (retain previous generation on failure)
When = PostTransaction
Exec = /usr/local/bin/omarchy-niri-extension refresh
''')
    owner = uuid.uuid4().hex
    atomic(PREFIX / '.omarchy-niri-owner', owner + '\n', 0o600)
    atomic(STATE / 'installed.json', json.dumps({'owner': owner, 'user': user, 'base': str(base), 'generation': str(generation),
      'version': json.loads((HERE / 'manifest.json').read_text())['version']}, indent=2) + '\n')
  except Exception:
    changes.restore(force=True)
    shutil.rmtree(generation, ignore_errors=True)
    if HERE != PREFIX: shutil.rmtree(PREFIX, ignore_errors=True)
    (STATE / 'transaction.json').unlink(missing_ok=True)
    if previous:
      switch(previous)
    else:
      (STATE / 'current').unlink(missing_ok=True)
    raise
  (STATE / 'transaction.json').unlink(missing_ok=True)
  print('Installed. Log out and select Omarchy (Niri), or reboot. Restore: sudo omarchy-niri-extension uninstall')


def recover_refresh():
  """Complete or undo an interrupted publication before the next mutation."""
  global HERE
  journal = STATE / 'refresh-transaction.json'
  if not journal.exists():
    return
  transaction = json.loads(journal.read_text())
  state = json.loads((STATE / 'installed.json').read_text())
  staged = PREFIX.with_name(PREFIX.name + '-next')
  archive = PREFIX.with_name(PREFIX.name + '-previous')
  if state['generation'] == transaction['generation']:
    switch(state['generation'])
    shutil.rmtree(archive, ignore_errors=True)
  else:
    if archive.exists():
      shutil.rmtree(PREFIX, ignore_errors=True)
      archive.rename(PREFIX)
      if HERE == archive:
        HERE = PREFIX
    switch(transaction['previous'])
    shutil.rmtree(transaction['generation'], ignore_errors=True)
  shutil.rmtree(staged, ignore_errors=True)
  journal.unlink()


def refresh(base=None):
  state = json.loads((STATE / 'installed.json').read_text())
  base = base or Path(state['base'])
  generation = STATE / 'generations' / str(time.time_ns())
  try:
    copy_runtime(base, generation)
    # Personal configuration is never rewritten during upgrades.
    home = Path(pwd.getpwnam(state['user']).pw_dir)
    config = (home / '.config/niri/config.kdl').read_text()
    config = config.replace('~/.config/niri/omarchy.kdl', str(generation / 'default/niri/config.kdl'))
    config = config.replace('~/.config/niri/window-management.kdl', str(generation / 'default/niri/window-management.kdl'))
    checked = generation / 'user-check.kdl'
    checked.write_text(config); checked.chmod(0o644)
    as_user(state['user'], generation, ['niri', 'validate', '--config', str(checked)])
    checked.unlink()
  except Exception:
    shutil.rmtree(generation, ignore_errors=True)
    atomic(STATE / 'refresh-failed', 'The installed Omarchy version needs an updated Niri patch. Previous generation retained.\n')
    raise
  previous = state['generation']
  journal = STATE / 'refresh-transaction.json'
  atomic(journal, json.dumps({'previous': previous, 'generation': str(generation)}), 0o600)
  old_state = json.dumps(state, indent=2) + '\n'
  staged = PREFIX.with_name(PREFIX.name + '-next')
  archive = PREFIX.with_name(PREFIX.name + '-previous')
  try:
    if HERE != PREFIX:
      shutil.rmtree(staged, ignore_errors=True)
      shutil.copytree(HERE, staged, ignore=shutil.ignore_patterns('.git', '__pycache__', 'test-artifacts'))
      shutil.rmtree(archive, ignore_errors=True)
      PREFIX.rename(archive)
      staged.rename(PREFIX)
    state.setdefault('owner', uuid.uuid4().hex)
    atomic(PREFIX / '.omarchy-niri-owner', state['owner'] + '\n', 0o600)
    switch(generation)
    state['generation'] = str(generation)
    state['version'] = json.loads((HERE / 'manifest.json').read_text())['version']
    atomic(STATE / 'installed.json', json.dumps(state, indent=2) + '\n')
  except Exception:
    # The journal records enough state for the same recovery path used after
    # a process interruption. Restore old metadata first so recovery takes the
    # rollback branch even if failure happened after publication.
    try:
      atomic(STATE / 'installed.json', old_state)
    finally:
      recover_refresh()
    raise
  if HERE != PREFIX:
    shutil.rmtree(archive)
  journal.unlink()
  (STATE / 'refresh-failed').unlink(missing_ok=True)
  print('Replacement refreshed. Log out and in to load this generation.')


def uninstall():
  installed = STATE / 'installed.json'
  if not installed.is_file():
    raise ValueError('No installed replacement; nothing will be removed')
  state = json.loads(installed.read_text())
  marker = PREFIX / '.omarchy-niri-owner'
  if not state.get('owner') or not marker.is_file() or marker.read_text().strip() != state['owner']:
    raise ValueError('Installation ownership cannot be verified; nothing will be removed')
  if (STATE / 'transaction.json').exists():
    raise ValueError('Incomplete installation; recover it before uninstalling')
  changes = Changes(STATE)
  conflicts = changes.conflicts()
  for key in conflicts:
    path = Path(key)
    if path.exists() or path.is_symlink():
      saved = STATE / 'preserved-edits' / key.lstrip('/')
      saved.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(path, saved, follow_symlinks=False)
  changes.restore(force=True)
  (STATE / 'current').unlink(missing_ok=True)
  if PREFIX.is_symlink(): PREFIX.unlink()
  elif PREFIX.exists(): shutil.rmtree(PREFIX)
  archive = STATE.with_name('omarchy-niri-uninstalled-' + str(time.time_ns()))
  STATE.rename(archive)
  print('Original session restored. Reboot. Packages retained; backups and subsequent edits saved at ' + str(archive))


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('action', choices=('install', 'refresh', 'uninstall', 'status'))
  parser.add_argument('--user', default=os.environ.get('SUDO_USER'))
  parser.add_argument('--base', type=Path)
  parser.add_argument('--skip-packages', action='store_true', help='For provisioned test environments only')
  args = parser.parse_args()
  if args.action == 'status':
    print((STATE / 'installed.json').read_text() if (STATE / 'installed.json').exists() else 'Not installed')
    if (STATE / 'refresh-transaction.json').exists():
      print('Interrupted update: run sudo omarchy-niri-extension refresh to recover'); return 1
    if (STATE / 'refresh-failed').exists():
      print((STATE / 'refresh-failed').read_text()); return 1
    return 0
  if os.geteuid() != 0:
    parser.error('Run with sudo; installation also requires --user USER')
  STATE.mkdir(parents=True, exist_ok=True)
  with (STATE / 'operation.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    recover_refresh()
    if args.action == 'install':
      if not args.user: parser.error('--user is required')
      install(args.user, args.base or Path('/usr/share/omarchy'), not args.skip_packages)
    elif args.action == 'refresh': refresh(args.base)
    else: uninstall()
  return 0


if __name__ == '__main__':
  try:
    sys.exit(main())
  except (OSError, ValueError, subprocess.SubprocessError) as error:
    print('omarchy-niri-extension: ' + str(error), file=sys.stderr)
    sys.exit(1)
