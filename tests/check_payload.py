"""Check distribution inputs; --base also reconstructs and verifies the runtime."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, help='Clean checkout of the pinned Omarchy base')
args = parser.parse_args()
manifest = json.loads((root / 'manifest.json').read_text())
expected = set()
for name, entry in manifest['files'].items():
  assert isinstance(entry['baseSha256'], list) and entry['baseSha256'], name
  if entry.get('patch'):
    path = root / 'patches' / (name + '.patch')
    expected.add(str(path.relative_to(root)))
    patch = path.read_text()
    assert patch.startswith('--- a/' + name + '\n+++ b/' + name + '\n'), name
    assert patch.count('\n--- a/') == 0, name
    continue
  path = root / 'payload' / name
  expected.add(str(path.relative_to(root)))
  data = path.read_bytes()
  assert hashlib.sha256(data).hexdigest() == entry['sha256'], name
  if data.startswith(b'#!/bin/bash'):
    subprocess.run(['bash', '-n', str(path)], check=True)
subprocess.run(['bash', '-n', str(root / 'install.sh')], check=True)
actual = {str(p.relative_to(root)) for directory in ('payload', 'patches')
  for p in (root / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual == expected, actual.symmetric_difference(expected)
print('PASS:', len(actual), 'replacement/patch inputs and shell syntax')

if args.base:
  spec = importlib.util.spec_from_file_location('manager', root / 'manage.py')
  manager = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(manager)
  with tempfile.TemporaryDirectory(prefix='niri-payload-') as temporary:
    stage = Path(temporary)
    for name, entry in manifest['files'].items():
      original = args.base / name
      data = original.read_bytes() if original.is_file() else None
      digest = hashlib.sha256(data).hexdigest() if data is not None else None
      assert digest in entry['baseSha256'], 'Wrong upstream base: ' + name
      if data is not None:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    manager.apply_payload(stage, manifest)
    for path in (stage / 'bin').iterdir():
      if path.read_bytes().startswith(b'#!/bin/bash'):
        subprocess.run(['bash', '-n', str(path)], check=True)
  print('PASS:', len(manifest['files']), 'reconstructed runtime hashes and shell syntax')
