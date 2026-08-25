from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from package_facts import package_plan, sha256, source_files
from self_governance import finalize_pipeline, package_gate, run_pipeline


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
DIST = ROOT / "dist"


def build_candidates(suite: Path, target_dir: Path) -> list[dict[str, Any]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    for item in package_plan(suite)["packages"]:
        plugin = suite / "plugins" / str(item["plugin"])
        target = target_dir / str(item["archive"])
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, source in source_files(plugin).items():
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        outputs.append({"plugin": item["plugin"], "version": item["version"], "archive": target.name, "sha256": sha256(target)})
    (target_dir / "SHA256SUMS.txt").write_text(
        "\n".join(f"{item['sha256']}  {item['archive']}" for item in outputs) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return outputs


def publish_candidates(candidate_dir: Path, dist: Path, expected_archives: list[str]) -> list[str]:
    """Publish only a fully verified candidate set; no source gate writes here."""
    dist.mkdir(parents=True, exist_ok=True)
    expected = set(expected_archives)
    removed: list[str] = []
    for old in sorted(dist.glob("*.zip")):
        if old.name not in expected:
            old.unlink()
            removed.append(old.name)
    for name in sorted(expected):
        staging = dist / f".{name}.verified"
        shutil.copyfile(candidate_dir / name, staging)
        staging.replace(dist / name)
    checksum_staging = dist / ".SHA256SUMS.txt.verified"
    shutil.copyfile(candidate_dir / "SHA256SUMS.txt", checksum_staging)
    checksum_staging.replace(dist / "SHA256SUMS.txt")
    return removed


def release(
    repository_root: Path = REPOSITORY_ROOT,
    suite: Path = ROOT,
    dist: Path = DIST,
    *,
    preflight_runner: Callable[..., dict[str, Any]] = run_pipeline,
    builder: Callable[[Path, Path], list[dict[str, Any]]] = build_candidates,
    publisher: Callable[[Path, Path, list[str]], list[str]] = publish_candidates,
) -> dict[str, Any]:
    preflight = preflight_runner(repository_root, suite)
    if not preflight.get("ok"):
        return {"ok": False, "phase": "source-gates", "self_governance": preflight, "published": False}
    with tempfile.TemporaryDirectory(prefix="hiker-release-candidate-") as temporary:
        candidate_dir = Path(temporary)
        outputs = builder(suite, candidate_dir)
        candidate_stage = package_gate(suite, candidate_dir)
        final = finalize_pipeline(preflight, candidate_stage)
        if not final["ok"]:
            return {"ok": False, "phase": "package-facts", "self_governance": final, "published": False}
        expected = list(candidate_stage["facts"]["plan"]["expected_archives"])
        removed = publisher(candidate_dir, dist, expected)
    return {
        "ok": True,
        "phase": "release-gate",
        "self_governance": final,
        "packages": outputs,
        "stale_packages_removed": removed,
        "published": True,
    }


def main() -> int:
    report = release()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
