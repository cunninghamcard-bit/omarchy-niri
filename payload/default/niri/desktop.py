"""Niri display and device controls used by the retained Omarchy menus."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from bridge import atomic_write, request, theme

ROOT = Path.home() / '.config/niri'
STATE = Path.home() / '.local/state/omarchy/niri'


def run(*args, **kwargs):
  return subprocess.run(args, check=True, **kwargs)


def action(name, **values):
  return request({'Action': {name: values}})


def settings():
  path = STATE / 'desktop.json'
  return json.loads(path.read_text()) if path.exists() else {}


def save(data):
  atomic_write(STATE / 'desktop.json', json.dumps(data, indent=2) + '\n')


def config_write(name, content):
  """Reject invalid generated config before allowing it to replace live settings."""
  check = ROOT / '.omarchy-check.kdl'
  atomic_write(check, content)
  try:
    run('niri', 'validate', '--config', str(check), stdout=subprocess.DEVNULL)
    atomic_write(ROOT / name, content)
  finally:
    check.unlink(missing_ok=True)


def outputs_write(data):
  lines = []
  for name, values in data.get('outputs', {}).items():
    lines.append('output ' + json.dumps(name) + ' {')
    if values.get('off'):
      lines.append('  off')
    if 'scale' in values:
      lines.append('  scale ' + str(values['scale']))
    lines.append('}')
  config_write('omarchy-outputs.kdl', '\n'.join(lines) + '\n')
  save(data)


def set_output(name, enabled):
  outputs = request('Outputs')
  if name not in outputs:
    raise ValueError('Unknown output: ' + name)
  if not enabled and outputs[name].get('logical') and sum(bool(o.get('logical')) for o in outputs.values()) <= 1:
    raise ValueError('Refusing to disable the last output')
  data = settings()
  data.setdefault('outputs', {}).setdefault(name, {})['off'] = not enabled
  outputs_write(data)


def scale(value=None):
  output = request('FocusedOutput')
  if not output or not output.get('logical'):
    raise ValueError('No focused output')
  current = output['logical']['scale']
  if value is None:
    print(current)
    return
  presets = [1, 1.25, 1.6, 2, 3, 4]
  if value == 'up':
    target = next((v for v in presets if v > current + 0.01), presets[-1])
  elif value == 'down':
    target = next((v for v in reversed(presets) if v < current - 0.01), presets[0])
  else:
    target = float(value)
  if not 0.5 <= target <= 5:
    raise ValueError('Scale must be between 0.5 and 5')
  data = settings()
  data.setdefault('outputs', {}).setdefault(output['name'], {})['scale'] = target
  outputs_write(data)


def input_devices(kind):
  if kind not in ('touchpad', 'touchscreen'):
    raise ValueError('Expected touchpad or touchscreen')
  for device in sorted(Path('/sys/class/input').glob('event*')):
    props = subprocess.run(['udevadm', 'info', '--query=property', '--path=' + str(device)], capture_output=True, text=True)
    if 'ID_INPUT_' + kind.upper() + '=1' in props.stdout.splitlines():
      name = (device / 'device/name').read_text().strip()
      yield name


def enabled_action(value, current):
  if value not in ('on', 'off', 'toggle'):
    raise ValueError('Expected on, off or toggle')
  return not current if value == 'toggle' else value == 'on'


def input_toggle(kind, value='toggle'):
  if not list(input_devices(kind)):
    raise ValueError('No ' + kind + ' device found')
  data = settings()
  inputs = data.setdefault('input', {})
  enabled = enabled_action(value, not inputs.get(kind, False))
  inputs[kind] = not enabled
  config_write('omarchy-input.kdl', 'input {\n' + '\n'.join(
    '  ' + ('touch' if k == 'touchscreen' else k) + ' { off; }' for k, off in inputs.items() if off) + '\n}\n')
  save(data)
  run('omarchy-osd', '-i', 'touchpad' if kind == 'touchpad' else 'touch', '-m', kind.capitalize() + (' enabled' if enabled else ' disabled'))


def internal(value='toggle'):
  output = next((o for o in request('Outputs').values() if re.match(r'^(eDP|LVDS|DSI)-', o['name'])), None)
  if output is None:
    raise ValueError('No internal display')
  set_output(output['name'], enabled_action(value, bool(output.get('logical'))))


def clamshell(value=None):
  outputs = request('Outputs')
  laptop = next((o for o in outputs.values() if re.match(r'^(eDP|LVDS|DSI)-', o['name'])), None)
  if laptop is None:
    return
  closed = value == 'close' if value else any('closed' in p.read_text() for p in Path('/proc/acpi/button/lid').glob('*/state'))
  external = any(o.get('logical') for o in outputs.values() if o is not laptop)
  marker = Path(os.environ['XDG_RUNTIME_DIR']) / 'omarchy-niri-lid-disabled'
  if closed and external and laptop.get('logical'):
    request({'Output': {'output': laptop['name'], 'action': 'Off'}})
    atomic_write(marker, laptop['name'])
  elif marker.exists() and (not closed or not external):
    request({'Output': {'output': laptop['name'], 'action': 'On'}})
    marker.unlink(missing_ok=True)


def mirror(value='toggle'):
  active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'omarchy-niri-mirror.service']).returncode == 0
  if not enabled_action(value, active):
    subprocess.run(['systemctl', '--user', 'stop', 'omarchy-niri-mirror.service'])
    return
  outputs = [o for o in request('Outputs').values() if o.get('logical')]
  source = request('FocusedOutput')
  target = next((o for o in outputs if o['name'] != source['name']), None)
  if target is None:
    raise ValueError('Connect a second display before mirroring')
  subprocess.run(['systemctl', '--user', 'stop', 'omarchy-niri-mirror.service'])
  run('systemd-run', '--user', '--collect', '--unit=omarchy-niri-mirror', 'wl-mirror', '--fullscreen', '--fullscreen-output', target['name'], source['name'])


def window_width(mode):
  window = request('FocusedWindow')
  if not window:
    raise ValueError('No focused window')
  key = hashlib.sha256((window.get('app_id') or window.get('title') or str(window['id'])).encode()).hexdigest()
  path = STATE / 'widths' / (key + '.json')
  if mode == 'save':
    atomic_write(path, json.dumps(window['layout']['window_size'][0]))
  elif mode == 'restore':
    run('niri', 'msg', 'action', 'set-window-width', '--id', str(window['id']), str(int(json.loads(path.read_text()))))
  else:
    raise ValueError('Expected save or restore')


def webcam(size):
  if size not in ('small', 'medium', 'large', 'smaller', 'larger'):
    raise ValueError('Expected small, medium, large, smaller or larger')
  window = next((w for w in request('Windows') if (w.get('app_id') or '').startswith('WebcamOverlay-')), None)
  if window is None:
    raise ValueError('Webcam overlay has not opened')
  output = request('FocusedOutput')['logical']
  presets = [.12, .18, .25]
  if size in ('smaller', 'larger'):
    current = window['layout']['window_size'][0] / output['width']
    candidates = [v for v in presets if v < current - .01] if size == 'smaller' else [v for v in presets if v > current + .01]
    fraction = (max(candidates) if size == 'smaller' else min(candidates)) if candidates else (presets[0] if size == 'smaller' else presets[-1])
  else:
    fraction = {'small': .12, 'medium': .18, 'large': .25}[size]
  width = round(output['width'] * fraction)
  height = width * 9 // 8
  run('niri', 'msg', 'action', 'set-window-width', '--id', str(window['id']), str(width))
  run('niri', 'msg', 'action', 'set-window-height', '--id', str(window['id']), str(height))
  run('niri', 'msg', 'action', 'move-floating-window', '--id', str(window['id']), '-x', str(max(0, output['width'] - width - 20)), '-y', str(max(0, output['height'] - height - 20)))


def flag(name, value='toggle'):
  data = settings()
  flags = data.setdefault('flags', {})
  if name == 'window-no-gaps':
    path = Path.home() / '.config/omarchy/niri-style.json'
    geometry = json.loads(path.read_text())
    enabled = enabled_action(value, geometry['gaps'] == 0)
    geometry['gaps'] = 0 if enabled else 10
    atomic_write(path, json.dumps(geometry) + '\n')
    theme()
  elif name == 'single-window-aspect-ratio':
    # Niri keeps empty scroll space. An explicit square command resizes only
    # the selected column, without a global auto-fill or single-window rule.
    enabled = enabled_action(value, flags.get(name, False))
    if enabled:
      window_width('save')
      output = request('FocusedOutput')['logical']
      run('niri', 'msg', 'action', 'set-window-width', str(int(output['height'] - 40)))
    else:
      window_width('restore')
  else:
    raise ValueError('Unknown Niri flag: ' + name)
  flags[name] = enabled
  save(data)
  print('on' if enabled else 'off')


def dispatch(op, args):
  if op == 'device':
    found = next(input_devices(args[0]), None)
    if found is None:
      return 1
    print(found)
  else:
    {'input': input_toggle, 'internal': internal, 'mirror': mirror, 'clamshell': clamshell,
     'window-width': window_width, 'webcam': webcam, 'flag': flag}[op](*args)
  return 0
