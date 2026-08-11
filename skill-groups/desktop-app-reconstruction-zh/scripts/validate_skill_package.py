#!/usr/bin/env python3
"""Validate a standalone OpenAI Agent Skill directory or ZIP.

The validator is intentionally standard-library only. It checks the standalone
Skill layout, SKILL.md front matter, agents/openai.yaml metadata, declared
assets, script syntax, package cleanliness, archive safety, and optionally runs
the deterministic regression self-test.
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from common import sha256_file, sha256_path, write_json
from lib_recon import parse_simple_yaml

FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SAFE_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
TEXT_REFERENCE_RE = re.compile(r"(?P<path>(?:references|scripts|assets)/[A-Za-z0-9_./\-\u4e00-\u9fff]+\.(?:md|py|yaml|yml|csv|svg|json))")

REQUIRED_REFERENCES = [f"{index:02d}_" for index in range(1, 20)]
REQUIRED_SCRIPTS = {
    "scripts/init_project.py",
    "scripts/index_evidence.py",
    "scripts/detect_project_stack.py",
    "scripts/validate_toolchain.py",
    "scripts/validate_discovery.py",
    "scripts/calculate_coverage.py",
    "scripts/validate_traceability.py",
    "scripts/detect_orphan_items.py",
    "scripts/compare_screenshots.py",
    "scripts/validate_deliverables.py",
    "scripts/validate_project.py",
    "scripts/run_quality_gates.py",
    "scripts/validate_skill_package.py",
    "scripts/self_test.py",
    "scripts/install_skill.py",
}
REQUIRED_ATOMIC_SKILLS = {
    "desktop-reconstruction-discovery",
    "desktop-reconstruction-technical-design",
    "desktop-reconstruction-implementation",
    "desktop-reconstruction-verification-release",
}
REQUIRED_ROOT_ENTRIES = {
    "SKILL.md",
    "VERSION",
    "README_安装与使用.md",
    "CHANGELOG.md",
    "agents/openai.yaml",
    "assets/icon-small.svg",
    "assets/project-template",
    "references",
    "scripts",
    "evals",
    "INSTALL_WINDOWS.ps1",
    "INSTALL_MAC_LINUX.sh",
}
IGNORED_CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
FORBIDDEN_PACKAGED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SECRET_FILE_PATTERNS = (
    re.compile(r"(^|/)(\.env(?:\..*)?)$", re.IGNORECASE),
    re.compile(r"(^|/)(id_rsa|id_ed25519|credentials\.json|service-account.*\.json)$", re.IGNORECASE),
    re.compile(r"\.(pem|p12|pfx|key)$", re.IGNORECASE),
)


def safe_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_RE.match(text)
    if not match:
        raise ValueError("SKILL.md 必须从第一行开始使用 --- YAML 前置区")
    values: dict[str, str] = {}
    for line_no, raw in enumerate(match.group(1).splitlines(), start=2):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"SKILL.md 前置区第 {line_no} 行缺少冒号")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"SKILL.md 前置区第 {line_no} 行键为空")
        if value.startswith(("\"", "'")) and value.endswith(value[:1]) and len(value) >= 2:
            value = value[1:-1]
        values[key] = value
    return values, text[match.end():]


def path_inside(root: Path, declared: str) -> tuple[bool, Path]:
    if not declared.startswith("./"):
        return False, root
    pure = PurePosixPath(declared[2:])
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        return False, root
    target = (root / Path(*pure.parts)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False, target
    return True, target


def validate_svg(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ET.ParseError) as exc:
        return [f"SVG 无法解析：{exc}"]
    tag = root.tag.split("}")[-1]
    if tag != "svg":
        issues.append("SVG 根元素不是 <svg>")
    width = height = None
    view_box = root.attrib.get("viewBox", "").strip().split()
    if len(view_box) == 4:
        try:
            width = float(view_box[2]); height = float(view_box[3])
        except ValueError:
            issues.append("SVG viewBox 不是数值")
    else:
        raw_w = root.attrib.get("width", "")
        raw_h = root.attrib.get("height", "")
        try:
            width = float(raw_w); height = float(raw_h)
        except (TypeError, ValueError):
            issues.append("SVG 缺少数值 viewBox，且 width/height 不是纯数值")
    if width is not None and height is not None:
        if width <= 0 or height <= 0:
            issues.append("SVG 尺寸必须为正数")
        if abs(width - height) > 1e-9:
            issues.append("SVG 图标必须为正方形")
        if width < 48 or height < 48:
            issues.append("SVG 图标尺寸不得小于 48×48")
    return issues


def validate_openai_yaml(root: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    path = root / "agents" / "openai.yaml"
    issues: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return {}, ["缺少 agents/openai.yaml"], warnings
    try:
        data = parse_simple_yaml(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {}, [f"agents/openai.yaml 无法解析：{exc}"], warnings
    if not isinstance(data, dict):
        return {}, ["agents/openai.yaml 顶层必须是映射"], warnings
    interface = data.get("interface")
    if not isinstance(interface, dict):
        issues.append("agents/openai.yaml 缺少 interface 映射")
        interface = {}
    display_name = interface.get("display_name")
    short_description = interface.get("short_description")
    if not isinstance(display_name, str) or not display_name.strip():
        issues.append("interface.display_name 必须是非空字符串")
    elif len(display_name.strip()) > 80:
        issues.append("interface.display_name 超过 80 个字符")
    if not isinstance(short_description, str) or not short_description.strip():
        issues.append("interface.short_description 必须是非空字符串")
    else:
        short = short_description.strip()
        if "\n" in short or "\r" in short:
            issues.append("interface.short_description 必须为单行")
        if len(short) > 240:
            issues.append("interface.short_description 超过 240 个字符")
    brand_color = interface.get("brand_color")
    if brand_color is not None and (not isinstance(brand_color, str) or not HEX_RE.fullmatch(brand_color.strip())):
        issues.append("interface.brand_color 必须是六位十六进制颜色，例如 #1ABCFE")
    default_prompt = interface.get("default_prompt")
    if default_prompt is not None:
        if not isinstance(default_prompt, str) or not default_prompt.strip():
            issues.append("interface.default_prompt 必须是非空字符串")
        else:
            prompt = default_prompt.strip()
            if "\n" in prompt or "\r" in prompt:
                issues.append("interface.default_prompt 必须为单行")
            if len(prompt) > 512:
                issues.append("interface.default_prompt 超过 512 个字符")
    for field in ("icon_small", "icon_large"):
        value = interface.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            issues.append(f"interface.{field} 必须是非空相对路径")
            continue
        ok, target = path_inside(root, value.strip())
        if not ok:
            issues.append(f"interface.{field} 必须以 ./ 开头且位于 Skill 内部：{value}")
        elif not target.is_file():
            issues.append(f"interface.{field} 指向的文件不存在：{value}")
        elif target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            issues.append(f"interface.{field} 图像格式不支持：{target.suffix}")
        elif target.suffix.lower() == ".svg":
            issues.extend(f"interface.{field}：{msg}" for msg in validate_svg(target))
    policy = data.get("policy")
    if policy is not None:
        if not isinstance(policy, dict):
            issues.append("policy 必须是映射")
        else:
            unknown = sorted(set(policy) - {"products", "allow_implicit_invocation"})
            if unknown:
                issues.append("policy 含不支持字段：" + ",".join(unknown))
            implicit = policy.get("allow_implicit_invocation")
            if implicit is not None and not isinstance(implicit, bool):
                issues.append("policy.allow_implicit_invocation 必须是布尔值")
            products = policy.get("products")
            if products is not None:
                if not isinstance(products, list) or not products:
                    issues.append("policy.products 必须是非空列表")
                else:
                    invalid = [item for item in products if item not in {"CHAT", "CODEX"}]
                    if invalid:
                        issues.append("policy.products 只能包含 CHAT、CODEX")
    dependencies = data.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, dict):
            issues.append("dependencies 必须是映射")
        elif set(dependencies) - {"tools"}:
            issues.append("dependencies 目前只能包含 tools")
    return data, issues, warnings


def validate_references(root: Path, skill_text: str) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    refs = sorted((root / "references").glob("*.md")) if (root / "references").is_dir() else []
    names = [path.name for path in refs]
    for prefix in REQUIRED_REFERENCES:
        matches = [name for name in names if name.startswith(prefix)]
        if len(matches) != 1:
            issues.append(f"参考文件前缀 {prefix} 应恰好存在 1 个，实际 {len(matches)} 个")
    referenced_paths = sorted(set(match.group("path") for match in TEXT_REFERENCE_RE.finditer(skill_text)))
    for rel in referenced_paths:
        if not (root / rel).exists():
            issues.append(f"SKILL.md 引用不存在：{rel}")
    for rel in sorted(REQUIRED_SCRIPTS):
        if not (root / rel).is_file():
            issues.append(f"缺少必需脚本：{rel}")
    return issues, warnings


def validate_root(root: Path, *, run_self_test: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    if not root.is_dir():
        return {"gate": "FAIL", "issues": ["Skill 根目录不存在"], "warnings": []}
    if root.name.startswith("."):
        issues.append("Skill 目录名不得以 . 开头")

    for rel in sorted(REQUIRED_ROOT_ENTRIES):
        if not (root / rel).exists():
            issues.append(f"缺少 {rel}")

    for name in sorted(REQUIRED_ATOMIC_SKILLS):
        skill_dir = root / "skills" / name
        skill_file = skill_dir / "SKILL.md"
        agent_file = skill_dir / "agents" / "openai.yaml"
        if not skill_file.is_file() or not agent_file.is_file():
            issues.append(f"缺少原子Skill结构：{name}")
            continue
        try:
            atomic_front, atomic_body = parse_frontmatter(safe_text(skill_file))
            if atomic_front.get("name") != name:
                issues.append(f"原子Skill名称不一致：{name}")
            if not atomic_front.get("description") or not atomic_body.strip():
                issues.append(f"原子Skill缺少描述或正文：{name}")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            issues.append(f"原子Skill无效 {name}：{exc}")
        atomic_metadata, atomic_meta_issues, _ = validate_openai_yaml(skill_dir)
        issues.extend(f"原子Skill {name}：{msg}" for msg in atomic_meta_issues)
        if atomic_metadata.get("policy", {}).get("allow_implicit_invocation") is not False:
            issues.append(f"原子Skill {name} 必须关闭隐式调用，由手动选择的顶层路由懒加载")

    skill_path = root / "SKILL.md"
    skill_text = ""
    front: dict[str, str] = {}
    body = ""
    if not skill_path.is_file():
        issues.append("缺少 SKILL.md")
    else:
        try:
            skill_text = safe_text(skill_path)
            front, body = parse_frontmatter(skill_text)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            issues.append(str(exc))
        name = front.get("name", "").strip()
        description = front.get("description", "").strip()
        if not name:
            issues.append("SKILL.md 前置区缺少 name")
        elif not SAFE_SKILL_NAME_RE.fullmatch(name):
            issues.append("Skill name 必须以 ASCII 字母或数字开头，且仅含字母、数字、_、-")
        elif len(name) > 64:
            issues.append("Skill name 超过 64 个字符")
        if not description:
            issues.append("SKILL.md 前置区缺少 description")
        elif len(description) > 1024:
            issues.append("Skill description 超过 1024 个字符")
        if not body.strip():
            issues.append("SKILL.md 指令正文为空")
        details.update({"skill_name": name, "description_length": len(description), "skill_body_chars": len(body)})
        if name and root.name != name:
            warnings.append(f"目录名 {root.name} 与 Skill name {name} 不一致")

    version_path = root / "VERSION"
    version = ""
    if not version_path.is_file():
        issues.append("缺少 VERSION")
    else:
        try:
            version = safe_text(version_path).strip()
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(f"VERSION 无法读取：{exc}")
        if version and not SEMVER_RE.fullmatch(version):
            issues.append("VERSION 不是有效语义版本")
        if version and skill_text and f"版本：{version}" not in skill_text:
            issues.append("SKILL.md 正文版本与 VERSION 不一致")
        readme = root / "README_安装与使用.md"
        if version and readme.is_file():
            try:
                if f"版本：{version}" not in safe_text(readme):
                    issues.append("README_安装与使用.md 版本与 VERSION 不一致")
            except (OSError, UnicodeDecodeError) as exc:
                issues.append(f"README_安装与使用.md 无法读取：{exc}")
    details["version"] = version

    metadata, metadata_issues, metadata_warnings = validate_openai_yaml(root)
    issues.extend(metadata_issues); warnings.extend(metadata_warnings)
    details["agent_metadata"] = metadata
    if metadata.get("policy", {}).get("allow_implicit_invocation") is not False:
        issues.append("第三组顶层桌面重建路由必须关闭隐式调用，只允许手动选择")

    ref_issues, ref_warnings = validate_references(root, skill_text)
    issues.extend(ref_issues); warnings.extend(ref_warnings)

    py_files: list[Path] = []
    cache_entries: list[str] = []
    secret_candidates: list[str] = []
    symlinks: list[str] = []
    forbidden_files: list[str] = []
    file_count = 0
    total_size = 0
    max_depth = 0
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        max_depth = max(max_depth, len(PurePosixPath(rel).parts))
        if path.is_symlink():
            symlinks.append(rel)
            continue
        if path.name in IGNORED_CACHE_NAMES or any(part in IGNORED_CACHE_NAMES for part in path.parts):
            cache_entries.append(rel)
        if path.is_file():
            file_count += 1
            total_size += path.stat().st_size
            if path.suffix.lower() == ".py":
                py_files.append(path)
            if path.name in FORBIDDEN_PACKAGED_NAMES or path.suffix.lower() in {".pyc", ".pyo", ".tmp", ".bak", ".swp"}:
                forbidden_files.append(rel)
            if any(pattern.search(rel) for pattern in SECRET_FILE_PATTERNS):
                secret_candidates.append(rel)
    if symlinks:
        issues.extend(f"Skill 不应打包符号链接：{rel}" for rel in symlinks)
    if cache_entries:
        issues.append("Skill 含缓存目录或文件：" + ";".join(cache_entries[:30]))
    if forbidden_files:
        issues.append("Skill 含不应发布的临时/系统文件：" + ";".join(forbidden_files[:30]))
    if secret_candidates:
        issues.append("Skill 含疑似凭据或密钥文件：" + ";".join(secret_candidates[:30]))
    if file_count > 5000:
        issues.append("Skill 文件数超过 5000")
    if total_size > 512 * 1024 * 1024:
        issues.append("Skill 解压大小超过 512 MiB")
    if max_depth > 20:
        issues.append("Skill 路径深度超过 20 层")

    compile_errors: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="skill-compile-") as temp_dir:
        temp = Path(temp_dir)
        for index, path in enumerate(py_files):
            try:
                py_compile.compile(str(path), cfile=str(temp / f"{index}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                compile_errors.append({"file": path.relative_to(root).as_posix(), "error": str(exc)})
    if compile_errors:
        issues.append(f"{len(compile_errors)} 个 Python 脚本语法失败")

    self_test_result: dict[str, Any] | None = None
    if run_self_test and not compile_errors:
        self_script = root / "scripts" / "self_test.py"
        if not self_script.is_file():
            issues.append("要求自测但缺少 scripts/self_test.py")
        else:
            with tempfile.TemporaryDirectory(prefix="skill-selftest-result-") as temp_dir:
                output = Path(temp_dir) / "self-test.json"
                env = dict(os.environ)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                completed = subprocess.run(
                    [sys.executable, str(self_script), "--skill-root", str(root), "--json", str(output)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    check=False,
                    timeout=300,
                    env=env,
                )
                try:
                    self_test_result = json.loads(output.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError) as exc:
                    self_test_result = {
                        "gate": "FAIL", "error": f"自测未生成有效 JSON：{exc}",
                        "exit_code": completed.returncode,
                    }
                self_test_result["exit_code"] = completed.returncode
                if completed.stderr.strip():
                    self_test_result["stderr"] = completed.stderr.strip()[-4000:]
                if self_test_result.get("gate") != "PASS" or completed.returncode != 0:
                    issues.append("Skill 回归自测失败")

    details.update({
        "file_count": file_count,
        "total_size_bytes": total_size,
        "max_path_depth": max_depth,
        "python_script_count": len(py_files),
        "python_compile_errors": compile_errors,
        "tree_sha256": sha256_path(root),
        "self_test": self_test_result,
        "atomic_skill_count": len(REQUIRED_ATOMIC_SKILLS),
    })
    gate = "PASS" if not issues else "FAIL"
    return {"gate": gate, **details, "issues": issues, "warnings": sorted(set(warnings))}


def normalized_archive_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def inspect_zip(zip_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    if zip_path.stat().st_size > 100 * 1024 * 1024:
        issues.append("ZIP 压缩大小超过 100 MiB")
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if not infos:
            issues.append("ZIP 为空")
        if len(infos) > 5000:
            issues.append("ZIP 条目超过 5000")
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > 512 * 1024 * 1024:
            issues.append("ZIP 解压大小超过 512 MiB")
        seen: dict[str, str] = {}
        top_levels: set[str] = set()
        for info in infos:
            name = info.filename
            if not name:
                issues.append("ZIP 含空路径条目"); continue
            if name != name.strip():
                issues.append(f"ZIP 路径首尾有空白：{name}")
            if "\\" in name:
                issues.append(f"ZIP 路径使用反斜杠：{name}")
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                issues.append(f"ZIP 含不安全路径：{name}")
            if any(part == "" for part in name.split("/")) and not name.endswith("/"):
                issues.append(f"ZIP 路径含空段：{name}")
            if len(pure.parts) > 20:
                issues.append(f"ZIP 路径超过 20 层：{name}")
            if len(name) > 1024:
                issues.append(f"ZIP 路径过长：{name[:120]}…")
            if pure.parts:
                top_levels.add(pure.parts[0])
            key = normalized_archive_key(name.rstrip("/"))
            previous = seen.get(key)
            if previous is not None and previous != name.rstrip("/"):
                issues.append(f"ZIP 路径大小写/Unicode 归一化冲突：{previous} / {name}")
            seen[key] = name.rstrip("/")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                issues.append(f"ZIP 含符号链接：{name}")
            if info.flag_bits & 0x1:
                issues.append(f"ZIP 条目被加密：{name}")
            if info.file_size > 100 * 1024 * 1024:
                issues.append(f"ZIP 单文件超过 100 MiB：{name}")
        if len(top_levels) != 1:
            issues.append("ZIP 必须只有一个顶层目录")
        top_level = next(iter(top_levels), "")
        return {
            "issues": issues,
            "entry_count": len(infos),
            "compressed_size_bytes": zip_path.stat().st_size,
            "uncompressed_size_bytes": total_uncompressed,
            "top_level_entries": sorted(top_levels),
            "top_level": top_level,
            "sha256": sha256_file(zip_path),
        }


def extract_zip(zip_path: Path, destination: Path, zip_info: dict[str, Any]) -> Path:
    if zip_info.get("issues"):
        return destination
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)
    return destination / str(zip_info["top_level"])


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 standalone Skill 目录或单顶层 ZIP")
    parser.add_argument("path", help="Skill 目录或 ZIP")
    parser.add_argument("--json", dest="json_path", default=None, help="写入机器可读 JSON")
    parser.add_argument("--self-test", action="store_true", help="额外运行确定性回归自测")
    parser.add_argument("--strict", action="store_true", help="将警告也视为失败")
    args = parser.parse_args()

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        result = {"gate": "FAIL", "issues": [f"路径不存在：{source}"], "warnings": []}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.json_path:
            write_json(Path(args.json_path).expanduser().resolve(), result)
        return 2

    temp_manager: tempfile.TemporaryDirectory[str] | None = None
    archive_info: dict[str, Any] = {}
    try:
        if source.is_file() and source.suffix.lower() == ".zip":
            try:
                archive_info = inspect_zip(source)
            except (OSError, zipfile.BadZipFile, NotImplementedError) as exc:
                archive_info = {"issues": [f"ZIP 无法读取：{exc}"]}
            if archive_info.get("issues"):
                result = {"gate": "FAIL", "source": str(source), "archive": archive_info, "issues": archive_info["issues"], "warnings": []}
            else:
                temp_manager = tempfile.TemporaryDirectory(prefix="skill-zip-validate-")
                root = extract_zip(source, Path(temp_manager.name), archive_info)
                result = {"source": str(source), "archive": archive_info, **validate_root(root, run_self_test=args.self_test)}
        elif source.is_dir():
            result = {"source": str(source), **validate_root(source, run_self_test=args.self_test)}
        else:
            result = {"gate": "FAIL", "source": str(source), "issues": ["只支持目录或 .zip"], "warnings": []}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {"gate": "FAIL", "source": str(source), "issues": [f"校验异常：{exc}"], "warnings": []}
    finally:
        if temp_manager is not None:
            temp_manager.cleanup()

    if args.strict and result.get("warnings"):
        result["gate"] = "FAIL"
        result.setdefault("issues", []).append("strict 模式下存在警告")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_path:
        write_json(Path(args.json_path).expanduser().resolve(), result)
    return 0 if result.get("gate") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
