import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from compat import prepare

class CompatTests(unittest.TestCase):
    def fixture(self, p, overlay='#!/bin/sh\necho niri\n', patch='--- a/bin/tool\n+++ b/bin/tool\n@@ -1 +1 @@\n-echo base\n+echo patched\n'):
        base=p/'base'; (base/'bin').mkdir(parents=True)
        for x in ('shell','default','config'): (base/x).mkdir()
        (base/'bin/tool').write_text('echo base\n')
        source=p/'source'; (source/'patches/bin').mkdir(parents=True); (source/'overlay/bin').mkdir(parents=True)
        (source/'overlay/bin/replacement').write_text(overlay)
        (base/'bin/replacement').write_text('echo original replacement\n')
        (source/'patches/bin/tool.patch').write_text(patch)
        import hashlib
        h=hashlib.sha256((base/'bin/replacement').read_bytes()).hexdigest()
        (source/'compatibility.json').write_text(json.dumps({'base':'test','patches':['bin/tool'],'replacements':{'bin/replacement':h}}))
        return base,source

    def test_real_pinned_base(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(__file__).parents[1]
            candidate = os.environ.get("OMARCHY_TEST_BASE", str(root / "test-artifacts/upstream-clean"))
            if not Path(candidate).is_dir(): self.skipTest("set OMARCHY_TEST_BASE to a clean archived Omarchy tree")
            base = Path(candidate)
            report = prepare(base, Path(d) / "runtime", root)
            self.assertEqual(report["reviewed_base"], "346e69e1cec6c4e8924531874af6ba010a1bc99e")

    def test_reviewed_try_omarchy_variant(self):
        root = Path(__file__).resolve().parents[1]
        base = Path(os.environ.get("OMARCHY_TEST_BASE", root / "test-artifacts/upstream-clean")).resolve()
        if not base.is_dir():
            self.skipTest("set OMARCHY_TEST_BASE to the reviewed upstream checkout")
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "base"
            shutil.copytree(base, source, ignore=shutil.ignore_patterns('.git'))
            subprocess.run(['git', 'apply', '--no-index', str(root / 'tests/fixtures/try-omarchy-cursor-idle.patch')], cwd=source, check=True)
            report = prepare(source, Path(d) / 'runtime', root)
            self.assertEqual(report['reviewed_base'], '346e69e1cec6c4e8924531874af6ba010a1bc99e')

    def test_drift_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base=p/"base"; (base/"bin").mkdir(parents=True)
            for x in ("shell", "default", "config"): (base/x).mkdir()
            (base/"bin/tool").write_text("changed")
            source=p/"source"; (source/"patches").mkdir(parents=True); (source/"overlay/bin").mkdir(parents=True)
            (source/"compatibility.json").write_text(json.dumps({"base":"x","patches":[],"replacements":{"bin/tool":"wrong"}}))
            with self.assertRaisesRegex(ValueError, "Omarchy changed"): prepare(base,p/"out",source)

    def test_missing_tree_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'base/bin').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'missing Omarchy runtime tree'): prepare(p/'base',p/'out',p/'source')

    def test_existing_destination_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p); (p/'out').mkdir()
            with self.assertRaisesRegex(ValueError, 'destination already exists'): prepare(base,p/'out',source)

    def test_unreviewed_overlay_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (base/'bin/other').write_text('base')
            (source/'overlay/bin/other').write_text('replacement')
            with self.assertRaisesRegex(ValueError, 'unreviewed overlay'): prepare(base,p/'out',source)

    def test_patch_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p,patch='not a patch')
            with self.assertRaisesRegex(ValueError, 'patch rejected'): prepare(base,p/'out',source)

    def test_hypr_interface_in_new_bin_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p,overlay='hyprctl monitors')
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_hypr_interface_added_by_patch_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p, overlay='#!/bin/sh\necho niri\n', patch='--- a/bin/tool\n+++ b/bin/tool\n@@ -1 +1 @@\n-echo base\n+hyprctl monitors\n')
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_hyprland_named_command_is_still_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (source/'overlay/bin/omarchy-hyprland-new').write_text('hyprctl monitors')
            # The compatibility name is retained for callers, but its implementation is audited.
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_removed_patch_target_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p); (base/'bin/tool').unlink()
            with self.assertRaisesRegex(ValueError, 'patch target missing|Omarchy changed'): prepare(base,p/'out',source)

    def test_deleted_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (source/'patches/bin/tool.patch').unlink()
            with self.assertRaisesRegex(ValueError, 'Patch inventory'):
                prepare(base,p/'out',source)

    def test_deleted_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (source/'overlay/bin/replacement').unlink()
            with self.assertRaisesRegex(ValueError, 'Reviewed replacements missing'):
                prepare(base,p/'out',source)

    def test_new_upstream_binding_file_needs_review(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            binding=base/'default/hypr/bindings/new.lua'
            binding.parent.mkdir(parents=True)
            binding.write_text('new shortcut')
            with self.assertRaisesRegex(ValueError, 'Window bindings changed'):
                prepare(base,p/'out',source)

    def test_unrelated_upstream_change_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p); (base/'default/unrelated').write_text('changed')
            prepare(base,p/'out',source)

    def test_symlink_is_materialized(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p); (base/'bin/real').write_text('real')
            (base/'bin/link').symlink_to('real')
            # A symlink not referenced by a patch is still copied as a regular file.
            report=prepare(base,p/'out',source)
            self.assertFalse((p/'out/bin/link').is_symlink()); self.assertEqual((p/'out/bin/link').read_text(),'real')
            (base/'bin/real').write_text('package-updated')
            self.assertEqual((p/'out/bin/link').read_text(), 'real')

if __name__ == "__main__": unittest.main()
