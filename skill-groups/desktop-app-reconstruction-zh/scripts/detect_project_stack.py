#!/usr/bin/env python3
"""Read-only source project technology and version fingerprinting.

The detector inspects common manifests, lock files, build scripts, and CI
configuration.  It never executes project commands and never treats a clue as
proof of the target implementation choice.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

from lib_recon import unique, write_json

IGNORED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "Library",
    "Temp",
    "Obj",
    "Logs",
    "Build",
    "Builds",
    "bin",
    "obj",
    ".idea",
    ".vscode",
    ".gradle",
    ".venv",
    "venv",
    "__pycache__",
    "target",
    "dist",
    "out",
}

INTERESTING_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    ".nvmrc",
    ".node-version",
    "global.json",
    "Directory.Build.props",
    "Directory.Packages.props",
    "packages.lock.json",
    "ProjectVersion.txt",
    "manifest.json",
    "packages-lock.json",
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "rust-toolchain",
    "pyproject.toml",
    ".python-version",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "requirements.txt",
    "requirements.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradle.properties",
    "gradlew",
    "gradlew.bat",
    "go.mod",
    "go.sum",
    "CMakeLists.txt",
    "CMakePresets.json",
    "vcpkg.json",
    "conanfile.py",
    "conanfile.txt",
    "pubspec.yaml",
    ".fvmrc",
    "Package.swift",
    "Gemfile",
    "composer.json",
}

INTERESTING_SUFFIXES = {
    ".csproj",
    ".fsproj",
    ".vbproj",
    ".sln",
    ".pro",
    ".pri",
    ".xcodeproj",
    ".xcworkspace",
    ".uproject",
    ".uplugin",
    ".runtimeconfig.json",
    ".deps.json",
    ".gradle",
    ".kts",
}

LOCK_FILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "packages.lock.json",
    "packages-lock.json",
    "Cargo.lock",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "requirements.lock",
    "go.sum",
    "gradle.lockfile",
    "composer.lock",
    "Gemfile.lock",
}

BINARY_INDICATOR_PATTERNS = [
    re.compile(r"^UnityPlayer\.(?:dll|so|dylib)$", re.I),
    re.compile(r"^(?:resources\.)?app\.asar$", re.I),
    re.compile(r"^(?:electron|chrome_elf|libcef)\.(?:exe|dll|so|dylib)$", re.I),
    re.compile(r"^(?:Qt[56](?:Core|Gui|Widgets|Quick)|libQt[56].*)\.(?:dll|so|dylib)(?:\..*)?$", re.I),
    re.compile(r"^(?:coreclr|hostfxr|hostpolicy)\.(?:dll|so|dylib)$", re.I),
    re.compile(r"^python3?\d*\.(?:dll|so|dylib)(?:\..*)?$", re.I),
    re.compile(r"^(?:jvm|java)\.(?:dll|so|dylib|exe)(?:\..*)?$", re.I),
    re.compile(r"^(?:UnrealEditor|UE4Editor|UE5Editor)(?:-Win64-Shipping)?\.exe$", re.I),
]

def is_binary_indicator(name: str) -> bool:
    return any(pattern.match(name) for pattern in BINARY_INDICATOR_PATTERNS)


def read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > max_bytes:
        data = data[:max_bytes]
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def add_evidence(store: dict[str, list[dict[str, str]]], technology: str, path: Path, root: Path, kind: str, value: Any) -> None:
    store[technology].append(
        {
            "path": rel(path, root),
            "kind": kind,
            "value": str(value),
        }
    )


def json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(path))
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def collect_files(root: Path, max_depth: int, max_files: int) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    warnings: list[str] = []
    root_parts = len(root.parts)
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_parts
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".cache")]
        if depth >= max_depth:
            dirs[:] = []
        for name in names:
            path = current_path / name
            lower_name = name.lower()
            multi_suffix = lower_name.endswith((".runtimeconfig.json", ".deps.json"))
            if (
                name in INTERESTING_NAMES
                or path.suffix in INTERESTING_SUFFIXES
                or multi_suffix
                or name.startswith("gradle-wrapper")
                or is_binary_indicator(name)
            ):
                files.append(path)
                if len(files) >= max_files:
                    warnings.append(f"达到最大文件数 {max_files}，结果可能不完整。")
                    return sorted(files), warnings
    return sorted(files), warnings


def detect(root: Path, files: list[Path]) -> dict[str, Any]:
    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    versions: dict[str, list[str]] = defaultdict(list)
    frameworks: dict[str, list[str]] = defaultdict(list)
    languages: dict[str, list[str]] = defaultdict(list)
    topology_hints: list[str] = []
    lock_files: list[str] = []
    manifests: list[str] = []
    warnings: list[str] = []

    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        by_name[path.name].append(path)
        if path.name in LOCK_FILE_NAMES:
            lock_files.append(rel(path, root))
        else:
            manifests.append(rel(path, root))

    # Unity
    for path in by_name.get("ProjectVersion.txt", []):
        text = read_text(path)
        match = re.search(r"m_EditorVersion:\s*([^\s]+)", text)
        if match:
            version = match.group(1)
            versions["Unity"].append(version)
            add_evidence(evidence, "Unity", path, root, "editor_version", version)
        else:
            add_evidence(evidence, "Unity", path, root, "manifest", "ProjectVersion.txt")
        languages["Unity"].append("C#")
        frameworks["Unity"].append("Unity")
        topology_hints.append("实时渲染/3D 客户端候选")
    for path in by_name.get("manifest.json", []):
        if "Packages" in path.parts:
            data = json_file(path)
            deps = data.get("dependencies", {}) if isinstance(data.get("dependencies"), dict) else {}
            add_evidence(evidence, "Unity", path, root, "package_manifest", f"{len(deps)} packages")
            for name in ("com.unity.render-pipelines.universal", "com.unity.render-pipelines.high-definition"):
                if name in deps:
                    frameworks["Unity"].append(f"{name}@{deps[name]}")

    # .NET projects
    dotnet_paths = [p for p in files if p.suffix.lower() in {".csproj", ".fsproj", ".vbproj", ".sln"}]
    if dotnet_paths or by_name.get("global.json"):
        languages[".NET"].append("C#/.NET")
        for path in by_name.get("global.json", []):
            data = json_file(path)
            sdk = data.get("sdk", {}) if isinstance(data.get("sdk"), dict) else {}
            version = sdk.get("version")
            if version:
                versions[".NET"].append(str(version))
                add_evidence(evidence, ".NET", path, root, "dotnet_sdk", version)
        for path in dotnet_paths:
            text = read_text(path)
            add_evidence(evidence, ".NET", path, root, "project_file", path.name)
            for pattern, kind in [
                (r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", "target_framework"),
                (r"<LangVersion>([^<]+)</LangVersion>", "language_version"),
            ]:
                for value in re.findall(pattern, text, flags=re.I):
                    versions[".NET"].append(value.strip())
                    add_evidence(evidence, ".NET", path, root, kind, value.strip())
            if re.search(r"<UseWPF>\s*true\s*</UseWPF>", text, flags=re.I):
                frameworks[".NET"].append("WPF")
            if re.search(r"<UseWindowsForms>\s*true\s*</UseWindowsForms>", text, flags=re.I):
                frameworks[".NET"].append("Windows Forms")
            if re.search(r"Microsoft\.WindowsAppSDK|UseWinUI", text, flags=re.I):
                frameworks[".NET"].append("WinUI/Windows App SDK")
        if any(framework in frameworks[".NET"] for framework in ("WPF", "Windows Forms", "WinUI/Windows App SDK")):
            topology_hints.append("Windows 原生桌面客户端")

    # Node / Electron / Tauri
    for path in by_name.get("package.json", []):
        data = json_file(path)
        if not data:
            continue
        deps: dict[str, Any] = {}
        for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            if isinstance(data.get(key), dict):
                deps.update(data[key])
        engines = data.get("engines", {}) if isinstance(data.get("engines"), dict) else {}
        package_manager = data.get("packageManager")
        add_evidence(evidence, "Node.js", path, root, "package_manifest", data.get("name", path.parent.name))
        languages["Node.js"].append("JavaScript/TypeScript")
        if engines.get("node"):
            versions["Node.js"].append(str(engines["node"]))
            add_evidence(evidence, "Node.js", path, root, "node_engine", engines["node"])
        if package_manager:
            add_evidence(evidence, "Node.js", path, root, "package_manager", package_manager)
        for dep_name, tech in [
            ("electron", "Electron"),
            ("@tauri-apps/cli", "Tauri"),
            ("@tauri-apps/api", "Tauri"),
            ("react", "React"),
            ("vue", "Vue"),
            ("@angular/core", "Angular"),
            ("svelte", "Svelte"),
        ]:
            if dep_name in deps:
                versions[tech].append(str(deps[dep_name]))
                frameworks[tech].append(tech)
                add_evidence(evidence, tech, path, root, "dependency", f"{dep_name}={deps[dep_name]}")
        if "electron" in deps:
            languages["Electron"].append("JavaScript/TypeScript")
            topology_hints.append("Web UI + Chromium 桌面壳")
        if "@tauri-apps/cli" in deps or "@tauri-apps/api" in deps:
            languages["Tauri"].append("Rust + JavaScript/TypeScript")
            topology_hints.append("Web UI + 原生 Tauri 桌面壳")
    for name in (".nvmrc", ".node-version"):
        for path in by_name.get(name, []):
            value = read_text(path).strip().splitlines()[0] if read_text(path).strip() else ""
            if value:
                versions["Node.js"].append(value)
                add_evidence(evidence, "Node.js", path, root, "node_version_file", value)

    # Rust / Tauri native side
    for path in by_name.get("rust-toolchain.toml", []) + by_name.get("rust-toolchain", []):
        text = read_text(path)
        match = re.search(r"channel\s*=\s*[\"']([^\"']+)", text)
        value = match.group(1) if match else text.strip().splitlines()[0] if text.strip() else ""
        if value:
            versions["Rust"].append(value)
            add_evidence(evidence, "Rust", path, root, "toolchain", value)
        languages["Rust"].append("Rust")
    for path in by_name.get("Cargo.toml", []):
        text = read_text(path)
        add_evidence(evidence, "Rust", path, root, "cargo_manifest", path.parent.name)
        languages["Rust"].append("Rust")
        edition = re.search(r"edition\s*=\s*[\"']([^\"']+)", text)
        if edition:
            versions["Rust"].append(f"edition {edition.group(1)}")
        tauri = re.search(r"(?:tauri|tauri-build)\s*=\s*(?:\{[^}]*version\s*=\s*)?[\"']([^\"']+)", text)
        if tauri:
            versions["Tauri"].append(tauri.group(1))
            frameworks["Tauri"].append("Tauri")
            add_evidence(evidence, "Tauri", path, root, "crate", tauri.group(1))

    # Python
    python_detected = False
    for name in ("pyproject.toml", ".python-version", "Pipfile", "requirements.txt", "requirements.lock", "poetry.lock", "uv.lock"):
        for path in by_name.get(name, []):
            python_detected = True
            add_evidence(evidence, "Python", path, root, "manifest_or_lock", name)
            text = read_text(path)
            for pattern in [
                r"requires-python\s*=\s*[\"']([^\"']+)",
                r"python_version\s*=\s*[\"']([^\"']+)",
            ]:
                match = re.search(pattern, text, flags=re.I)
                if match:
                    versions["Python"].append(match.group(1))
            if name == ".python-version" and text.strip():
                versions["Python"].append(text.strip().splitlines()[0])
            for framework, pattern in [
                ("PySide", r"\bPySide[26]?\b"),
                ("PyQt", r"\bPyQt[56]?\b"),
                ("Kivy", r"\bkivy\b"),
                ("wxPython", r"\bwxPython\b"),
                ("Flet", r"\bflet\b"),
            ]:
                if re.search(pattern, text, flags=re.I):
                    frameworks["Python"].append(framework)
        
    if python_detected:
        languages["Python"].append("Python")
        if frameworks["Python"]:
            topology_hints.append("Python GUI 桌面客户端候选")

    # Java / JVM
    java_paths = by_name.get("pom.xml", []) + by_name.get("build.gradle", []) + by_name.get("build.gradle.kts", [])
    for path in java_paths:
        text = read_text(path)
        add_evidence(evidence, "Java/JVM", path, root, "build_manifest", path.name)
        languages["Java/JVM"].append("Java/Kotlin")
        for pattern in [
            r"<java\.version>([^<]+)</java\.version>",
            r"<maven\.compiler\.release>([^<]+)</maven\.compiler\.release>",
            r"sourceCompatibility\s*=\s*[\"']?([^\s\"']+)",
            r"JavaLanguageVersion\.of\((\d+)\)",
        ]:
            for value in re.findall(pattern, text, flags=re.I):
                versions["Java/JVM"].append(str(value))
        if re.search(r"javafx", text, flags=re.I):
            frameworks["Java/JVM"].append("JavaFX")
            topology_hints.append("JVM 桌面客户端")
        if re.search(r"swing", text, flags=re.I):
            frameworks["Java/JVM"].append("Swing")

    # C++ / Qt / CMake
    cmake_paths = by_name.get("CMakeLists.txt", [])
    qmake_paths = [p for p in files if p.suffix.lower() in {".pro", ".pri"}]
    if cmake_paths or qmake_paths or by_name.get("vcpkg.json"):
        languages["C++"].append("C/C++")
    for path in cmake_paths:
        text = read_text(path)
        add_evidence(evidence, "C++", path, root, "cmake_manifest", path.parent.name)
        standard = re.search(r"CMAKE_CXX_STANDARD\s+(\d+)", text, flags=re.I)
        if standard:
            versions["C++"].append(f"C++{standard.group(1)}")
        for qt_match in re.findall(r"find_package\s*\(\s*Qt([56])(?:\s+([0-9.]+))?", text, flags=re.I):
            major, version = qt_match
            qt_version = version or f"{major}.x"
            versions["Qt"].append(qt_version)
            frameworks["Qt"].append(f"Qt{major}")
            add_evidence(evidence, "Qt", path, root, "find_package", qt_version)
        if re.search(r"Qt[56]?::|QT\s*\+=", text):
            frameworks["Qt"].append("Qt")
    for path in qmake_paths:
        text = read_text(path)
        add_evidence(evidence, "Qt", path, root, "qmake_project", path.name)
        languages["Qt"].append("C++")
        frameworks["Qt"].append("Qt")
        if re.search(r"\bwidgets\b", text, flags=re.I):
            frameworks["Qt"].append("Qt Widgets")
        if re.search(r"\bquick\b|qml", text, flags=re.I):
            frameworks["Qt"].append("Qt Quick/QML")
    if evidence["Qt"]:
        topology_hints.append("Qt 原生/自绘桌面客户端")

    # Go
    for path in by_name.get("go.mod", []):
        text = read_text(path)
        languages["Go"].append("Go")
        add_evidence(evidence, "Go", path, root, "module", path.parent.name)
        match = re.search(r"^go\s+([^\s]+)", text, flags=re.M)
        if match:
            versions["Go"].append(match.group(1))
        for framework in ("fyne.io/fyne", "github.com/wailsapp/wails", "github.com/webview/webview"):
            if framework in text:
                frameworks["Go"].append(framework)

    # Flutter / Dart
    for path in by_name.get("pubspec.yaml", []):
        text = read_text(path)
        if re.search(r"^\s*flutter\s*:", text, flags=re.M):
            languages["Flutter"].append("Dart")
            frameworks["Flutter"].append("Flutter")
            add_evidence(evidence, "Flutter", path, root, "pubspec", path.parent.name)
            sdk = re.search(r"sdk:\s*[\"']?([^\s\"']+)", text)
            if sdk:
                versions["Flutter"].append(sdk.group(1))
            topology_hints.append("Flutter 跨平台桌面客户端")
    for path in by_name.get(".fvmrc", []):
        data = json_file(path)
        version = data.get("flutter") if data else read_text(path).strip()
        if version:
            versions["Flutter"].append(str(version))
            add_evidence(evidence, "Flutter", path, root, "fvm_version", version)

    # Swift
    for path in by_name.get("Package.swift", []):
        text = read_text(path)
        languages["Swift"].append("Swift")
        add_evidence(evidence, "Swift", path, root, "swift_package", path.parent.name)
        match = re.search(r"swift-tools-version:\s*([0-9.]+)", text)
        if match:
            versions["Swift"].append(match.group(1))
        topology_hints.append("macOS 原生客户端候选")

    # Non-invasive binary/install-directory fingerprints. These are candidates, not proof of source language.
    for path in files:
        name = path.name
        lower = name.lower()
        if re.match(r"^unityplayer\.(?:dll|so|dylib)$", name, re.I):
            add_evidence(evidence, "Unity", path, root, "binary_runtime_indicator", name)
            frameworks["Unity"].append("Unity runtime")
            topology_hints.append("实时渲染/3D 客户端候选")
        if lower in {"app.asar", "resources.app.asar"} or re.match(r"^(?:electron|chrome_elf|libcef)\.", name, re.I):
            add_evidence(evidence, "Electron", path, root, "binary_runtime_indicator", name)
            frameworks["Electron"].append("Chromium/Electron runtime candidate")
            topology_hints.append("Web UI + Chromium 桌面壳候选")
        if re.match(r"^(?:qt[56](?:core|gui|widgets|quick)|libqt[56].*)\.", name, re.I):
            add_evidence(evidence, "Qt", path, root, "binary_runtime_indicator", name)
            frameworks["Qt"].append("Qt runtime candidate")
            topology_hints.append("Qt 原生/自绘桌面客户端候选")
        if re.match(r"^(?:coreclr|hostfxr|hostpolicy)\.", name, re.I) or lower.endswith((".runtimeconfig.json", ".deps.json")):
            add_evidence(evidence, ".NET", path, root, "binary_runtime_indicator", name)
            languages[".NET"].append("C#/.NET candidate")
        if re.match(r"^python3?\d*\.", name, re.I):
            add_evidence(evidence, "Python", path, root, "binary_runtime_indicator", name)
            languages["Python"].append("Python candidate")
        if re.match(r"^(?:jvm|java)\.", name, re.I):
            add_evidence(evidence, "Java/JVM", path, root, "binary_runtime_indicator", name)
            languages["Java/JVM"].append("Java/Kotlin candidate")
        if path.suffix.lower() in {".uproject", ".uplugin"} or re.match(r"^(?:UnrealEditor|UE4Editor|UE5Editor)", name, re.I):
            add_evidence(evidence, "Unreal Engine", path, root, "binary_or_project_indicator", name)
            frameworks["Unreal Engine"].append("Unreal Engine")
            languages["Unreal Engine"].append("C++/Blueprint candidate")
            topology_hints.append("实时 3D/仿真客户端候选")

    # Build a scored candidate list.
    candidates: list[dict[str, Any]] = []
    technologies = sorted(set(evidence) | set(languages) | set(frameworks) | set(versions))
    for tech in technologies:
        ev = evidence.get(tech, [])
        score = 0.25
        if ev:
            score += min(0.45, 0.12 * len(ev))
        if versions.get(tech):
            score += 0.15
        if frameworks.get(tech):
            score += 0.10
        score = min(0.99, score)
        candidates.append(
            {
                "technology": tech,
                "languages": unique(languages.get(tech, [])),
                "frameworks": unique(frameworks.get(tech, [])),
                "version_evidence": unique(versions.get(tech, [])),
                "confidence": round(score, 2),
                "evidence": ev,
                "status": (
                    "INFERRED_FROM_BINARY_FINGERPRINT"
                    if ev and all("binary" in item.get("kind", "") for item in ev)
                    else "OBSERVED_FROM_SOURCE_FILES"
                ),
            }
        )

    candidates.sort(key=lambda item: (-float(item["confidence"]), item["technology"]))
    if not candidates:
        warnings.append("未找到受支持的项目清单。结果不代表项目没有技术栈，需人工检查。")

    return {
        "candidates": candidates,
        "manifests": unique(manifests),
        "lock_files": unique(lock_files),
        "topology_hints": unique(topology_hints),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="只读识别源码工程的语言、框架和版本证据")
    parser.add_argument("project_dir", help="源码项目目录")
    parser.add_argument("--output", "--json", dest="output", default=None, help="JSON 输出文件")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--max-files", type=int, default=5000)
    args = parser.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"错误：源码目录不存在：{root}", file=sys.stderr)
        return 2

    files, scan_warnings = collect_files(root, max(1, args.max_depth), max(10, args.max_files))
    result = detect(root, files)
    result.update(
        {
            "scan_root": str(root),
            "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "files_examined": len(files),
            "scan_warnings": scan_warnings,
            "conclusion_boundary": "该结果是源码清单指纹，不自动决定重建软件目标技术栈。",
        }
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
