from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


SKIP_PARTS = {"__pycache__", ".pytest_cache", ".codex-output"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def included(path: Path) -> bool:
    return not any(part in SKIP_PARTS for part in path.parts) and path.suffix.lower() not in SKIP_SUFFIXES


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_content(path: Path) -> bytes:
    """Return deterministic package bytes without rewriting binary payloads."""
    content = path.read_bytes()
    if b"\r\n" not in content or b"\x00" in content:
        return content
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    return content.replace(b"\r\n", b"\n")


def source_files(plugin: Path) -> dict[str, Path]:
    return {
        "./" + path.relative_to(plugin).as_posix(): path
        for path in sorted(item for item in plugin.rglob("*") if item.is_file() and included(item))
    }


def package_plan(suite: Path) -> dict[str, Any]:
    plugins = sorted(path for path in (suite / "plugins").iterdir() if path.is_dir())
    entries: list[dict[str, Any]] = []
    source_digest = hashlib.sha256()
    for plugin in plugins:
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        public_version = str(manifest["version"]).split("+", 1)[0]
        files = source_files(plugin)
        for name, path in files.items():
            source_digest.update(plugin.name.encode("utf-8"))
            source_digest.update(name.encode("utf-8"))
            source_digest.update(canonical_content(path))
        entries.append({
            "plugin": plugin.name,
            "version": str(manifest["version"]),
            "archive": f"{plugin.name}-{public_version}.zip",
            "file_count": len(files),
        })
    return {
        "ok": bool(entries),
        "source_fingerprint": source_digest.hexdigest(),
        "packages": entries,
        "expected_archives": [item["archive"] for item in entries],
    }


def audit_packages(suite: Path, archive_dir: Path | None = None) -> dict[str, Any]:
    suite = suite.resolve()
    plan = package_plan(suite)
    errors: list[str] = []
    if not plan["ok"]:
        errors.append("no plugins available for packaging")
    if archive_dir is None:
        return {"ok": not errors, "mode": "source-plan", "plan": plan, "errors": errors}
    archive_dir = archive_dir.resolve()
    expected = set(plan["expected_archives"])
    actual = {path.name for path in archive_dir.glob("*.zip")}
    if actual != expected:
        errors.append(f"archive set mismatch: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    package_rows: list[dict[str, Any]] = []
    by_name = {item["archive"]: item for item in plan["packages"]}
    for archive_name in sorted(expected & actual):
        archive_path = archive_dir / archive_name
        plugin = suite / "plugins" / str(by_name[archive_name]["plugin"])
        expected_files = source_files(plugin)
        try:
            with zipfile.ZipFile(archive_path) as bundle:
                broken = bundle.testzip()
                names = {info.filename for info in bundle.infolist() if not info.is_dir()}
                if broken:
                    errors.append(f"{archive_name}: corrupt member {broken}")
                if names != set(expected_files):
                    errors.append(
                        f"{archive_name}: members differ from source: "
                        f"missing={sorted(set(expected_files)-names)[:8]} extra={sorted(names-set(expected_files))[:8]}"
                    )
                for name in sorted(names & set(expected_files)):
                    if hashlib.sha256(bundle.read(name)).digest() != hashlib.sha256(canonical_content(expected_files[name])).digest():
                        errors.append(f"{archive_name}: stale source member {name}")
        except (OSError, zipfile.BadZipFile) as exc:
            errors.append(f"{archive_name}: unreadable archive: {exc}")
        package_rows.append({"archive": archive_name, "sha256": sha256(archive_path)})
    checksum_path = archive_dir / "SHA256SUMS.txt"
    expected_lines = [f"{item['sha256']}  {item['archive']}" for item in package_rows]
    actual_lines = checksum_path.read_text(encoding="utf-8").splitlines() if checksum_path.is_file() else []
    if actual_lines != expected_lines:
        errors.append("SHA256SUMS.txt does not exactly describe the candidate archives")
    return {
        "ok": not errors,
        "mode": "candidate-archives",
        "plan": plan,
        "archive_dir": str(archive_dir),
        "packages": package_rows,
        "errors": errors,
    }
