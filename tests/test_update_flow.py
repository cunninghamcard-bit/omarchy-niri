import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
PATCH = ROOT / "patches/bin/omarchy-update.patch"


class UpdateFlowTests(unittest.TestCase):
    def pinned_script(self):
        configured = os.environ.get("OMARCHY_TEST_BASE")
        candidates = ([Path(configured)] if configured else []) + [
            ROOT / "test-artifacts/upstream-clean",
            ROOT.parent / "omarchy",
        ]
        for base in candidates:
            script = base / "bin/omarchy-update"
            if script.is_file():
                return script
        self.skipTest("set OMARCHY_TEST_BASE to a clean archived Omarchy tree")

    def patched_script(self, directory):
        source = self.pinned_script()
        work = directory / "repo"
        (work / "bin").mkdir(parents=True)
        shutil.copy2(source, work / "bin/omarchy-update")
        shutil.copy2(PATCH, work / "update.patch")
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "add", "bin/omarchy-update"], cwd=work, check=True)
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                         "commit", "-qm", "base"], cwd=work, check=True)
        subprocess.run(["git", "apply", "update.patch"], cwd=work, check=True)
        script = work / "bin/omarchy-update"
        text = script.read_text().replace("source /etc/omarchy.conf", "source \"$OMARCHY_TEST_CONF\"")
        script.write_text(text)
        script.chmod(0o755)
        return script

    def fixture(self, fail_status=False):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        script = self.patched_script(root)
        oldroot = root / "oldroot"
        newroot = root / "newroot"
        oldbin = oldroot / "bin"
        newbin = newroot / "bin"
        oldbin.mkdir(parents=True); newbin.mkdir(parents=True)
        log = root / "calls.log"
        conf = root / "omarchy.conf"
        conf.write_text(f'export OMARCHY_PATH="{oldroot}"\n')

        def stub(name, body="exit 0"):
            path = oldbin / name
            path.write_text("#!/bin/bash\n" + body + "\n")
            path.chmod(0o755)

        stub("omarchy-update-lock", "[[ $1 == held ]] && exit 0")
        stub("omarchy-niri-extension", ("echo status >> \"$OMARCHY_UPDATE_LOG\"; exit 7" if fail_status
                                        else "echo status >> \"$OMARCHY_UPDATE_LOG\"; exit 0"))
        stub("omarchy-update-system-pkgs", f'echo system-pkgs >> "$OMARCHY_UPDATE_LOG"; printf \'export OMARCHY_PATH="{newroot}"\\n\' > "$OMARCHY_TEST_CONF"')
        for name in ("omarchy-update-requires-free-space", "omarchy-update-pkg-prune", "omarchy-snapshot",
                     "omarchy-update-stay-awake", "omarchy-update-dev", "omarchy-update-keyring",
                     "omarchy-update-aur-pkgs", "omarchy-update-mise", "omarchy-update-orphan-pkgs",
                     "omarchy-update-analyze-logs", "omarchy-update-status", "omarchy-update-restart"):
            stub(name, f'echo {name} >> "$OMARCHY_UPDATE_LOG"; exit 0')
        for name in ("omarchy-migrate", "omarchy-hook"):
            path = newbin / name
            path.write_text(f'#!/bin/bash\necho new-{name} >> "$OMARCHY_UPDATE_LOG"\n')
            path.chmod(0o755)
        return temp, script, oldbin, newbin, conf, log

    def run_update(self, fail_status=False):
        temp, script, oldbin, newbin, conf, log = self.fixture(fail_status)
        env = {**os.environ, "OMARCHY_UPDATE_LOGGED": "1", "OMARCHY_TEST_CONF": str(conf),
               "OMARCHY_UPDATE_LOG": str(log), "PATH": str(oldbin)}
        result = subprocess.run([str(script), "-y"], env=env, capture_output=True, text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        return temp, result, calls

    def test_migration_and_hook_follow_runtime_published_by_system_packages(self):
        temp, result, calls = self.run_update()
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("new-omarchy-migrate"), 1)
        self.assertEqual(calls.count("new-omarchy-hook"), 1)
        self.assertLess(calls.index("system-pkgs"), calls.index("new-omarchy-migrate"))

    def test_status_failure_stops_before_migration_and_preserves_failure(self):
        temp, result, calls = self.run_update(fail_status=True)
        self.addCleanup(temp.cleanup)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Niri compatibility review required", result.stderr)
        self.assertNotIn("new-omarchy-migrate", calls)
        self.assertNotIn("new-omarchy-hook", calls)


if __name__ == "__main__":
    unittest.main()
