#!/usr/bin/env python3
"""Validate the G5-T technology stack and exact-version gate.

The script never executes commands supplied by project files.  It uses a fixed
allow-list of read-only version commands and verifies manifest paths when the
lock names them as evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from lib_recon import (
    get_nested,
    is_pass,
    is_true,
    is_unknown,
    markdown_table,
    normalized,
    parse_simple_yaml,
    read_csv_rows,
    split_ids,
    write_json,
)

FLOATING_PATTERNS = [
    re.compile(r"(^|\s)(latest|stable|lts)(\s|$)", re.I),
    re.compile(r"[\*^~<>]"),
    re.compile(r"(^|[.\-])x($|[.\-])", re.I),
    re.compile(r"\|\||\s-\s"),
]

# Fixed, read-only version commands.  Keys are matched as substrings against
# the component name.  Commands from project files are deliberately ignored.
COMMAND_ADAPTERS: list[tuple[tuple[str, ...], list[list[str]]]] = [
    (("python",), [["python", "--version"], ["python3", "--version"]]),
    (("node", "node.js"), [["node", "--version"]]),
    (("npm",), [["npm", "--version"]]),
    (("pnpm",), [["pnpm", "--version"]]),
    (("yarn",), [["yarn", "--version"]]),
    (("bun",), [["bun", "--version"]]),
    ((".net", "dotnet"), [["dotnet", "--version"]]),
    (("msbuild",), [["dotnet", "msbuild", "-version"], ["msbuild", "-version"]]),
    (("rust", "rustc"), [["rustc", "--version"]]),
    (("cargo",), [["cargo", "--version"]]),
    (("java", "jdk"), [["java", "-version"], ["javac", "-version"]]),
    (("gradle",), [["gradle", "--version"], ["./gradlew", "--version"]]),
    (("maven",), [["mvn", "--version"]]),
    (("cmake",), [["cmake", "--version"]]),
    (("qt", "qmake"), [["qmake6", "--version"], ["qmake", "--version"]]),
    (("go", "golang"), [["go", "version"]]),
    (("swift",), [["swift", "--version"]]),
    (("dart",), [["dart", "--version"]]),
    (("flutter",), [["flutter", "--version"]]),
    (("gcc", "g++"), [["g++", "--version"], ["gcc", "--version"]]),
    (("clang",), [["clang++", "--version"], ["clang", "--version"]]),
]


def has_floating_version(value: str) -> bool:
    text = value.strip()
    if is_unknown(text):
        return True
    return any(pattern.search(text) for pattern in FLOATING_PATTERNS)


def version_tokens(value: str) -> list[str]:
    tokens = re.findall(r"\d+(?:\.\d+){0,4}(?:[-+][0-9A-Za-z.-]+)?", value)
    return tokens or [value.strip().lower()]


def versions_match(expected: str, actual: str) -> bool:
    expected_tokens = version_tokens(expected)
    actual_tokens = version_tokens(actual)
    if not expected_tokens or not actual_tokens:
        return normalized(expected) in normalized(actual)
    expected_main = expected_tokens[0].lstrip("v")
    return any(token.lstrip("v") == expected_main for token in actual_tokens)


def adapter_commands(name: str) -> list[list[str]]:
    lower = name.lower()
    for aliases, commands in COMMAND_ADAPTERS:
        if any(alias in lower for alias in aliases):
            return commands
    return []


def run_fixed_version_command(commands: list[list[str]], cwd: Path) -> tuple[str | None, list[str]]:
    attempts: list[str] = []
    for command in commands:
        executable = command[0]
        if executable.startswith("./"):
            candidate = cwd / executable[2:]
            if not candidate.exists():
                attempts.append(f"missing:{candidate}")
                continue
            command = [str(candidate), *command[1:]]
        elif shutil.which(executable) is None:
            attempts.append(f"missing:{executable}")
            continue
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            attempts.append(f"error:{' '.join(command)}:{exc}")
            continue
        output = completed.stdout.strip()
        attempts.append(f"{' '.join(command)} => rc={completed.returncode}: {output[:300]}")
        if output:
            return output, attempts
    return None, attempts


def source_path_verification(root: Path, source: str, expected: str) -> tuple[bool, str]:
    source = source.strip()
    if not source:
        return False, "未提供 verification_source"
    source_path = (root / source).resolve()
    try:
        source_path.relative_to(root.resolve())
    except ValueError:
        return False, "verification_source 越出项目目录"
    if not source_path.is_file():
        return False, f"verification_source 不是文件：{source}"
    try:
        text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return False, f"无法读取 verification_source：{exc}"
    if expected.lower() in text.lower() or versions_match(expected, text):
        return True, f"版本出现在 {source}"
    return False, f"{source} 中未找到精确版本 {expected}"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 G5-T 技术栈、精确版本和平台门禁")
    parser.add_argument("project_dir")
    parser.add_argument("--json", dest="json_output", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--no-fail", action="store_true", help="仍写报告但不以门禁失败作为进程失败")
    args = parser.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"错误：项目目录不存在：{root}", file=sys.stderr)
        return 2

    lock_path = root / "05_technical_design" / "TECH_STACK_LOCK.yaml"
    decision_path = root / "05_technical_design" / "TECH_STACK_DECISION.yaml"
    docs_path = root / "05_technical_design" / "OFFICIAL_DOC_INDEX.csv"
    candidates_path = root / "05_technical_design" / "TECH_STACK_CANDIDATES.csv"
    platform_path = root / "01_environment" / "PLATFORM_COMPATIBILITY_MATRIX.csv"
    dependency_path = root / "05_technical_design" / "DEPENDENCY_INVENTORY.csv"

    missing_inputs = [
        str(path.relative_to(root))
        for path in (lock_path, decision_path, docs_path, candidates_path, platform_path, dependency_path)
        if not path.is_file()
    ]
    if missing_inputs:
        result = {
            "schema_version": "1.1", "gate_id": "G5-T", "gate": "FAIL",
            "pass": False, "project_dir": str(root), "missing_inputs": missing_inputs,
            "errors": ["缺少必需输入：" + ";".join(missing_inputs)], "warnings": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.json_output:
            write_json(Path(args.json_output).expanduser().resolve(), result)
        return 0 if args.no_fail else 1

    try:
        lock = parse_simple_yaml(lock_path)
        decision = parse_simple_yaml(decision_path)
    except (ValueError, OSError) as exc:
        print(f"错误：YAML 解析失败：{exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    component_results: list[dict[str, Any]] = []

    lock_status = str(lock.get("lock_status", "")) if isinstance(lock, dict) else ""
    if normalized(lock_status) != "locked":
        errors.append(f"TECH_STACK_LOCK.lock_status 必须为 LOCKED，当前为 {lock_status or '空'}")

    components = lock.get("components", {}) if isinstance(lock, dict) else {}
    if not isinstance(components, dict) or not components:
        errors.append("TECH_STACK_LOCK.components 为空")
        components = {}

    docs = read_csv_rows(docs_path)
    docs_by_component: dict[str, list[dict[str, str]]] = {}
    for row in docs:
        keys = {normalized(row.get("component_id")), normalized(row.get("component_name"))}
        for key in keys:
            if key:
                docs_by_component.setdefault(key, []).append(row)

    for component_id, raw in components.items():
        if not isinstance(raw, dict):
            errors.append(f"组件 {component_id} 不是映射")
            continue
        required = bool(raw.get("required")) if isinstance(raw.get("required"), bool) else is_true(raw.get("required"))
        name = str(raw.get("name", ""))
        exact_version = str(raw.get("exact_version", ""))
        verification_source = str(raw.get("verification_source", ""))
        verification_status = str(raw.get("verification_status", ""))
        item: dict[str, Any] = {
            "component_id": component_id,
            "required": required,
            "name": name,
            "expected_version": exact_version,
            "declared_status": verification_status,
            "automated_actual": None,
            "automated_match": None,
            "source_match": None,
            "official_doc_match": False,
            "messages": [],
        }

        if not required:
            item["result"] = "NOT_APPLICABLE" if normalized(verification_status) == "not_applicable" else "OPTIONAL"
            component_results.append(item)
            continue

        if is_unknown(name):
            errors.append(f"必需组件 {component_id} 未锁定名称")
            item["messages"].append("名称未锁定")
        if has_floating_version(exact_version):
            errors.append(f"必需组件 {component_id} 使用未知或浮动版本：{exact_version}")
            item["messages"].append("版本不是精确值")
        if not is_pass(verification_status):
            errors.append(f"必需组件 {component_id} verification_status 未通过：{verification_status}")
            item["messages"].append("声明验证状态未通过")

        source_ok, source_message = source_path_verification(root, verification_source, exact_version)
        item["source_match"] = source_ok
        item["messages"].append(source_message)

        commands = adapter_commands(name)
        if commands:
            actual, attempts = run_fixed_version_command(commands, root)
            item["command_attempts"] = attempts
            if actual is not None:
                item["automated_actual"] = actual[:1000]
                item["automated_match"] = versions_match(exact_version, actual)
                if not item["automated_match"]:
                    errors.append(
                        f"组件 {component_id} 安装版本与锁定值不一致：expected={exact_version}, actual={actual.splitlines()[0][:120]}"
                    )
            else:
                warnings.append(f"组件 {component_id} 未找到可用的固定版本命令")
        else:
            warnings.append(f"组件 {component_id} 无内置命令适配器，依赖清单/文件证据和人工复核")

        doc_candidates = docs_by_component.get(normalized(component_id), []) + docs_by_component.get(normalized(name), [])
        seen_ids: set[str] = set()
        unique_docs: list[dict[str, str]] = []
        for row in doc_candidates:
            key = row.get("doc_id", "") or json.dumps(row, sort_keys=True)
            if key not in seen_ids:
                seen_ids.add(key)
                unique_docs.append(row)
        for row in unique_docs:
            if (
                versions_match(exact_version, row.get("locked_version", ""))
                and is_pass(row.get("verification_status"))
                and normalized(row.get("source_type")) in {"official", "official_repository", "vendor_official"}
            ):
                item["official_doc_match"] = True
                item["official_doc_id"] = row.get("doc_id", "")
                break
        if not item["official_doc_match"]:
            errors.append(f"必需组件 {component_id} 缺少对应精确版本的已核验官方文档记录")

        if not source_ok and item.get("automated_match") is not True:
            errors.append(f"必需组件 {component_id} 没有可复核的本地精确版本证据")

        item["result"] = "PASS" if not any(
            message for message in item["messages"] if message in {"名称未锁定", "版本不是精确值", "声明验证状态未通过"}
        ) and item["official_doc_match"] and (source_ok or item.get("automated_match") is True) else "FAIL"
        component_results.append(item)

    # Technology decision and POC.
    decision_status = str(decision.get("status", "")) if isinstance(decision, dict) else ""
    selected_candidate = str(decision.get("selected_candidate_id", "")) if isinstance(decision, dict) else ""
    poc_result = str(get_nested(decision, "poc", "overall_result", default=""))
    if normalized(decision_status) not in {"accepted", "approved"}:
        errors.append(f"TECH_STACK_DECISION.status 必须为 ACCEPTED，当前为 {decision_status or '空'}")
    if is_unknown(selected_candidate):
        errors.append("TECH_STACK_DECISION.selected_candidate_id 未确定")
    if not is_pass(poc_result):
        errors.append(f"代表性 POC overall_result 未通过：{poc_result or '空'}")

    candidate_rows = read_csv_rows(candidates_path)
    if selected_candidate and not any(row.get("candidate_id") == selected_candidate for row in candidate_rows):
        errors.append(f"选中候选 {selected_candidate} 不存在于 TECH_STACK_CANDIDATES.csv")
    selected_rows = [row for row in candidate_rows if row.get("candidate_id") == selected_candidate]
    if selected_rows and not is_pass(selected_rows[0].get("poc_status")):
        errors.append(f"选中候选 {selected_candidate} 的 poc_status 未通过")
    if len([row for row in candidate_rows if row.get("candidate_id")]) < 2:
        warnings.append("候选少于两个；应在决策中记录充分的排他理由。")

    # Platform compatibility.
    platform_results: list[dict[str, Any]] = []
    for row in read_csv_rows(platform_path):
        if not is_true(row.get("required")):
            continue
        result = row.get("result", "")
        item = {
            "platform_id": row.get("platform_id", ""),
            "platform": f"{row.get('os_name', '')} {row.get('os_version', '')} {row.get('architecture', '')}".strip(),
            "result": result,
        }
        platform_results.append(item)
        if not is_pass(result):
            errors.append(f"必需平台 {item['platform_id']} 未通过：{result or '空'}")
        for field in ("framework_support_status", "runtime_support_status", "installer_support_status", "poc_status"):
            if not is_pass(row.get(field, "")):
                errors.append(f"必需平台 {item['platform_id']} 的 {field} 未通过：{row.get(field, '') or '空'}")

    if not platform_results:
        errors.append("PLATFORM_COMPATIBILITY_MATRIX.csv 没有 required=true 的平台")

    # Dependency locks.
    dependency_errors: list[str] = []
    for row in read_csv_rows(dependency_path):
        if not is_true(row.get("required")):
            continue
        dep_id = row.get("dependency_id", row.get("name", "UNKNOWN"))
        version = row.get("exact_version", "")
        if has_floating_version(version):
            dependency_errors.append(f"依赖 {dep_id} 不是精确版本：{version}")
        lock_file = row.get("lock_file", "").strip()
        if not lock_file:
            dependency_errors.append(f"依赖 {dep_id} 未记录 lock_file")
        else:
            candidate = (root / lock_file).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                dependency_errors.append(f"依赖 {dep_id} lock_file 越出项目目录")
            else:
                if not candidate.is_file():
                    dependency_errors.append(f"依赖 {dep_id} lock_file 不存在：{lock_file}")
    errors.extend(dependency_errors)

    expected_lock_files = get_nested(lock, "dependency_policy", "expected_lock_files", default=[])
    if isinstance(expected_lock_files, str):
        expected_lock_files = split_ids(expected_lock_files)
    if not isinstance(expected_lock_files, list):
        expected_lock_files = []
    if is_true(get_nested(lock, "dependency_policy", "lock_files_required", default=False)) and not expected_lock_files:
        errors.append("TECH_STACK_LOCK 要求锁文件，但 expected_lock_files 为空")
    for value in expected_lock_files:
        lock_file = (root / str(value)).resolve()
        try:
            lock_file.relative_to(root)
        except ValueError:
            errors.append(f"expected_lock_files 路径越界：{value}")
        else:
            if not lock_file.is_file():
                errors.append(f"expected_lock_files 不存在：{value}")

    # Reproducibility, license and security review are hard G5-T requirements.
    reproducibility = get_nested(lock, "build_reproducibility", default={})
    if not isinstance(reproducibility, dict):
        reproducibility = {}
    for key in ("clean_build_verified", "clean_test_verified", "artifact_checksum_verified"):
        if not is_true(reproducibility.get(key)):
            errors.append(f"build_reproducibility.{key} 未通过")
    if not is_pass(reproducibility.get("verification_status")):
        errors.append("build_reproducibility.verification_status 未通过")
    if not reproducibility.get("build_commands"):
        errors.append("build_reproducibility.build_commands 为空")
    if not reproducibility.get("test_commands"):
        errors.append("build_reproducibility.test_commands 为空")
    if not reproducibility.get("output_paths"):
        errors.append("build_reproducibility.output_paths 为空")
    if not is_pass(lock.get("license_review_status")):
        errors.append("license_review_status 未通过")
    if not is_pass(lock.get("security_review_status")):
        errors.append("security_review_status 未通过")

    passed = not errors
    result = {
        "schema_version": "1.1",
        "gate_id": "G5-T",
        "gate": "PASS" if passed else "FAIL",
        "project_dir": str(root),
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pass": passed,
        "lock_status": lock_status,
        "decision_status": decision_status,
        "selected_candidate_id": selected_candidate,
        "poc_result": poc_result,
        "build_reproducibility": reproducibility,
        "components": component_results,
        "platforms": platform_results,
        "errors": errors,
        "warnings": warnings,
        "boundary": "自动验证只覆盖模板字段、白名单版本命令、项目文件和索引；人工兼容测试仍是必需门禁。",
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_output:
        write_json(Path(args.json_output).expanduser().resolve(), result)

    report_path = Path(args.report).expanduser().resolve() if args.report else root / "09_reports" / "TECHNOLOGY_VALIDATION_REPORT.md"
    component_table = markdown_table(
        ["组件", "名称", "锁定版本", "声明状态", "本地证据", "官方文档", "结果"],
        [
            [
                item["component_id"],
                item["name"],
                item["expected_version"],
                item["declared_status"],
                "PASS" if item.get("source_match") or item.get("automated_match") else "FAIL/NA",
                "PASS" if item.get("official_doc_match") else "FAIL/NA",
                item.get("result", ""),
            ]
            for item in component_results
        ],
    )
    platform_table = markdown_table(
        ["平台 ID", "平台", "结果"],
        [[item["platform_id"], item["platform"], item["result"]] for item in platform_results],
    )
    report = (
        "<!-- document_status: " + ("PASS" if passed else "FAIL") + " -->\n"
        "# 技术栈与版本验证报告\n\n"
        f"- 检查时间：{result['checked_at']}\n"
        f"- 项目：`{root}`\n"
        f"- G5-T：{'PASS' if passed else 'FAIL'}\n\n"
        "## 1. 精确版本组件\n\n"
        + component_table
        + "\n\n## 2. 平台兼容\n\n"
        + platform_table
        + "\n\n## 3. 错误\n\n"
        + ("\n".join(f"- {item}" for item in errors) if errors else "- 无。")
        + "\n\n## 4. 警告\n\n"
        + ("\n".join(f"- {item}" for item in warnings) if warnings else "- 无。")
        + "\n\n## 5. 结论\n\n"
        + ("PASS" if passed else "FAIL")
        + "\n"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    concise_path = root / "09_reports" / "TOOLCHAIN_VALIDATION_REPORT.md"
    if concise_path.resolve() != report_path.resolve():
        concise_path.write_text(report, encoding="utf-8", newline="\n")
    return 0 if passed or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
