from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN_NAMES = sorted(p.name for p in (ROOT / "plugins").iterdir() if p.is_dir())
GLOBAL_TEMPLATE = ROOT / "templates" / "GLOBAL_AGENTS_AI_ENGINEERING.md"
BLOCK_START = "<!-- ai-engineering-global-governance start -->"
BLOCK_END = "<!-- ai-engineering-global-governance end -->"


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


def activate_plugins(home: Path, marketplace_name: str, explicit_cli: str | None, skip: bool) -> dict:
    commands = [f"codex plugin add {name}@{marketplace_name} --json" for name in PLUGIN_NAMES]
    if skip: return {"status": "skipped", "cli": None, "results": [], "manual_commands": commands}
    cli = find_codex_cli(home, explicit_cli)
    if not cli: return {"status": "manual-required", "cli": None, "results": [], "manual_commands": commands}
    results = []; failed = []
    for name in PLUGIN_NAMES:
        plugin_id = f"{name}@{marketplace_name}"
        try:
            completed = subprocess.run([str(cli), "plugin", "add", plugin_id, "--json"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            item = {"plugin_id": plugin_id, "ok": completed.returncode == 0, "returncode": completed.returncode}
            if completed.returncode != 0: item["error"] = (completed.stderr or completed.stdout).strip()[:1000]; failed.append(plugin_id)
        except OSError as exc:
            item = {"plugin_id": plugin_id, "ok": False, "returncode": None, "error": str(exc)}; failed.append(plugin_id)
        results.append(item)
    return {"status": "activated" if not failed else "partial-failure", "cli": str(cli), "results": results, "failed": failed, "manual_commands": commands if failed else []}


def main() -> int:
    parser = argparse.ArgumentParser(description="安装AI软件工程插件，并默认安全合并Codex全局自动应用规则。")
    parser.add_argument("--no-merge-global-agents", action="store_true", help="只安装插件，不修改 ~/.codex/AGENTS.md")
    parser.add_argument("--no-activate-plugins", action="store_true", help="只注册Marketplace，不调用Codex CLI安装启用插件")
    parser.add_argument("--codex-cli", help="显式指定codex或codex.exe路径")
    args = parser.parse_args()
    home = Path.home(); dest = home / ".codex" / "plugins"; market = home / ".agents" / "plugins" / "marketplace.json"; stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); backup = home / ".codex" / "plugins-backup" / stamp
    dest.mkdir(parents=True, exist_ok=True); installed = []
    for name in PLUGIN_NAMES:
        src = ROOT / "plugins" / name; target = dest / name
        if target.exists(): backup.mkdir(parents=True, exist_ok=True); shutil.copytree(target, backup / name, dirs_exist_ok=True); shutil.rmtree(target)
        tmp = dest / (name + ".installing"); shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(src, tmp); os.replace(tmp, target); installed.append({"name": name, "path": str(target)})
    current = load(market); plugins = [item for item in current.get("plugins", []) if item.get("name") not in PLUGIN_NAMES]
    plugins += [{"name": item["name"], "source": {"source": "local", "path": f"./.codex/plugins/{item['name']}"}, "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"} for item in installed]
    merged = {"name": current.get("name", "personal-ai-engineering-marketplace"), "interface": current.get("interface", {"displayName": "个人插件"}), "plugins": plugins}
    marketplace_backup = None
    if market.exists(): marketplace_backup = market.with_suffix(f".json.{stamp}.bak"); marketplace_backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(market, marketplace_backup)
    atomic_json(market, merged)
    global_agents = {"status": "skipped", "path": str(home / ".codex" / "AGENTS.md"), "backup": None} if args.no_merge_global_agents else merge_global_agents(home, stamp)
    activation = activate_plugins(home, str(merged["name"]), args.codex_cli, args.no_activate_plugins)
    ok = activation["status"] != "partial-failure"
    next_step = "重启ChatGPT/Codex桌面端并新建任务。" if activation["status"] == "activated" else "按manual_commands安装启用插件，再重启桌面端并新建任务。"
    print(json.dumps({"ok": ok, "installed": installed, "marketplace": str(market), "marketplace_backup": str(marketplace_backup) if marketplace_backup else None, "plugin_backup": str(backup) if backup.exists() else None, "global_agents": global_agents, "plugin_activation": activation, "next_step": next_step}, ensure_ascii=False, indent=2)); return 0 if ok else 2


if __name__ == "__main__": raise SystemExit(main())
