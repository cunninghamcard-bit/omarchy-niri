"""Compare independent simplifications and deliberate removals in temporary copies.

Requires the repository's baseline commit and a clean checkout of pinned Omarchy.
No variant is installed; failure controls never modify the working tree.
"""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'f0eca34c34b1b6ddfed845ca8db56183dec4f87f'
IGNORE = shutil.ignore_patterns('.git', '__pycache__', 'test-artifacts')


def function_source(text, name):
  node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
  lines = text.splitlines(True)
  return ''.join(lines[node.lineno - 1:node.end_lineno])


def replace_function(text, name, replacement):
  original = function_source(text, name)
  return text.replace(original, replacement, 1)


def manifest_write(path):
  file = path / 'manifest.json'
  data = json.loads(file.read_text())
  for name, entry in data['files'].items():
    if not entry.get('patch'):
      entry['sha256'] = hashlib.sha256((path / 'payload' / name).read_bytes()).hexdigest()
  file.write_text(json.dumps(data, indent=2) + '\n')


def measurements(path):
  production = [path / 'manage.py', path / 'install.sh']
  production += [p for folder in ('payload', 'patches') for p in (path / folder).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts]
  control = [p for p in production if p.suffix == '.py']
  trees = [ast.parse(p.read_text()) for p in control]
  return {
    'production_lines': sum(len(p.read_bytes().splitlines()) for p in production),
    'python_lines': sum(len(p.read_text().splitlines()) for p in control),
    'python_functions': sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for t in trees for n in ast.walk(t)),
  }


def materialized_hashes(path, upstream):
  manifest = json.loads((path / 'manifest.json').read_text())
  if not any(e.get('patch') for e in manifest['files'].values()):
    return {name: hashlib.sha256((path / 'payload' / name).read_bytes()).hexdigest() for name in manifest['files']}
  spec = importlib.util.spec_from_file_location('variant_manager', path / 'manage.py')
  manager = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(manager)
  with tempfile.TemporaryDirectory(prefix='niri-ablation-output-') as directory:
    stage = Path(directory)
    for name, entry in manifest['files'].items():
      original = upstream / name
      data = original.read_bytes() if original.is_file() else None
      digest = hashlib.sha256(data).hexdigest() if data is not None else None
      assert digest in entry['baseSha256'], name
      if data is not None:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    manager.apply_payload(stage, manifest)
    return {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in manifest['files']}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--base', type=Path, required=True)
  parser.add_argument('--output', type=Path, default=ROOT / 'test-artifacts/ablation')
  args = parser.parse_args()
  args.output.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='niri-ablation-') as directory:
    area = Path(directory)
    baseline = area / 'baseline'
    baseline.mkdir()
    archive = subprocess.check_output(['git', 'archive', BASELINE], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
      tar.extractall(baseline, filter='data')
    # Apply the same contract suite to every variant, including the baseline.
    # The three patch-specific tests are added only to patch-capable variants.
    shutil.copy2(ROOT / 'tests/test_installer.py', baseline / 'tests/test_installer.py')
    old_manager = (baseline / 'manage.py').read_text()
    new_manager = (ROOT / 'manage.py').read_text()
    original_hashes = materialized_hashes(baseline, args.base)
    variants = [('baseline', baseline, False)]

    def copy(name, source=baseline, negative=False):
      path = area / name
      shutil.copytree(source, path, ignore=IGNORE)
      variants.append((name, path, negative))
      return path

    patches = copy('patches-only')
    patch_manager = replace_function(old_manager, 'copy_runtime',
      function_source(new_manager, 'apply_payload') + '\n\n\n' + function_source(new_manager, 'copy_runtime'))
    (patches / 'manage.py').write_text(patch_manager)
    old_manifest = json.loads((patches / 'manifest.json').read_text())
    current_manifest = json.loads((ROOT / 'manifest.json').read_text())
    shutil.copytree(ROOT / 'patches', patches / 'patches')
    for name, entry in current_manifest['files'].items():
      if entry.get('patch'):
        old_manifest['files'][name]['patch'] = True
        (patches / 'payload' / name).unlink()
    (patches / 'manifest.json').write_text(json.dumps(old_manifest))
    shutil.copy2(ROOT / 'tests/test_payload.py', patches / 'tests/test_payload.py')

    installer = copy('installer-only')
    installer_manager = replace_function(new_manager, 'apply_payload', '')
    installer_manager = replace_function(installer_manager, 'copy_runtime', function_source(old_manager, 'copy_runtime'))
    (installer / 'manage.py').write_text(installer_manager)

    extraction = copy('runtime-extraction-rejected')
    subprocess.run(['git', 'apply', '--no-index', str(ROOT / 'tests/fixtures/runtime-extraction.patch')], cwd=extraction, check=True)
    manifest_write(extraction)

    dead_code = copy('dead-code-only')
    shutil.copy2(ROOT / 'payload/default/niri/desktop.py', dead_code / 'payload/default/niri/desktop.py')
    manifest_write(dead_code)

    combined = copy('combined', ROOT)
    no_recovery = copy('without-refresh-recovery', combined, True)
    file = no_recovery / 'manage.py'
    file.write_text(replace_function(file.read_text(), 'recover_refresh', 'def recover_refresh():\n  pass'))

    no_conflicts = copy('without-conflict-preflight', combined, True)
    file = no_conflicts / 'manage.py'
    text = file.read_text().replace('    conflicts = self.conflicts()\n    if conflicts and not force:\n      return conflicts\n', '')
    file.write_text(text)

    no_hash = copy('without-output-hash', combined, True)
    file = no_hash / 'manage.py'
    text = file.read_text().replace("    if digest(target) != entry['sha256']:\n      raise ValueError('Damaged extension payload: ' + name)\n", '')
    file.write_text(text)

    no_ipc_error = copy('without-ipc-errors', combined, True)
    file = no_ipc_error / 'payload/default/niri/bridge.py'
    file.write_text(file.read_text().replace('raise RuntimeError(reply["Err"])', 'return reply["Err"]'))

    results = []
    for name, path, negative in variants:
      result = {'variant': name, 'expected_failure': negative, **measurements(path)}
      commands = [['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], ['node', 'tests/niri-model-test.cjs']]
      statuses, logs = [], []
      for command in commands:
        process = subprocess.run(command, cwd=path, capture_output=True, text=True, timeout=60)
        statuses.append(process.returncode)
        logs.append(process.stdout + process.stderr)
      text = '\n'.join(logs)
      (args.output / (name + '.log')).write_text(text)
      result['exit_codes'] = statuses
      result['tests'] = int(re.search(r'Ran (\d+) tests', text)[1])
      result['failed_tests'] = re.findall(r'^(?:FAIL|ERROR): (.+)$', text, re.M)
      result['matched_expectation'] = bool(any(statuses)) == negative
      if not negative:
        hashes = materialized_hashes(path, args.base)
        result['runtime_files'] = len(hashes)
        result['runtime_byte_changes'] = [name for name, digest in hashes.items() if digest != original_hashes[name]]
      results.append(result)
      print(name, 'EXPECTED FAIL' if negative and any(statuses) else ('PASS' if not any(statuses) else 'FAIL'), flush=True)
    (args.output / 'results.json').write_text(json.dumps({'baseline': BASELINE, 'variants': results}, indent=2) + '\n')
    assert all(r['matched_expectation'] for r in results), 'Unexpected ablation result'
    patch_result = next(r for r in results if r['variant'] == 'patches-only')
    assert not patch_result['runtime_byte_changes'], 'Patch representation changed runtime behavior'


if __name__ == '__main__':
  main()
