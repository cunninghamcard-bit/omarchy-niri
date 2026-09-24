import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
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

    def test_replacement_drift_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (base/"bin/replacement").write_text("echo drifted\n")
            report=prepare(base,p/"out",source)
            self.assertEqual(report["drift"],[{"path":"bin/replacement","kind":"replacement",
                "accepted":[hashlib.sha256(b"echo original replacement\n").hexdigest()],
                "actual":hashlib.sha256(b"echo drifted\n").hexdigest()}])

    def test_missing_replacement_target_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p); (base/"bin/replacement").unlink()
            with self.assertRaisesRegex(ValueError, "Omarchy removed reviewed files"): prepare(base,p/"out",source)

    def test_bindings_drift_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            binding=base/"default/hypr/bindings/tiling.lua"
            binding.parent.mkdir(parents=True); binding.write_text("bind\n")
            spec=json.loads((source/"compatibility.json").read_text())
            spec["bindings"]={"default/hypr/bindings/tiling.lua":"wrong"}
            (source/"compatibility.json").write_text(json.dumps(spec))
            report=prepare(base,p/"out",source)
            self.assertEqual(report["drift"],[{"path":"default/hypr/bindings/tiling.lua","kind":"bindings",
                "accepted":["wrong"],"actual":hashlib.sha256(b"bind\n").hexdigest()}])

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
            p=Path(d); base,source=self.fixture(p,overlay='hyprctl devices -j')
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_hypr_interface_added_by_patch_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p, overlay='#!/bin/sh\necho niri\n', patch='--- a/bin/tool\n+++ b/bin/tool\n@@ -1 +1 @@\n-echo base\n+hyprctl eval "hl.config()"\n')
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_hyprland_named_command_is_still_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (source/'overlay/bin/omarchy-hyprland-new').write_text('hyprctl binds')
            # The compatibility name is retained for callers, but its implementation is audited.
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_shim_supported_hyprctl_call_in_bin_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for script in ['hyprctl monitors -j | jq .', 'hyprctl reload', 'hyprctl -j monitors >/dev/null', 'hyprctl switchxkblayout all 0']:
                with self.subTest(script=script):
                    base,source=self.fixture(p/script.replace('/','_'),overlay=script)
                    prepare(base,p/script.replace('/','_')/'out',source)

    def test_shim_serves_upstream_dispatch_pattern(self):
        # Upstream tries the Lua dispatcher and falls back to the classic name; both are covered.
        line = r'hyprctl dispatch "hl.dsp.focus({ window = \"address:$WINDOW_ADDRESS\" })" >/dev/null 2>&1 || hyprctl dispatch focuswindow "address:$WINDOW_ADDRESS"'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p,overlay=line)
            prepare(base,p/'out',source)

    def test_unsupported_dispatch_fails_the_scan(self):
        for line in ['hyprctl dispatch exec bash -lc true', 'hyprctl dispatch togglefloating "address:0x1"',
                     'hyprctl dispatch "$lua"', 'hyprctl dispatch "hl.dsp.dpms({ action = \\"disable\\" })"', 'hyprctl dispatch']:
            with self.subTest(line=line), tempfile.TemporaryDirectory() as d:
                p=Path(d); base,source=self.fixture(p,overlay=line)
                with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_shell_files_keep_the_strict_hyprland_scan(self):
        for content in ['hyprctl monitors', 'Quickshell.Hyprland', 'Hyprland.dispatch()']:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as d:
                p=Path(d); base,source=self.fixture(p)
                (base/'shell/Widget.qml').write_text(content)
                with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_qml_hyprland_in_bin_is_not_covered_by_the_shim(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p,overlay='Quickshell.Hyprland')
            with self.assertRaisesRegex(ValueError, 'unadapted Hyprland interface'): prepare(base,p/'out',source)

    def test_the_shim_itself_is_exempt_from_the_scan(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            (source/'overlay/bin/hyprctl').write_text('hyprctl devices -j\n')  # the shim may name its own command
            prepare(base,p/'out',source)


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

    def test_new_upstream_binding_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            binding=base/'default/hypr/bindings/new.lua'
            binding.parent.mkdir(parents=True)
            binding.write_text('new shortcut')
            report=prepare(base,p/'out',source)
            self.assertEqual(report['drift'],[{'path':'default/hypr/bindings/new.lua','kind':'bindings',
                'accepted':[],'actual':hashlib.sha256(b'new shortcut').hexdigest()}])

    def test_removed_upstream_binding_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            binding=base/'default/hypr/bindings/tiling.lua'
            binding.parent.mkdir(parents=True); binding.write_text('bind\n')
            spec=json.loads((source/'compatibility.json').read_text())
            spec['bindings']={'default/hypr/bindings/tiling.lua':'stale'}
            (source/'compatibility.json').write_text(json.dumps(spec))
            binding.unlink()
            report=prepare(base,p/'out',source)
            self.assertEqual(report['drift'],[{'path':'default/hypr/bindings/tiling.lua','kind':'bindings',
                'accepted':[],'actual':None}])

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

    def test_review_drift_accept_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); base,source=self.fixture(p)
            subprocess.run(['git','init','-q'],cwd=base,check=True)
            subprocess.run(['git','add','bin','shell','default','config'],cwd=base,check=True)
            subprocess.run(['git','-c','user.name=t','-c','user.email=t@example.invalid','commit','-qm','base'],cwd=base,check=True)
            sha=subprocess.run(['git','rev-parse','HEAD'],cwd=base,capture_output=True,text=True,check=True).stdout.strip()
            spec=json.loads((source/'compatibility.json').read_text()); spec['base']=sha
            manifest=p/'compatibility.json'; manifest.write_text(json.dumps(spec))
            (base/'bin/replacement').write_text('echo drifted\n')
            script=[sys.executable,str(Path(__file__).resolve().parents[1]/'tools/review-drift')]
            listing=subprocess.run(script+[str(base),'--manifest',str(manifest)],capture_output=True,text=True)
            self.assertEqual(listing.returncode,0,listing.stderr)
            self.assertIn('bin/replacement',listing.stdout)
            self.assertIn(hashlib.sha256(b'echo original replacement\n').hexdigest(),listing.stdout)
            accepting=subprocess.run(script+[str(base),'--manifest',str(manifest),'--accept'],capture_output=True,text=True)
            self.assertEqual(accepting.returncode,0,accepting.stderr)
            spec=json.loads(manifest.read_text())
            self.assertEqual(spec['replacements']['bin/replacement'],
                             [hashlib.sha256(b'echo original replacement\n').hexdigest(),
                              hashlib.sha256(b'echo drifted\n').hexdigest()])
            (source/'compatibility.json').write_text(json.dumps(spec))
            self.assertEqual(prepare(base,p/'out',source)['drift'],[])

if __name__ == "__main__": unittest.main()
