from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from audit_skill_coherence import audit as audit_skill_coherence
from benchmark_router import benchmark as benchmark_router
from evaluate_master_progression import evaluate as evaluate_master_progression
from evaluate_router import evaluate as evaluate_router
from desktop_stability_gate import audit as audit_desktop_stability


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
    unit_run = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "tools" / "run_all_tests.py")],
        cwd=str(ROOT), text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    unit_report = json.loads((ROOT / "test-results.json").read_text(encoding="utf-8")) if (ROOT / "test-results.json").is_file() else {"ok": False}
    router_eval = evaluate_router()
    master_progression = evaluate_master_progression()
    router_performance = benchmark_router(20, 500.0)
    coherence = audit_skill_coherence(ROOT)
    desktop_stability = audit_desktop_stability(ROOT)
    gate_errors = []
    if unit_run.returncode != 0 or not unit_report.get("ok"):
        gate_errors.append("完整单元测试失败")
    if not router_eval["ok"]:
        gate_errors.append("轻量路由行为 Eval 失败")
    if not master_progression["ok"]:
        gate_errors.append("总控多维推进评估失败")
    if not router_performance["ok"]:
        gate_errors.append(f"轻量路由性能失败: P95 {router_performance['p95_ms']}ms")
    if not coherence["ok"]:
        gate_errors.extend(f"Skill一致性: {item['code']} {item['skill']}" for item in coherence["errors"])
    if not desktop_stability["ok"]:
        gate_errors.extend(f"桌面稳定性: {item}" for item in desktop_stability["errors"])
    if gate_errors:
        print(json.dumps({"ok": False, "gate": "complete-release-source-gate", "errors": gate_errors}, ensure_ascii=False, indent=2))
        return 2
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
        with zipfile.ZipFile(target, "r") as archive:
            broken = archive.testzip()
            names = set(archive.namelist())
        if broken or "./.codex-plugin/plugin.json" not in names:
            target.unlink(missing_ok=True)
            print(json.dumps({"ok": False, "gate": "package-integrity", "plugin": plugin.name, "broken": broken}, ensure_ascii=False, indent=2))
            return 2
        outputs.append({"plugin": manifest["interface"]["displayName"], "version": manifest["version"], "path": target.relative_to(ROOT).as_posix(), "sha256": sha256(target)})
    lines = [f"{item['sha256']}  {item['path']}" for item in outputs]
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "release_gate":{"unit_tests":True,"router_eval":True,"master_progression":True,"router_p95_ms":router_performance["p95_ms"],"skill_coherence":True,"desktop_stability":True,"package_integrity":True},"packages": outputs, "stale_packages_removed": removed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
