"""Check the distributable files and Bash syntax without Linux UI dependencies."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'manifest.json').read_text())
for name, entry in manifest['files'].items():
  path = root / 'payload' / name
  data = path.read_bytes()
  assert hashlib.sha256(data).hexdigest() == entry['sha256'], name
  assert isinstance(entry['baseSha256'], list) and entry['baseSha256'], name
  if data.startswith(b'#!/bin/bash'):
    subprocess.run(['bash', '-n', str(path)], check=True)
subprocess.run(['bash', '-n', str(root / 'install.sh')], check=True)
actual = {str(p.relative_to(root / 'payload')) for p in (root / 'payload').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual == set(manifest['files']), actual.symmetric_difference(manifest['files'])
print('PASS:', len(actual), 'payload hashes, file inventory and Bash syntax')
