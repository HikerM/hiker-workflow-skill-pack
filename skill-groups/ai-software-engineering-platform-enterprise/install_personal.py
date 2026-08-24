from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN_NAMES = ["ai-engineering-core", "ai-engineering-web", "ai-engineering-unity", "ai-engineering-workspace", "ai-engineering-quality"]
GLOBAL_TEMPLATE = ROOT / "templates" / "GLOBAL_AGENTS_AI_ENGINEERING.md"
BLOCK_START = "<!-- ai-engineering-global-governance start -->"
BLOCK_END = "<!-- ai-engineering-global-governance end -->"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store")


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def load(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(item for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"):
        digest.update(file.relative_to(path).as_posix().encode("utf-8")); digest.update(b"\0"); digest.update(file.read_bytes())
    return digest.hexdigest()


def plugin_display(name: str) -> str:
    manifest = load(ROOT / "plugins" / name / ".codex-plugin" / "plugin.json")
    return str(manifest.get("interface", {}).get("displayName") or "未命名工程插件")


def seed_plugin_cache(dest: Path, marketplace_name: str, installed: list[dict], backup: Path) -> list[dict]:
    cache_root = dest / "cache" / marketplace_name
    seeded = []
    for item in installed:
        name = item["id"]; src = Path(item["path"])
        manifest = load(src / ".codex-plugin" / "plugin.json"); version = str(manifest.get("version") or "").strip()
        if not version: raise RuntimeError(f"{name}: plugin version missing")
        parent = cache_root / name; target = parent / version; tmp = parent / (version + ".installing")
        parent.mkdir(parents=True, exist_ok=True); shutil.rmtree(tmp, ignore_errors=True)
        if target.exists():
            cached_backup = backup / "cache" / name / version; cached_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, cached_backup, dirs_exist_ok=True); shutil.rmtree(target)
        shutil.copytree(src, tmp, ignore=COPY_IGNORE); os.replace(tmp, target)
        seeded.append({"plugin": plugin_display(name), "version": version, "path": str(target)})
    return seeded


def prune_plugin_cache(dest: Path, marketplace_name: str, installed: list[dict], backup: Path, retention: int) -> list[dict]:
    """Retain current plus the newest previous cache versions; move older entries into the install backup."""
    cache_root = (dest / "cache" / marketplace_name).resolve(); moved = []
    current_versions = {item["id"]: str(load(Path(item["path"]) / ".codex-plugin" / "plugin.json").get("version") or "") for item in installed}
    for name in PLUGIN_NAMES:
        parent = (cache_root / name).resolve()
        if parent.parent != cache_root or not parent.is_dir(): continue
        versions = [p for p in parent.iterdir() if p.is_dir() and not p.name.endswith(".installing")]
        current = current_versions.get(name)
        def version_key(path: Path) -> tuple:
            numbers = tuple(int(value) for value in re.findall(r"\d+", path.name)[:8])
            return (path.name == current, numbers + (0,) * (8 - len(numbers)), path.name)
        versions.sort(key=version_key, reverse=True)
        for stale in versions[max(1, retention):]:
            resolved = stale.resolve()
            if resolved.parent != parent: raise RuntimeError(f"unsafe cache prune target: {resolved}")
            target = backup / "cache-pruned" / name / stale.name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved), str(target)); moved.append({"plugin": plugin_display(name), "version": stale.name, "backup": str(target)})
    return moved


def managed_block() -> str:
    text = GLOBAL_TEMPLATE.read_text(encoding="utf-8").strip()
    if text.count(BLOCK_START) != 1 or text.count(BLOCK_END) != 1 or text.index(BLOCK_START) > text.index(BLOCK_END):
        raise RuntimeError("invalid global AGENTS template markers")
    return text


def merge_global_agents(home: Path, stamp: str) -> dict:
    target = home / ".codex" / "AGENTS.md"; block = managed_block(); original = target.read_text(encoding="utf-8") if target.exists() else ""
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), re.S)
    matches = pattern.findall(original)
    if len(matches) > 1: raise RuntimeError("multiple managed governance blocks found; resolve duplicates before installation")
    if matches: updated = pattern.sub(lambda _: block, original, count=1)
    else: updated = original.rstrip() + ("\n\n" if original.strip() else "") + block + "\n"
    if updated == original: return {"path": str(target), "status": "unchanged", "backup": None}
    backup_path = None
    if target.exists():
        backup_path = home / ".codex" / "agents-backup" / stamp / "AGENTS.md"; backup_path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, backup_path)
    atomic_text(target, updated)
    return {"path": str(target), "status": "updated" if original else "created", "backup": str(backup_path) if backup_path else None}


def find_codex_cli(home: Path, explicit: str | None) -> Path | None:
    candidates = []
    if explicit: candidates.append(Path(explicit).expanduser())
    if os.environ.get("CODEX_CLI_PATH"): candidates.append(Path(os.environ["CODEX_CLI_PATH"]).expanduser())
    config = home / ".codex" / "config.toml"
    if config.exists():
        match = re.search(r"^\s*CODEX_CLI_PATH\s*=\s*['\"]([^'\"]+)['\"]", config.read_text(encoding="utf-8"), re.M)
        if match: candidates.append(Path(match.group(1)))
    found = shutil.which("codex")
    if found: candidates.append(Path(found))
    if os.name == "nt": candidates += sorted((home / "AppData" / "Local" / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"), reverse=True)
    for candidate in candidates:
        if not candidate.is_file(): continue
        try:
            probe = subprocess.run([str(candidate.resolve()), "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if probe.returncode == 0: return candidate.resolve()
        except (OSError, subprocess.SubprocessError): continue
    return None


def enable_plugins_in_config(home: Path, marketplace_name: str, stamp: str) -> dict:
    target = home / ".codex" / "config.toml"
    original = target.read_text(encoding="utf-8") if target.exists() else ""
    updated = original
    enabled = []
    for name in PLUGIN_NAMES:
        plugin_id = f'{name}@{marketplace_name}'
        header = f'[plugins."{plugin_id}"]'
        section = re.compile(rf'(?ms)^{re.escape(header)}[ \t]*$.*?(?=^\[|\Z)')
        match = section.search(updated)
        if match:
            body = match.group(0)
            if re.search(r'(?m)^[ \t]*enabled[ \t]*=[ \t]*(?:true|false)[ \t]*$', body):
                body = re.sub(r'(?m)^[ \t]*enabled[ \t]*=[ \t]*(?:true|false)[ \t]*$', 'enabled = true', body, count=1)
            else:
                body = body.rstrip() + "\nenabled = true\n\n"
            updated = updated[:match.start()] + body + updated[match.end():]
        else:
            updated = updated.rstrip() + ("\n\n" if updated.strip() else "") + header + "\nenabled = true\n"
        enabled.append(plugin_display(name))
    backup_path = None
    if updated != original:
        if target.exists():
            backup_path = home / ".codex" / "config-backup" / stamp / "config.toml"
            backup_path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, backup_path)
        atomic_text(target, updated)
    return {"status": "updated" if updated != original else "unchanged", "path": str(target), "backup": str(backup_path) if backup_path else None, "enabled": enabled}


def activate_plugins(home: Path, marketplace_name: str, explicit_cli: str | None, skip: bool, stamp: str) -> dict:
    commands = [f"codex plugin add {name}@{marketplace_name} --json" for name in PLUGIN_NAMES]
    if skip: return {"status": "skipped", "cli": None, "results": [], "manual_commands": commands}
    config = enable_plugins_in_config(home, marketplace_name, stamp)
    if not explicit_cli:
        return {"status": "activated", "method": "desktop-config", "cli": None, "config": config, "results": [{"plugin": name, "ok": True, "returncode": None} for name in config["enabled"]], "failed": [], "manual_commands": []}
    cli = find_codex_cli(home, explicit_cli)
    supports_plugin_add = False
    if cli:
        try:
            probe = subprocess.run([str(cli), "plugin", "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            supports_plugin_add = probe.returncode == 0 and bool(re.search(r"(?m)^\s+add\s", probe.stdout))
        except (OSError, subprocess.SubprocessError):
            supports_plugin_add = False
    if not supports_plugin_add:
        return {"status": "activated", "method": "desktop-config", "cli": str(cli) if cli else None, "config": config, "results": [{"plugin": name, "ok": True, "returncode": None} for name in config["enabled"]], "failed": [], "manual_commands": []}
    results = []; failed = []
    for name in PLUGIN_NAMES:
        plugin_id = f"{name}@{marketplace_name}"
        try:
            completed = subprocess.run([str(cli), "plugin", "add", plugin_id, "--json"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            item = {"plugin": plugin_display(name), "ok": completed.returncode == 0, "returncode": completed.returncode}
            if completed.returncode != 0: item["error"] = (completed.stderr or completed.stdout).strip()[:1000]; failed.append(plugin_display(name))
        except OSError as exc:
            item = {"plugin": plugin_display(name), "ok": False, "returncode": None, "error": str(exc)}; failed.append(plugin_display(name))
        results.append(item)
    return {"status": "activated" if not failed else "partial-failure", "method": "cli", "cli": str(cli), "results": results, "failed": failed, "manual_commands": commands if failed else []}


def verify_installation(home: Path, marketplace_name: str) -> dict:
    dest = home / ".codex" / "plugins"; mismatches = []; plugins = []
    config_text = (home / ".codex" / "config.toml").read_text(encoding="utf-8", errors="ignore") if (home / ".codex" / "config.toml").exists() else ""
    for name in PLUGIN_NAMES:
        source = ROOT / "plugins" / name; installed = dest / name
        manifest = load(source / ".codex-plugin" / "plugin.json"); version = str(manifest.get("version") or "")
        cached = dest / "cache" / marketplace_name / name / version
        source_hash = tree_digest(source) if source.is_dir() else ""
        installed_hash = tree_digest(installed) if installed.is_dir() else ""
        cache_hash = tree_digest(cached) if cached.is_dir() else ""
        enabled = bool(re.search(rf'(?ms)^\[plugins\."{re.escape(name + "@" + marketplace_name)}"\]\s*$.*?^enabled\s*=\s*true\s*$', config_text))
        item = {"plugin": plugin_display(name), "version": version, "source_hash": source_hash, "installed_hash": installed_hash, "cache_hash": cache_hash, "enabled": enabled, "consistent": bool(source_hash and source_hash == installed_hash == cache_hash and enabled)}
        if not item["consistent"]: mismatches.append(item["plugin"])
        plugins.append(item)
    agents = home / ".codex" / "AGENTS.md"
    agents_ok = agents.is_file() and managed_block() in agents.read_text(encoding="utf-8", errors="ignore")
    if not agents_ok: mismatches.append("全局自动应用规则")
    return {"ok": not mismatches, "marketplace": marketplace_name, "plugins": plugins, "global_rules_consistent": agents_ok, "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser(description="安装AI软件工程插件，并默认安全合并Codex全局自动应用规则。")
    parser.add_argument("--no-merge-global-agents", action="store_true", help="只安装插件，不修改 ~/.codex/AGENTS.md")
    parser.add_argument("--no-activate-plugins", action="store_true", help="只注册Marketplace，不调用Codex CLI安装启用插件")
    parser.add_argument("--codex-cli", help="仅为旧版兼容显式指定codex或codex.exe；桌面端安装默认不需要")
    parser.add_argument("--cache-retention", type=int, default=1, help="每个插件保留的缓存版本数（默认只保留当前版；旧版进入可恢复备份）")
    args = parser.parse_args()
    if args.cache_retention < 1: parser.error("--cache-retention must be at least 1")
    home = Path.home(); dest = home / ".codex" / "plugins"; market = home / ".agents" / "plugins" / "marketplace.json"; stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); backup = home / ".codex" / "plugins-backup" / stamp
    dest.mkdir(parents=True, exist_ok=True); installed = []
    for name in PLUGIN_NAMES:
        src = ROOT / "plugins" / name; target = dest / name
        if target.exists(): backup.mkdir(parents=True, exist_ok=True); shutil.copytree(target, backup / name, dirs_exist_ok=True); shutil.rmtree(target)
        tmp = dest / (name + ".installing"); shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(src, tmp, ignore=COPY_IGNORE); os.replace(tmp, target); installed.append({"id": name, "name": plugin_display(name), "path": str(target)})
    current = load(market); plugins = [item for item in current.get("plugins", []) if item.get("name") not in PLUGIN_NAMES]
    plugins += [{"name": item["id"], "source": {"source": "local", "path": f"./.codex/plugins/{item['id']}"}, "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"} for item in installed]
    merged = {"name": current.get("name", "personal-ai-engineering-marketplace"), "interface": current.get("interface", {"displayName": "个人插件"}), "plugins": plugins}
    marketplace_backup = None
    if market.exists(): marketplace_backup = market.with_suffix(f".json.{stamp}.bak"); marketplace_backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(market, marketplace_backup)
    atomic_json(market, merged)
    cache = seed_plugin_cache(dest, str(merged["name"]), installed, backup)
    cache_pruned = prune_plugin_cache(dest, str(merged["name"]), installed, backup, args.cache_retention)
    global_agents = {"status": "skipped", "path": str(home / ".codex" / "AGENTS.md"), "backup": None} if args.no_merge_global_agents else merge_global_agents(home, stamp)
    activation = activate_plugins(home, str(merged["name"]), args.codex_cli, args.no_activate_plugins, stamp)
    verification = verify_installation(home, str(merged["name"])) if not args.no_activate_plugins and not args.no_merge_global_agents else {"ok": True, "skipped": True}
    runtime_activation = {
        "status": "NOT_VERIFIED",
        "reason": "文件、缓存与启用配置一致不等于运行中的桌面进程已刷新插件注册表",
        "verification": "新建任务读取实际 SKILL.md 与 plugin.json 路径；若仍指向旧缓存，必须重启桌面端",
        "existing_task_policy": "旧任务不得继续写源码；先保存Checkpoint，再由使用当前完整版本的新任务接管",
        "mixed_version_execution": "FORBIDDEN",
    }
    install_state = {"schema_version": "1.1.0", "installed_at": stamp, "marketplace": str(merged["name"]), "plugins": [{"plugin": item["plugin"], "version": item["version"]} for item in cache], "cache_retention": args.cache_retention, "cache_pruned": cache_pruned, "verification": verification, "runtime_activation": runtime_activation, "new_task_required": True, "existing_tasks_must_handoff": True, "mixed_version_execution_forbidden": True}
    atomic_json(home / ".codex" / "plugin-install-state.json", install_state)
    ok = activation["status"] != "partial-failure" and verification.get("ok", False)
    next_step = "先让旧任务保存Checkpoint并停止写入，再新建任务读取实际插件路径复验；若仍指向旧缓存，关闭并重启桌面端后再新建任务。" if activation["status"] == "activated" else "按manual_commands安装启用插件；旧任务保存Checkpoint后停止写入，再由新任务接管。"
    print(json.dumps({"ok": ok, "installed": installed, "cache": cache, "cache_pruned": cache_pruned, "marketplace": str(market), "marketplace_backup": str(marketplace_backup) if marketplace_backup else None, "plugin_backup": str(backup) if backup.exists() else None, "global_agents": global_agents, "plugin_activation": activation, "verification": verification, "runtime_activation": runtime_activation, "install_state": str(home / ".codex" / "plugin-install-state.json"), "next_step": next_step}, ensure_ascii=False, indent=2)); return 0 if ok else 2


if __name__ == "__main__": raise SystemExit(main())
