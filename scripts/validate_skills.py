#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FILES = (
    "README.md", "VERSION", "CHANGELOG.md", "AGENTS.md", "VALIDATE.ps1",
    "docs/INSTALLATION.md", "docs/USAGE.md", "docs/SKILL_INDEX.md",
    "docs/CAPABILITY_PACKS_ZH.md", "docs/SAFETY_RULES.md", "scripts/audit_public_content.py",
)
ALLOWED_PACKS = {"ai-software-engineering-platform-enterprise", "desktop-app-reconstruction-zh"}
REMOVED_PATHS = (".agents/skills", "INSTALL.ps1", "UNINSTALL.ps1", "examples", "docs/THREE_SKILL_GROUPS_ZH.md")
STALE_PUBLIC_TERMS = (
    "Hiker 工作流守护", "Hiker工作流守护", "hiker-" + "workflow-router",
    "第一组", "第二组", "第三组", "三组 Skill",
)
PUBLIC_DOCS = (
    "README.md", "docs/INSTALLATION.md", "docs/USAGE.md", "docs/SKILL_INDEX.md",
    "docs/CAPABILITY_PACKS_ZH.md", "skill-groups/README.md",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def repository_facts(root: Path) -> dict[str, object]:
    engineering = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    desktop = root / "skill-groups" / "desktop-app-reconstruction-zh"
    plugin_dirs = sorted(path for path in (engineering / "plugins").iterdir() if path.is_dir())
    versions: set[str] = set()
    engineering_skills = 0
    for plugin in plugin_dirs:
        manifest = json.loads(read_text(plugin / ".codex-plugin" / "plugin.json"))
        versions.add(str(manifest["version"]).split("+", 1)[0])
        engineering_skills += len(list((plugin / "skills").glob("*/SKILL.md")))
    if len(versions) != 1:
        raise ValueError(f"engineering plugin versions differ: {sorted(versions)}")
    desktop_skills = len(list(desktop.rglob("SKILL.md")))
    return {
        "repository": read_text(root / "VERSION").strip(),
        "engineering": next(iter(versions)),
        "plugins": len(plugin_dirs),
        "engineering_skills": engineering_skills,
        "desktop": read_text(desktop / "VERSION").strip(),
        "desktop_skills": desktop_skills,
        "total_skills": engineering_skills + desktop_skills,
    }


def validate_structure(root: Path) -> list[str]:
    errors = [f"missing required file: {name}" for name in REQUIRED_FILES if not (root / name).is_file()]
    packs_root = root / "skill-groups"
    actual = {path.name for path in packs_root.iterdir() if path.is_dir()} if packs_root.is_dir() else set()
    if actual != ALLOWED_PACKS:
        errors.append(f"skill-groups must contain exactly {sorted(ALLOWED_PACKS)}, got {sorted(actual)}")
    for name in REMOVED_PATHS:
        target = root / name
        if target.is_file() or (target.is_dir() and any(path.is_file() for path in target.rglob("*"))):
            errors.append(f"removed package residue exists: {name}")
    return errors


def validate_public_docs(root: Path, facts: dict[str, object]) -> list[str]:
    errors: list[str] = []
    metadata = (
        f"<!-- repository-facts: repo={facts['repository']}; engineering={facts['engineering']}; "
        f"plugins={facts['plugins']}; engineering-skills={facts['engineering_skills']}; "
        f"desktop={facts['desktop']}; desktop-skills={facts['desktop_skills']}; "
        f"total-skills={facts['total_skills']} -->"
    )
    required = {
        "README.md": (
            metadata, f"> 仓库版本：`{facts['repository']}`",
            f"> 当前规模：`2` 套能力包、共 `{facts['total_skills']}` 个 Skill",
            f"## 智能软件工程平台 {facts['engineering']}", f"## 桌面软件等价重建 {facts['desktop']}",
        ),
        "docs/SKILL_INDEX.md": (
            f"共 {facts['total_skills']} 个 Skill", f"智能软件工程平台（{facts['engineering_skills']} 个）",
            f"桌面软件等价重建（{facts['desktop_skills']} 个）",
        ),
        "skill-groups/README.md": (
            f"智能软件工程平台 {facts['engineering']}", f"桌面软件等价重建 {facts['desktop']}",
        ),
    }
    for name in PUBLIC_DOCS:
        path = root / name
        if not path.is_file():
            continue
        text = read_text(path)
        for term in STALE_PUBLIC_TERMS:
            if term in text:
                errors.append(f"{name}: stale removed-package or ordinal-group term: {term}")
    for name, tokens in required.items():
        text = read_text(root / name)
        for token in tokens:
            if token not in text:
                errors.append(f"{name}: missing or stale public fact: {token}")
    return errors


def validate_no_temp(root: Path) -> list[str]:
    errors: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".codex-output" in relative.parts:
            errors.append(f"temporary artifact not allowed: {relative}")
        if path.is_file() and path.name.lower().endswith((".tmp", ".temp", ".bak", "~")):
            errors.append(f"temporary file not allowed: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="验证双能力包仓库结构和公开文档事实")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = validate_structure(root)
    try:
        facts = repository_facts(root)
        errors.extend(validate_public_docs(root, facts))
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot derive repository facts: {exc}")
    errors.extend(validate_no_temp(root))
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
