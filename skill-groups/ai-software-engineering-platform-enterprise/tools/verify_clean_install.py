from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SUITE = Path(__file__).resolve().parents[1]
PLUGIN_NAMES = (
    "ai-engineering-core",
    "ai-engineering-web",
    "ai-engineering-unity",
    "ai-engineering-workspace",
    "ai-engineering-quality",
)


def _safe_extract(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe archive member: {info.filename}")
        archive.extractall(destination)


def verify(suite: Path = SUITE, archive_dir: Path | None = None) -> dict[str, Any]:
    archive_dir = (archive_dir or suite / "dist").resolve()
    expected_version: str | None = None
    with tempfile.TemporaryDirectory(prefix="hiker-clean-install-") as temporary:
        root = Path(temporary)
        candidate = root / "suite"
        plugins = candidate / "plugins"
        plugins.mkdir(parents=True)
        shutil.copy2(suite / "install_personal.py", candidate / "install_personal.py")
        shutil.copytree(suite / "templates", candidate / "templates")
        for name in PLUGIN_NAMES:
            source_manifest = json.loads((suite / "plugins" / name / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
            version = str(source_manifest["version"])
            expected_version = expected_version or version
            if version != expected_version:
                return {"ok": False, "errors": ["source plugin versions differ"]}
            public = version.split("+", 1)[0]
            archive = archive_dir / f"{name}-{public}.zip"
            if not archive.is_file():
                return {"ok": False, "errors": [f"missing archive: {archive.name}"]}
            target = plugins / name
            target.mkdir()
            _safe_extract(archive, target)
        home = root / "home"
        (home / ".codex").mkdir(parents=True)
        (home / ".codex" / "AGENTS.md").write_text("# Existing\n\n- preserve me\n", encoding="utf-8")
        env = dict(os.environ)
        env.update({"HOME": str(home), "USERPROFILE": str(home), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(candidate / "install_personal.py"), "--cache-retention", "1"],
            cwd=candidate,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            installed = json.loads(completed.stdout) if completed.returncode == 0 else {}
        except json.JSONDecodeError:
            installed = {}
        cache_root = home / ".codex" / "plugins" / "cache" / "personal-ai-engineering-marketplace"
        rows = []
        for name in PLUGIN_NAMES:
            active_manifest = home / ".codex" / "plugins" / name / ".codex-plugin" / "plugin.json"
            active = json.loads(active_manifest.read_text(encoding="utf-8")) if active_manifest.is_file() else {}
            versions = sorted(path.name for path in (cache_root / name).iterdir() if path.is_dir() and not path.name.endswith(".installing")) if (cache_root / name).is_dir() else []
            installing = list((cache_root / name).glob("*.installing")) if (cache_root / name).is_dir() else []
            rows.append({"plugin": name, "active_version": active.get("version"), "cache_versions": versions, "installing_count": len(installing)})
        agents = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8") if (home / ".codex" / "AGENTS.md").is_file() else ""
        errors = []
        if completed.returncode != 0 or installed.get("verification", {}).get("ok") is not True:
            errors.append("installer verification failed")
        for row in rows:
            if row["active_version"] != expected_version or row["cache_versions"] != [expected_version] or row["installing_count"] != 0:
                errors.append(f"single-version install mismatch: {row['plugin']}")
        if "preserve me" not in agents or agents.count("<!-- ai-engineering-global-governance start -->") != 1:
            errors.append("global rule merge is not safe or idempotent")
        return {
            "ok": not errors,
            "version": expected_version,
            "archives": len(PLUGIN_NAMES),
            "plugins": rows,
            "installer_verification": installed.get("verification", {}).get("ok") is True,
            "single_active_version": not any("single-version" in item for item in errors),
            "global_rules_preserved": "preserve me" in agents,
            "temporary_home_removed_on_exit": True,
            "errors": errors,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hiker release archives in an isolated clean HOME")
    parser.add_argument("--suite", default=str(SUITE))
    parser.add_argument("--archive-dir")
    args = parser.parse_args()
    suite = Path(args.suite).resolve()
    report = verify(suite, Path(args.archive_dir).resolve() if args.archive_dir else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
