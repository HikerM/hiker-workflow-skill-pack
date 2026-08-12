from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
DIST = ROOT / "dist"
SKIP_PARTS = {"__pycache__", ".pytest_cache"}


def include(path: Path) -> bool:
    return not any(part in SKIP_PARTS for part in path.parts) and path.suffix not in {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    outputs = []
    release_specs = []
    for plugin in sorted(item for item in PLUGINS.iterdir() if item.is_dir()):
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        public_version = str(manifest["version"]).split("+", 1)[0]
        target = DIST / f"{plugin.name}-{public_version}.zip"
        release_specs.append((plugin, manifest, target))
    current_targets = {target.resolve() for _, _, target in release_specs}
    plugin_prefixes = tuple(f"{plugin.name}-" for plugin, _, _ in release_specs)
    removed = []
    for old in sorted(DIST.glob("*.zip")):
        if old.name.startswith(plugin_prefixes) and old.resolve() not in current_targets:
            old.unlink()
            removed.append(old.relative_to(ROOT).as_posix())
    for plugin, manifest, target in release_specs:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(item for item in plugin.rglob("*") if item.is_file() and include(item)):
                info = zipfile.ZipInfo("./" + file.relative_to(plugin).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16; info.create_system = 3
                archive.writestr(info, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        outputs.append({"plugin": manifest["interface"]["displayName"], "version": manifest["version"], "path": target.relative_to(ROOT).as_posix(), "sha256": sha256(target)})
    lines = [f"{item['sha256']}  {item['path']}" for item in outputs]
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "packages": outputs, "stale_packages_removed": removed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
