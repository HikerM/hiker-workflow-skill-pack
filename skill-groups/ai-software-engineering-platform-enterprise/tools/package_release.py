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
    for plugin in sorted(item for item in PLUGINS.iterdir() if item.is_dir()):
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        public_version = str(manifest["version"]).split("+", 1)[0]
        target = DIST / f"{plugin.name}-{public_version}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(item for item in plugin.rglob("*") if item.is_file() and include(item)):
                archive.write(file, "./" + file.relative_to(plugin).as_posix())
        outputs.append({"plugin": manifest["interface"]["displayName"], "version": manifest["version"], "path": target.relative_to(ROOT).as_posix(), "sha256": sha256(target)})
    lines = [f"{item['sha256']}  {item['path']}" for item in outputs]
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "packages": outputs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
