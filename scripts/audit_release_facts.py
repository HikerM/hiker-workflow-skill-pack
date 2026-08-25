#!/usr/bin/env python3
"""Audit current release facts without treating history as current documentation.

The audit has three document classes:

* current: must match the manifests, source tests and task-state implementation;
* history: changelog/versioned migration records are intentionally not rewritten;
* checkpoint: an explicitly dated snapshot may retain old facts, but must declare
  itself as a checkpoint and point readers at this audit for current facts.

No network access, model call or background service is used.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType


MARKER_DOCS = (
    "docs/INSTALLATION.md",
    "docs/MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md",
    "skill-groups/ai-software-engineering-platform-enterprise/plugins/ai-engineering-core/README_CN.md",
    "skill-groups/ai-software-engineering-platform-enterprise/plugins/ai-engineering-workspace/README_CN.md",
)
VERSION_SOURCE = "release-versions.json"
CURRENT_DOCS = (
    "README.md",
    "skill-groups/ai-software-engineering-platform-enterprise/README_CN.md",
    *MARKER_DOCS,
)
CHECKPOINT_DOC = (
    "skill-groups/ai-software-engineering-platform-enterprise/docs/"
    "DESKTOP_CRASH_RECOVERY_CHECKPOINT_CN.md"
)
STATE_PROTOCOL_DOC = (
    "skill-groups/ai-software-engineering-platform-enterprise/docs/STATE_PROTOCOL.md"
)
PRODUCT_NAME = "Hiker Engineering Capability System（Hiker 工程能力系统）"
CHECKPOINT_MARKER = (
    "<!-- document-class: checkpoint; current-facts-source: "
    "scripts/audit_release_facts.py -->"
)
RAN_TESTS_RE = re.compile(r"\bRan\s+(\d+)\s+tests?\b")
CURRENT_MARKER_RE = re.compile(r"<!-- engineering-current-facts: [^>]+ -->")
LIFECYCLE_MARKER_RE = re.compile(r"<!-- task-lifecycle: [^>]+ -->")


@dataclass(frozen=True)
class ReleaseFacts:
    repository_version: str
    engineering_version: str
    engineering_full_version: str
    desktop_version: str
    plugin_count: int
    skill_count: int
    source_test_count: int
    task_states: tuple[str, ...]

    @property
    def lifecycle(self) -> str:
        return " → ".join(self.task_states)

    @property
    def marker(self) -> str:
        return (
            "<!-- engineering-current-facts: "
            f"version={self.engineering_version}; plugins={self.plugin_count}; "
            f"skills={self.skill_count}; tests={self.source_test_count} -->"
        )

    @property
    def lifecycle_marker(self) -> str:
        return f"<!-- task-lifecycle: {self.lifecycle} -->"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_version_source(root: Path) -> dict[str, str]:
    path = root / VERSION_SOURCE
    value = json.loads(read_text(path))
    required = ("repository", "engineering", "desktop")
    missing = [key for key in required if not str(value.get(key) or "").strip()]
    if missing:
        raise ValueError(f"{VERSION_SOURCE} missing versions: {missing}")
    return {key: str(value[key]).strip() for key in required}


def _load_governance_state(path: Path) -> ModuleType:
    scripts = path.parent
    inserted = str(scripts)
    sys.path.insert(0, inserted)
    try:
        spec = importlib.util.spec_from_file_location("hiker_release_governance_state", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load governance state: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == inserted:
            sys.path.pop(0)


def _count_source_tests(suite: Path) -> int:
    count = 0
    for path in sorted(suite.glob("plugins/*/tests/test_*.py")):
        tree = ast.parse(read_text(path), filename=str(path))
        count += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return count


def derive_facts(root: Path) -> tuple[ReleaseFacts, dict[str, dict[str, object]]]:
    version_source = load_version_source(root)
    suite = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    plugins_root = suite / "plugins"
    manifests: dict[str, dict[str, object]] = {}
    full_versions: set[str] = set()
    public_versions: set[str] = set()
    skill_count = 0
    for plugin in sorted(path for path in plugins_root.iterdir() if path.is_dir()):
        manifest = json.loads(read_text(plugin / ".codex-plugin" / "plugin.json"))
        manifests[plugin.name] = manifest
        full_version = str(manifest["version"])
        full_versions.add(full_version)
        public_versions.add(full_version.split("+", 1)[0])
        skill_count += len(list((plugin / "skills").glob("*/SKILL.md")))
    if len(full_versions) != 1 or len(public_versions) != 1:
        raise ValueError(
            "five engineering plugins must share one exact version: "
            f"{sorted(full_versions)}"
        )
    manifest_version = next(iter(full_versions))
    if manifest_version != version_source["engineering"]:
        raise ValueError(
            f"plugin manifests differ from {VERSION_SOURCE}: "
            f"{manifest_version} != {version_source['engineering']}"
        )
    repository_version = read_text(root / "VERSION").strip()
    if repository_version != version_source["repository"]:
        raise ValueError(
            f"VERSION differs from {VERSION_SOURCE}: "
            f"{repository_version} != {version_source['repository']}"
        )
    desktop_version = read_text(root / "skill-groups" / "desktop-app-reconstruction-zh" / "VERSION").strip()
    if desktop_version != version_source["desktop"]:
        raise ValueError(
            f"desktop VERSION differs from {VERSION_SOURCE}: "
            f"{desktop_version} != {version_source['desktop']}"
        )
    governance = _load_governance_state(
        suite / "plugins" / "ai-engineering-workspace" / "scripts" / "governance_state.py"
    )
    states = tuple(str(item) for item in getattr(governance, "TASK_STATES", ()))
    if not states:
        raise ValueError("governance_state.TASK_STATES is empty")
    facts = ReleaseFacts(
        repository_version=version_source["repository"],
        engineering_version=next(iter(public_versions)),
        engineering_full_version=version_source["engineering"],
        desktop_version=version_source["desktop"],
        plugin_count=len(manifests),
        skill_count=skill_count,
        source_test_count=_count_source_tests(suite),
        task_states=states,
    )
    return facts, manifests


def _replace_required(text: str, pattern: str, replacement: str, relative: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"cannot synchronize version surface: {relative}: {pattern}")
    return updated


def synchronize(root: Path) -> dict[str, object]:
    """Generate all mutable version surfaces from release-versions.json."""
    root = root.resolve()
    source = load_version_source(root)
    suite = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    changed: list[str] = []

    def write(relative: str | Path, text: str) -> None:
        relative_text = Path(relative).as_posix()
        path = root / relative_text
        previous = read_text(path) if path.is_file() else ""
        if previous != text:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed.append(relative_text)

    write("VERSION", source["repository"] + "\n")
    write("skill-groups/desktop-app-reconstruction-zh/VERSION", source["desktop"] + "\n")
    for plugin in sorted(path for path in (suite / "plugins").iterdir() if path.is_dir()):
        relative = plugin.relative_to(root) / ".codex-plugin" / "plugin.json"
        manifest = json.loads(read_text(root / relative))
        if str(manifest.get("version") or "") != source["engineering"]:
            manifest["version"] = source["engineering"]
            write(relative.as_posix(), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    facts, _ = derive_facts(root)
    for relative in MARKER_DOCS:
        text = read_text(root / relative)
        text = _replace_required(text, r"<!-- engineering-current-facts: [^>]+ -->", facts.marker, relative)
        write(relative, text)
    installation = "docs/INSTALLATION.md"
    text = read_text(root / installation)
    text = _replace_required(text, r"发布源码对应 \d+ 项源码测试", f"发布源码对应 {facts.source_test_count} 项源码测试", installation)
    write(installation, text)
    return {"ok": True, "source": VERSION_SOURCE, "facts": asdict(facts), "changed": changed}


def _audit_current_docs(root: Path, facts: ReleaseFacts) -> list[str]:
    errors: list[str] = []
    for relative in MARKER_DOCS:
        path = root / relative
        if not path.is_file():
            errors.append(f"current document is missing: {relative}")
            continue
        text = read_text(path)
        markers = CURRENT_MARKER_RE.findall(text)
        if markers != [facts.marker]:
            errors.append(f"{relative}: missing or stale current-facts marker: {facts.marker}")
    root_readme = read_text(root / "README.md")
    root_tokens = (
        f"repo={facts.repository_version}; engineering={facts.engineering_version}; "
        f"plugins={facts.plugin_count}; "
        f"engineering-skills={facts.skill_count};",
        f"> 仓库版本：`{facts.repository_version}`",
        f"## 智能软件工程平台 {facts.engineering_version}",
    )
    for token in root_tokens:
        if token not in root_readme:
            errors.append(f"README.md: missing or stale current release fact: {token}")
    suite_readme_path = (
        root / "skill-groups" / "ai-software-engineering-platform-enterprise" / "README_CN.md"
    )
    suite_readme = read_text(suite_readme_path)
    short_version = ".".join(facts.engineering_version.split(".")[:2])
    if f"# 智能软件工程平台 {short_version}" not in suite_readme:
        errors.append(
            "skill-groups/ai-software-engineering-platform-enterprise/README_CN.md: "
            f"missing current suite heading for {facts.engineering_version}"
        )
    installation = read_text(root / "docs" / "INSTALLATION.md")
    for token in (
        PRODUCT_NAME,
        f"## 智能软件工程平台 {facts.engineering_version}",
        f"{facts.plugin_count} 个插件、{facts.skill_count} 个 Skill",
        f"{facts.source_test_count} 项源码测试",
    ):
        if token not in installation:
            errors.append(f"docs/INSTALLATION.md: missing current release fact: {token}")
    multi = read_text(root / "docs" / "MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md")
    if PRODUCT_NAME not in multi:
        errors.append(f"docs/MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md: missing product position: {PRODUCT_NAME}")
    if LIFECYCLE_MARKER_RE.findall(multi) != [facts.lifecycle_marker]:
        errors.append(
            "docs/MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md: lifecycle differs from "
            f"governance_state.TASK_STATES: {facts.lifecycle}"
        )
    protocol = read_text(root / STATE_PROTOCOL_DOC)
    if LIFECYCLE_MARKER_RE.findall(protocol) != [facts.lifecycle_marker]:
        errors.append(
            f"{STATE_PROTOCOL_DOC}: lifecycle differs from governance_state.TASK_STATES: "
            f"{facts.lifecycle}"
        )
    host_boundary = (
        "桌面任务归档与本地工具运行时释放由 ChatGPT Desktop / Codex 宿主显式执行；"
        "本地脚本只验证并记录结果"
    )
    for relative in (
        "docs/MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md",
        "skill-groups/ai-software-engineering-platform-enterprise/plugins/"
        "ai-engineering-workspace/README_CN.md",
    ):
        if host_boundary not in read_text(root / relative):
            errors.append(f"{relative}: missing host/runtime boundary statement")
    checkpoint = root / CHECKPOINT_DOC
    checkpoint_text = read_text(checkpoint) if checkpoint.is_file() else ""
    if CHECKPOINT_MARKER not in checkpoint_text:
        errors.append(f"{CHECKPOINT_DOC}: checkpoint classification marker is missing")
    if CURRENT_MARKER_RE.search(checkpoint_text):
        errors.append(f"{CHECKPOINT_DOC}: checkpoint must not claim current release facts")
    return errors


def _reported_test_count(report: dict[str, object]) -> tuple[int, list[str]]:
    errors: list[str] = []
    structured_total = report.get("test_count")
    has_structured_total = isinstance(structured_total, int) and not isinstance(
        structured_total, bool
    )
    if report.get("test_count_complete") is False:
        errors.append("test-results.json: structured test count is incomplete")
    item_total = 0
    item_counts_complete = True
    results = report.get("results")
    if not isinstance(results, list):
        return 0, ["test-results.json: results must be a list"]
    for item in results:
        if not isinstance(item, dict):
            errors.append("test-results.json: invalid plugin result")
            continue
        explicit = item.get("test_count")
        if isinstance(explicit, int) and not isinstance(explicit, bool):
            item_total += explicit
            continue
        matches = RAN_TESTS_RE.findall(str(item.get("output_excerpt") or ""))
        if len(matches) != 1:
            item_counts_complete = False
            errors.append(
                f"test-results.json: cannot derive exact test count for {item.get('plugin')}"
            )
            continue
        item_total += int(matches[0])
    if has_structured_total:
        if item_counts_complete and item_total != structured_total:
            errors.append(
                "test-results.json: structured test count differs from plugin results: "
                f"{structured_total} != {item_total}"
            )
        return int(structured_total), errors
    return item_total, errors


def _test_source_fingerprint(root: Path, plugin_names: set[str]) -> str:
    suite = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    bases = [suite / "plugins" / name for name in sorted(plugin_names)] + [suite / "tools"]
    digest = hashlib.sha256()
    for base in bases:
        for path in sorted(
            item
            for item in base.rglob("*")
            if item.is_file()
            and item.suffix.lower() in {".py", ".md", ".json", ".yaml", ".yml", ".csv"}
            and ".codex-output" not in item.parts
        ):
            digest.update(path.relative_to(suite).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def _audit_test_report(root: Path, facts: ReleaseFacts, manifests: dict[str, object]) -> list[str]:
    report_path = (
        root
        / "skill-groups"
        / "ai-software-engineering-platform-enterprise"
        / "test-results.json"
    )
    if not report_path.is_file():
        return ["current full test report is missing: test-results.json"]
    report = json.loads(read_text(report_path))
    errors: list[str] = []
    if not report.get("ok") or report.get("partial"):
        errors.append("test-results.json must be a successful non-partial run")
    actual_plugins = set(str(item) for item in (report.get("plugins") or []))
    if actual_plugins != set(manifests):
        errors.append(
            "test-results.json plugin set differs from current manifests: "
            f"{sorted(actual_plugins)} != {sorted(manifests)}"
        )
    expected_fingerprint = _test_source_fingerprint(root, set(manifests))
    if report.get("source_fingerprint") != expected_fingerprint:
        errors.append(
            "test-results.json is stale for the current source: "
            f"{report.get('source_fingerprint')} != {expected_fingerprint}"
        )
    reported_count, count_errors = _reported_test_count(report)
    errors.extend(count_errors)
    if reported_count != facts.source_test_count:
        errors.append(
            "test-results.json count differs from source tests: "
            f"{reported_count} != {facts.source_test_count}"
        )
    return errors


def _audit_archives(
    root: Path,
    facts: ReleaseFacts,
    manifests: dict[str, dict[str, object]],
) -> list[str]:
    suite = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    errors: list[str] = []
    expected_names = {f"{name}-{facts.engineering_version}.zip" for name in manifests}
    actual_names = {path.name for path in (suite / "dist").glob("*.zip")}
    if actual_names != expected_names:
        errors.append(
            "dist must contain exactly the current five plugin archives: "
            f"missing={sorted(expected_names - actual_names)} "
            f"extra={sorted(actual_names - expected_names)}"
        )
    for plugin_name, source_manifest in manifests.items():
        archive_path = suite / "dist" / f"{plugin_name}-{facts.engineering_version}.zip"
        if not archive_path.is_file():
            continue
        source_readme_path = suite / "plugins" / plugin_name / "README_CN.md"
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                broken = archive.testzip()
                if broken:
                    errors.append(f"{archive_path.name}: corrupt member: {broken}")
                    continue
                archived_manifest = json.loads(
                    archive.read("./.codex-plugin/plugin.json").decode("utf-8-sig")
                )
                archived_readme = archive.read("./README_CN.md")
                archived_skill_count = sum(
                    1
                    for name in archive.namelist()
                    if name.startswith("./skills/") and name.endswith("/SKILL.md")
                )
        except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            errors.append(f"{archive_path.name}: cannot inspect release facts: {exc}")
            continue
        if archived_manifest != source_manifest:
            errors.append(f"{archive_path.name}: archived manifest differs from source")
        if not source_readme_path.is_file():
            errors.append(f"{plugin_name}: source README_CN.md is missing")
        elif sha256_bytes(archived_readme) != sha256_bytes(source_readme_path.read_bytes()):
            errors.append(f"{archive_path.name}: archived README_CN.md is stale")
        source_skill_count = len(list((suite / "plugins" / plugin_name / "skills").glob("*/SKILL.md")))
        if archived_skill_count != source_skill_count:
            errors.append(
                f"{archive_path.name}: archived Skill count differs from source: "
                f"{archived_skill_count} != {source_skill_count}"
            )
    return errors


def audit(
    root: Path,
    *,
    require_archives: bool,
    require_test_report: bool,
) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    try:
        facts, manifests = derive_facts(root)
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        SyntaxError,
        ImportError,
        AttributeError,
        RuntimeError,
    ) as exc:
        return {"ok": False, "errors": [f"cannot derive current release facts: {exc}"]}
    if facts.plugin_count != 5:
        errors.append(f"current engineering suite must contain 5 plugins, got {facts.plugin_count}")
    if facts.skill_count != 42:
        errors.append(f"current engineering suite must contain 42 Skills, got {facts.skill_count}")
    errors.extend(_audit_current_docs(root, facts))
    if require_test_report:
        try:
            errors.extend(_audit_test_report(root, facts, manifests))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot audit current test report: {exc}")
    if require_archives:
        errors.extend(_audit_archives(root, facts, manifests))
    return {
        "ok": not errors,
        "document_classes": {
            "current": list(CURRENT_DOCS) + [STATE_PROTOCOL_DOC],
            "history": ["CHANGELOG.md", "versioned migration records"],
            "checkpoint": [CHECKPOINT_DOC],
        },
        "facts": {
            **asdict(facts),
            "lifecycle": facts.lifecycle,
            "marker": facts.marker,
            "lifecycle_marker": facts.lifecycle_marker,
        },
        "version_source": VERSION_SOURCE,
        "archives_checked": require_archives,
        "test_report_checked": require_test_report,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="审计当前发布事实、生命周期和ZIP内README")
    parser.add_argument("--root", required=True, help="仓库根目录")
    parser.add_argument("--no-archives", action="store_true", help="打包前只检查源码事实")
    parser.add_argument(
        "--skip-test-report",
        action="store_true",
        help="只按源码统计测试数量，不要求已有测试报告",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="从 release-versions.json 生成 VERSION、Manifest 与当前文档事实",
    )
    args = parser.parse_args()
    if args.sync:
        result = synchronize(Path(args.root))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    report = audit(
        Path(args.root),
        require_archives=not args.no_archives,
        require_test_report=not args.skip_test_report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
