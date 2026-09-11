import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('payload_manager', Path(__file__).parents[1] / 'manage.py')
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class PayloadTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.base = self.root / 'base'
    self.extension = self.root / 'extension'
    self.stage = self.root / 'stage'
    self.name = 'bin/example'
    self.before = '#!/bin/bash\nprintf original\n'
    self.after = '#!/bin/bash\nprintf replacement\n'
    for name in ('bin', 'shell', 'config', 'default'):
      (self.base / name).mkdir(parents=True)
    self.packaged = self.root / 'packaged-command'
    self.packaged.write_text(self.before)
    self.packaged.chmod(0o755)
    (self.base / self.name).symlink_to(self.packaged)
    self.patch = self.extension / 'patches/bin/example.patch'
    self.patch.parent.mkdir(parents=True)
    self.write_patch(self.after)
    config = self.extension / 'payload/default/niri/config.kdl'
    config.parent.mkdir(parents=True)
    config.write_text('')
    self.manifest = {'files': {
      self.name: {'baseSha256': [self.sha(self.before)], 'sha256': self.sha(self.after), 'patch': True},
      'default/niri/config.kdl': {'baseSha256': [None], 'sha256': self.sha('')},
    }}
    (self.extension / 'manifest.json').write_text(json.dumps(self.manifest))
    self.here = mock.patch.object(manager, 'HERE', self.extension)
    self.here.start()
    self.addCleanup(self.here.stop)

  @staticmethod
  def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

  def write_patch(self, replacement):
    self.patch.write_text(''.join(difflib.unified_diff(
      self.before.splitlines(True), replacement.splitlines(True),
      fromfile='a/' + self.name, tofile='b/' + self.name)))

  def assemble(self):
    real_run = manager.run
    def portable_run(*command, **kwargs):
      if command[0] != 'niri':
        return real_run(*command, **kwargs)
    with mock.patch.object(manager, 'run', side_effect=portable_run), mock.patch.object(manager.os, 'chown'):
      manager.copy_runtime(self.base, self.stage)

  def test_patch_materializes_command_without_touching_package(self):
    self.assemble()
    self.assertFalse((self.stage / self.name).is_symlink())
    self.assertEqual((self.stage / self.name).read_text(), self.after)
    self.assertEqual((self.stage / self.name).stat().st_mode & 0o777, 0o755)
    self.assertEqual(self.packaged.read_text(), self.before)

  def test_corrupt_patch_output_is_rejected(self):
    self.write_patch('#!/bin/bash\nprintf unintended\n')
    with self.assertRaisesRegex(ValueError, 'Damaged extension payload'):
      self.assemble()
    self.assertEqual(self.packaged.read_text(), self.before)

  def test_patch_is_limited_to_its_manifest_target(self):
    victim = self.base / 'bin/untouched'
    victim.write_text('original\n')
    with self.patch.open('a') as stream:
      stream.write('--- a/bin/untouched\n+++ b/bin/untouched\n@@ -1 +1 @@\n-original\n+changed\n')
    self.assemble()
    self.assertEqual((self.stage / 'bin/untouched').read_text(), 'original\n')
