#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "Use When",
    "Do Not Use When",
    "Goal",
    "Required Inputs",
    "Required Process",
    "Evidence Rules",
    "Output Format",
    "Hard Rules",
    "Failure Modes",
    "Example User Inputs",
    "Example Final Output",
]

PACKAGE_FILES = [
    "README.md",
    "VERSION",
    "CHANGELOG.md",
    "INSTALL.ps1",
    "UNINSTALL.ps1",
    "VALIDATE.ps1",
]

DOC_FILES = [
    "docs/INSTALLATION.md",
    "docs/USAGE.md",
    "docs/SKILL_INDEX.md",
    "docs/SAFETY_RULES.md",
]

EXAMPLE_FILES = [
    "examples/codex-thread-review.example.md",
    "examples/project-phase-review.example.md",
    "examples/nodets-execution-pipeline.example.md",
]

DANGEROUS_TERMS = [
    "git reset --hard",
    "git push --force",
    "force push",
    "Remove-Item -Recurse",
    "rm -rf",
    "DROP DATABASE",
    "TRUNCATE TABLE",
]

NEGATIONS = [
    "do not",
    "don't",
    "never",
    "without explicit",
    "不要",
    "禁止",
    "不得",
    "不允许",
    "除非",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_frontmatter(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "missing opening frontmatter delimiter"
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return None, "missing closing frontmatter delimiter"
    data = {}
    for line in lines[1:end_index]:
        if not line.strip():
            continue
        if ":" not in line:
            return None, f"invalid frontmatter line: {line}"
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data, None


def has_section(text: str, section: str) -> bool:
    pattern = r"(?m)^##\s+" + re.escape(section) + r"\s*$"
    return re.search(pattern, text) is not None


def validate_skill(skill_dir: Path):
    errors = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir.name}: missing SKILL.md"]
    text = read_text(skill_md)
    fm, err = parse_frontmatter(text)
    if err:
        errors.append(f"{skill_dir.name}: {err}")
        return errors
    extra_keys = sorted(set(fm.keys()) - {"name", "description"})
    if extra_keys:
        errors.append(f"{skill_dir.name}: frontmatter has unsupported keys: {', '.join(extra_keys)}")
    name = fm.get("name", "")
    desc = fm.get("description", "")
    if name != skill_dir.name:
        errors.append(f"{skill_dir.name}: frontmatter name must equal folder name, got {name!r}")
    if not desc.strip():
        errors.append(f"{skill_dir.name}: description is empty")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", name):
        errors.append(f"{skill_dir.name}: name must be lowercase hyphen-case and under 64 chars")
    for section in REQUIRED_SECTIONS:
        if not has_section(text, section):
            errors.append(f"{skill_dir.name}: missing section ## {section}")
    agent_file = skill_dir / "agents" / "openai.yaml"
    if not agent_file.is_file():
        errors.append(f"{skill_dir.name}: missing agents/openai.yaml")
    else:
        agent_text = read_text(agent_file)
        expected = "false"
        if f"allow_implicit_invocation: {expected}" not in agent_text:
            errors.append(f"{skill_dir.name}: fast-routing policy requires allow_implicit_invocation: {expected}")
    return errors


def validate_agents(root: Path):
    agents = root / "AGENTS.md"
    if not agents.exists():
        return []
    errors = []
    for line_no, line in enumerate(read_text(agents).splitlines(), start=1):
        lowered = line.lower()
        for term in DANGEROUS_TERMS:
            if term.lower() in lowered:
                if not any(neg.lower() in lowered for neg in NEGATIONS):
                    errors.append(f"AGENTS.md:{line_no}: dangerous default command without negation: {term}")
    return errors


def validate_no_temp(root: Path):
    errors = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        parts = rel.parts
        if ".codex-output" in parts:
            errors.append(f"temp artifact not allowed: {rel}")
        if len(parts) >= 2 and parts[0] == "outputs" and parts[1] == "tmp":
            errors.append(f"outputs/tmp artifact not allowed: {rel}")
        if path.is_file() and path.name.lower().endswith((".tmp", ".temp", ".bak", "~")):
            errors.append(f"temporary file not allowed: {rel}")
    return errors


def validate_package_files(root: Path):
    errors = []
    for rel in PACKAGE_FILES + DOC_FILES + EXAMPLE_FILES:
        if not (root / rel).exists():
            errors.append(f"missing package file: {rel}")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = []
    package_mode = any((root / rel).exists() for rel in PACKAGE_FILES)

    skills_root = root / ".agents" / "skills"
    if not skills_root.exists():
        errors.append("missing .agents/skills")
    else:
        skill_dirs = sorted([p for p in skills_root.iterdir() if p.is_dir()])
        if not package_mode:
            marker = root / ".agents" / "hiker-workflow-pack.installed.json"
            try:
                managed = set(json.loads(read_text(marker)).get("skills", [])) if marker.is_file() else set()
            except (OSError, json.JSONDecodeError):
                managed = set()
            if managed:
                skill_dirs = [p for p in skill_dirs if p.name in managed]
        if not skill_dirs:
            errors.append("no skill directories found")
        names = []
        for skill_dir in skill_dirs:
            errors.extend(validate_skill(skill_dir))
            names.append(skill_dir.name)
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            errors.append(f"duplicate skill name: {name}")

    if package_mode:
        errors.extend(validate_package_files(root))

    if package_mode:
        errors.extend(validate_agents(root))
    # 仓库源码模式检查整个包；安装目标模式只检查本组skills，避免递归用户主目录、缓存和其他项目。
    errors.extend(validate_no_temp(root if package_mode else skills_root))

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("VALIDATION PASSED")
    print(f"Root: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
