"""Build and validate a private Omarchy runtime without touching the package tree."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HYPRCTL = re.compile(r"(?<![A-Za-z0-9_-])hyprctl\b")
_QML_HYPR = re.compile(r"Quickshell\.Hyprland|\bHyprland\.[A-Za-z_]")
# The setup-only upgrader talks to a legacy Hyprland session outside this runtime;
# the shim is the hyprctl executable itself and cannot be asked to avoid its own name.
_SCAN_EXEMPT = {"bin/omarchy-upgrade-to-quattro", "bin/hyprctl"}

def _shim_supported():
    """The hyprctl surface the shim translates; kept in overlay/default/niri/hyprctl.py."""
    path = Path(__file__).resolve().parent / "overlay/default/niri/hyprctl.py"
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("hyprctl_shim", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.SUPPORTED
    finally:
        sys.path.remove(str(path.parent))

def _hyprctl_positionals(rest):
    """Positional tokens of one invocation: flags go, and -- ends option parsing."""
    positionals, terminated = [], False
    for token in rest.split():
        if terminated:
            positionals.append(token)
        elif token == "--":
            terminated = True
        elif not token.startswith("-"):
            positionals.append(token)
    return positionals

def _unadapted_hyprctl(text, supported):
    """A bin/ hyprctl call fails only when the shim cannot serve its subcommand or dispatcher."""
    for line in text.splitlines():
        matches = list(_HYPRCTL.finditer(line))
        for index, match in enumerate(matches):
            rest = line[match.end():matches[index + 1].start() if index + 1 < len(matches) else None]
            positionals = _hyprctl_positionals(rest)
            if not positionals: return True
            if positionals[0] == "dispatch":
                dispatcher = (positionals[1:2] or [""])[0].strip("\"'")
                lua = re.match(r"^(hl\.[a-z_.]+?)\s*\(", dispatcher)
                if (lua.group(1) if lua else dispatcher) not in supported["dispatch"]: return True
            elif positionals[0] not in supported: return True
    return False

def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def _copy_materialized(src: Path, dst: Path, seen: set[Path]) -> None:
    src = src.resolve(strict=True)
    if src in seen: raise ValueError(f"repeated symlink target: {src}")
    seen.add(src)
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            if child.name not in {".git", "__pycache__"}:
                _copy_materialized(child, dst / child.name, seen.copy())
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    else: raise ValueError(f"unsupported runtime entry: {src}")

def _patches(source: Path):
    return sorted((source / "patches").rglob("*.patch"))

def prepare(base: Path, destination: Path, source: Path) -> dict:
    """Materialize a checked Niri runtime; record drift instead of blocking it."""
    base, destination, source = map(lambda p: Path(p).resolve(), (base, destination, source))
    if not base.is_dir(): raise ValueError(f"missing Omarchy base: {base}")
    for top in ("bin", "shell", "default", "config"):
        if not (base / top).is_dir(): raise ValueError(f"missing Omarchy runtime tree: {top}")
    spec = json.loads((source / "compatibility.json").read_text())
    if destination.exists(): raise ValueError(f"destination already exists: {destination}")
    replacements = spec.get("replacements", {})
    bindings = spec.get("bindings", {})
    drift = []
    missing = [rel for rel in replacements if not (base / rel).is_file()]
    if missing: raise ValueError("Omarchy removed reviewed files: " + ", ".join(sorted(missing)))
    actual_bindings = {p.relative_to(base).as_posix() for p in (base / "default/hypr/bindings").glob("*.lua")}
    for rel in sorted(actual_bindings ^ set(bindings)):
        actual = _hash(base / rel) if rel in actual_bindings else None
        drift.append({"path": rel, "kind": "bindings", "accepted": [], "actual": actual})
    for rel, expected in sorted({**replacements, **bindings}.items()):
        p = base / rel
        if not p.is_file(): continue  # removed binding file; recorded above
        accepted = [expected] if isinstance(expected, str) else expected
        actual = _hash(p)
        if actual not in accepted:
            drift.append({"path": rel, "kind": "replacement" if rel in replacements else "bindings", "accepted": accepted, "actual": actual})
    expected_patches = set(spec["patches"])
    actual_patches = {str(p.relative_to(source / "patches"))[:-6] for p in _patches(source)}
    if actual_patches != expected_patches:
        raise ValueError("Patch inventory differs from the reviewed source: " + ", ".join(sorted(actual_patches ^ expected_patches)))
    overlay_files = {p.relative_to(source / "overlay").as_posix() for p in (source / "overlay").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    missing = set(spec.get("replacements", {})) - overlay_files
    if missing:
        raise ValueError("Reviewed replacements missing: " + ", ".join(sorted(missing)))
    staged = destination.with_name(destination.name + ".staging")
    if staged.exists():
        raise ValueError(f"staging directory already exists: {staged}")
    try:
        _copy_materialized(base, staged, set())
        for patch in _patches(source):
            rel = Path(str(patch.relative_to(source / "patches"))[:-6])
            target = staged / rel
            if not target.is_file(): raise ValueError(f"patch target missing: {rel}")
            before = _hash(target)
            result = subprocess.run(["git", "apply", "--no-index", "--check", "--include", str(rel), str(patch)], cwd=staged, text=True, capture_output=True)
            if result.returncode: raise ValueError(f"patch rejected for {rel}: {result.stderr.strip()}")
            subprocess.run(["git", "apply", "--no-index", "--include", str(rel), str(patch)], cwd=staged, check=True, stdout=subprocess.DEVNULL)
            if _hash(target) == before:
                raise ValueError(f"patch did not modify its declared target: {rel}")
        overlay = source / "overlay"
        for item in overlay.rglob("*"):
            if item.is_dir() or "__pycache__" in item.parts: continue
            rel = item.relative_to(overlay); out = staged / rel
            if out.exists() and rel.as_posix() not in spec.get("replacements", {}):
                raise ValueError(f"unreviewed overlay replacement: {rel}")
            _copy_materialized(item, out, set())
        bad = []
        shim = _shim_supported()
        for item in staged.rglob("*"):
            rel = item.relative_to(staged)
            if not item.is_file() or not (rel.parts[0] in ("bin", "shell")): continue
            if rel.as_posix() in _SCAN_EXEMPT: continue
            text = "\n".join(line for line in item.read_text(errors="ignore").splitlines() if not line.lstrip().startswith(("#", "//")))
            # shell/ never calls the compositor CLI; in bin/ the shim covers its reviewed surface.
            if _QML_HYPR.search(text) or (rel.parts[0] == "shell" and _HYPRCTL.search(text)) \
               or (rel.parts[0] == "bin" and _unadapted_hyprctl(text, shim)):
                bad.append(str(rel))
        if bad: raise ValueError("unadapted Hyprland interface: " + ", ".join(sorted(bad)))
        if destination.exists(): raise ValueError(f"destination already exists: {destination}")
        staged.rename(destination)
    except BaseException:
        if staged.exists(): shutil.rmtree(staged)
        raise
    return {"reviewed_base": spec["base"], "patches": len(actual_patches), "replacements": len(spec.get("replacements", {})), "drift": drift}
