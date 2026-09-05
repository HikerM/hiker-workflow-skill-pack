from __future__ import annotations
import argparse,json,re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from corelib import git_info
from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from technology_markers import NODE_FRAMEWORK_PACKAGES, PACKAGE_MANAGER_LOCKS

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

def safe_json(path:Path)->dict[str,Any]:
    try:
        data=json.loads(safe_text(path));return data if isinstance(data,dict) else {}
    except Exception:return {}
def safe_toml(text:str)->dict[str,Any]:
    if tomllib is None:return {}
    try:
        data=tomllib.loads(text);return data if isinstance(data,dict) else {}
    except Exception:return {}
def first_text(*paths:Path)->str|None:
    for p in paths:
        try:
            value=safe_text(p).strip()
            if value:return value.splitlines()[0].strip()
        except OSError:pass
    return None
def exact_node_version(root:Path,package:str,declared:str|None)->str|None:
    installed=safe_json(root/"node_modules"/package/"package.json").get("version")
    if installed:return str(installed)
    lock=safe_json(root/"package-lock.json");packages=lock.get("packages",{}) if isinstance(lock,dict) else {};item=packages.get(f"node_modules/{package}",{}) if isinstance(packages,dict) else {}
    return str(item.get("version")) if isinstance(item,dict) and item.get("version") else declared

def detect_package_json(path:Path)->dict[str,Any]:
    root=path.parent;data=safe_json(path);deps={}
    for key in ("dependencies","devDependencies","peerDependencies","optionalDependencies"):
        value=data.get(key,{})
        if isinstance(value,dict):deps.update({str(k):str(v) for k,v in value.items()})
    frameworks=[{"name":display,"package":package,"version":exact_node_version(root,package,deps.get(package))} for package,(_framework_id,display,_roles) in NODE_FRAMEWORK_PACKAGES.items() if package in deps]
    pm_raw=data.get("packageManager");pm_name=None;pm_version=None
    if isinstance(pm_raw,str) and "@" in pm_raw:pm_name,pm_version=pm_raw.rsplit("@",1)
    elif isinstance(pm_raw,str):pm_name=pm_raw
    if not pm_name:
        pm_name=next((manager for filename,manager in PACKAGE_MANAGER_LOCKS if (root/filename).exists()),None)
    node_version=(data.get("engines",{}) or {}).get("node") if isinstance(data.get("engines",{}),dict) else None
    volta=data.get("volta",{}) if isinstance(data.get("volta",{}),dict) else {}
    node_version=volta.get("node") or first_text(root/".nvmrc",root/".node-version") or node_version
    ts_version=exact_node_version(root,"typescript",deps.get("typescript")) if "typescript" in deps or (root/"tsconfig.json").exists() else None
    languages=[{"name":"TypeScript","version":ts_version}] if ts_version or (root/"tsconfig.json").exists() else [{"name":"JavaScript","version":None}]
    return {"kind":"web-node","root":str(root),"name":data.get("name") or root.name,"languages":languages,"runtimes":[{"name":"Node.js","version":node_version}],"frameworks":frameworks,"package_manager":{"name":pm_name,"version":pm_version},"scripts":data.get("scripts",{}),"manifest":str(path)}

def detect_unity(path:Path)->dict[str,Any]|None:
    if path.parent.name!="ProjectSettings":return None
    root=path.parent.parent;manifest=root/"Packages/manifest.json";text=safe_text(path);m=re.search(r"m_EditorVersion:\s*([^\r\n]+)",text);packages=safe_json(manifest).get("dependencies",{}) if manifest.exists() else {}
    ui=[]
    if isinstance(packages,dict):
        if "com.unity.ugui" in packages:ui.append("UGUI")
        if "com.unity.ui" in packages:ui.append("UI Toolkit")
    return {"kind":"unity","root":str(root),"name":root.name,"languages":[{"name":"C#","version":"Unity-managed"}],"frameworks":[{"name":"Unity","version":m.group(1).strip() if m else None}],"ui_systems":ui or ["unknown"],"packages":packages,"manifest":str(path)}

def detect_python(path:Path)->dict[str,Any]:
    root=path.parent;deps=[];version=first_text(root/".python-version")
    if path.name=="pyproject.toml":
        data=safe_toml(safe_text(path))
        project=data.get("project",{}) if isinstance(data,dict) else {}
        if isinstance(project,dict):version=version or project.get("requires-python");raw=project.get("dependencies",[]);deps.extend(map(str,raw if isinstance(raw,list) else []))
        poetry=(data.get("tool",{}) or {}).get("poetry",{}) if isinstance(data,dict) else {}
        if isinstance(poetry,dict) and isinstance(poetry.get("dependencies"),dict):deps.extend(str(x) for x in poetry["dependencies"].keys())
    else:
        try:deps=[x.strip() for x in safe_text(path).splitlines() if x.strip() and not x.lstrip().startswith("#")]
        except OSError:pass
    low="\n".join(deps).lower();frameworks=[name for token,name in [("fastapi","FastAPI"),("django","Django"),("flask","Flask"),("sqlalchemy","SQLAlchemy"),("pydantic","Pydantic")] if token in low]
    return {"kind":"python","root":str(root),"name":root.name,"languages":[{"name":"Python","version":version}],"frameworks":frameworks,"dependencies":deps[:500],"manifest":str(path)}

def detect_dotnet(path:Path)->dict[str,Any]:
    root=path.parent;targets=[];packages=[];lang=None;properties={};sdk=""
    try:
        tree=ET.parse(path)
        sdk=tree.getroot().attrib.get("Sdk","")
        for node in tree.iter():
            tag=node.tag.split("}")[-1]
            if tag in {"TargetFramework","TargetFrameworks"} and node.text:targets.extend(x.strip() for x in node.text.split(";") if x.strip())
            elif tag=="LangVersion" and node.text:lang=node.text.strip()
            elif tag=="PackageReference":packages.append({"name":node.attrib.get("Include","") or node.attrib.get("Update",""),"version":node.attrib.get("Version")})
            elif tag in {"UseWPF","UseWindowsForms","UseWinUI","UseMaui"} and node.text:properties[tag]=node.text.strip()
    except Exception:pass
    package_names=" ".join(x.get("name","") for x in packages).lower();package_versions={x.get("name","").lower():x.get("version") for x in packages};target_version=",".join(targets) or None;frameworks=[{"name":".NET","version":target_version,"evidence":"TargetFramework(s)"}]
    for key,name in [("UseWPF","WPF"),("UseWindowsForms","WinForms"),("UseWinUI","WinUI"),("UseMaui",".NET MAUI")]:
        if properties.get(key,"").lower()=="true":frameworks.append({"name":name,"version":target_version,"evidence":key+" + TargetFramework(s)"})
    if "avalonia" in package_names:
        version=next((v for k,v in package_versions.items() if "avalonia" in k and v),None);frameworks.append({"name":"Avalonia","version":version,"evidence":"PackageReference"})
    if "maui" in sdk.lower() and not any(x["name"]==".NET MAUI" for x in frameworks):frameworks.append({"name":".NET MAUI","version":target_version,"evidence":"Project Sdk + TargetFramework(s)"})
    return {"kind":"dotnet","root":str(root),"name":root.name,"languages":[{"name":"C#","version":lang}],"frameworks":frameworks,"packages":packages,"manifest":str(path)}

def detect_maven(path:Path)->dict[str,Any]:
    root=path.parent;props={};artifacts=[];dependencies=[]
    try:
        tree=ET.parse(path)
        for node in tree.iter():
            tag=node.tag.split("}")[-1]
            if tag in {"java.version","maven.compiler.source","maven.compiler.target"} and node.text:props[tag]=node.text.strip()
            elif tag=="artifactId" and node.text:artifacts.append(node.text.strip())
        for dep in tree.iter():
            if dep.tag.split("}")[-1]!="dependency":continue
            values={child.tag.split("}")[-1]:(child.text or "").strip() for child in dep}
            dependencies.append(values)
    except Exception:pass
    frameworks=[{"name":"Spring Boot","version":None}] if any("spring-boot" in x for x in artifacts) else []
    javafx=next((x for x in dependencies if "javafx" in x.get("artifactId","").lower()),None)
    if javafx:frameworks.append({"name":"JavaFX","version":javafx.get("version") or None,"evidence":"Maven dependency"})
    return {"kind":"java","root":str(root),"name":root.name,"languages":[{"name":"Java","version":props.get("java.version") or props.get("maven.compiler.source")}],"frameworks":frameworks,"manifest":str(path)}

def detect_simple(path:Path)->dict[str,Any]|None:
    root=path.parent;text=safe_text(path)
    if path.name=="go.mod":
        m=re.search(r"^go\s+([^\s]+)",text,re.M);return {"kind":"go","root":str(root),"name":root.name,"languages":[{"name":"Go","version":m.group(1) if m else None}],"manifest":str(path)}
    if path.name=="Cargo.toml":
        data=safe_toml(text)
        pkg=data.get("package",{}) if isinstance(data,dict) else {};return {"kind":"rust","root":str(root),"name":pkg.get("name") or root.name,"languages":[{"name":"Rust","version":pkg.get("rust-version")}],"manifest":str(path)}
    if path.name=="composer.json":
        data=safe_json(path);deps=data.get("require",{}) if isinstance(data,dict) else {};frameworks=[{"name":"Laravel","version":deps.get("laravel/framework")}] if isinstance(deps,dict) and "laravel/framework" in deps else []
        return {"kind":"php","root":str(root),"name":data.get("name") or root.name,"languages":[{"name":"PHP","version":deps.get("php") if isinstance(deps,dict) else None}],"frameworks":frameworks,"manifest":str(path)}
    if path.name in {"build.gradle","build.gradle.kts"}:
        m=re.search(r"JavaLanguageVersion\.of\((\d+)\)|sourceCompatibility\s*=\s*['\"]?([^'\"\s]+)",text);version=next((g for g in (m.groups() if m else []) if g),None);frameworks=[]
        if "org.springframework.boot" in text:frameworks.append({"name":"Spring Boot","version":None})
        android_plugin=re.search(r"com\.android\.(?:application|library)[\"']?\s+version\s+[\"']([^\"']+)",text)
        compile_sdk=re.search(r"compileSdk(?:Version)?\s*[=( ]\s*(\d+)",text)
        if "com.android.application" in text or "com.android.library" in text:frameworks.append({"name":"Android","version":android_plugin.group(1) if android_plugin else ("API "+compile_sdk.group(1) if compile_sdk else None),"evidence":"Gradle plugin or compileSdk"})
        compose_version=re.search(r"(?:compose|kotlinCompilerExtensionVersion)[^\n]*?[\"']([0-9][^\"']*)[\"']",text,re.I)
        if "compose" in text.lower():frameworks.append({"name":"Jetpack Compose","version":compose_version.group(1) if compose_version else None,"evidence":"Gradle declaration"})
        javafx_version=re.search(r"org\.openjfx\.javafxplugin[\"']?\s+version\s+[\"']([^\"']+)",text)
        if "javafx" in text.lower():frameworks.append({"name":"JavaFX","version":javafx_version.group(1) if javafx_version else None,"evidence":"Gradle declaration"})
        return {"kind":"java-gradle","root":str(root),"name":root.name,"languages":[{"name":"Java","version":version}],"frameworks":frameworks,"manifest":str(path)}
    if path.name=="CMakeLists.txt":
        m=re.search(r"cmake_minimum_required\s*\(\s*VERSION\s+([^\s\)]+)",text,re.I);frameworks=[]
        qt=re.search(r"find_package\s*\(\s*Qt([56])?(?:\s+([0-9]+(?:\.[0-9]+){1,2}))?",text,re.I)
        if qt or re.search(r"qt_add_",text,re.I):frameworks.append({"name":"Qt","version":qt.group(2) if qt and qt.group(2) else (qt.group(1) if qt and qt.group(1) else None),"evidence":"CMake find_package/qt_add"})
        lvgl=re.search(r"LVGL_VERSION[^0-9]*([0-9]+(?:\.[0-9]+){1,2})",text,re.I)
        if "lvgl" in text.lower():frameworks.append({"name":"LVGL","version":lvgl.group(1) if lvgl else None,"evidence":"CMake declaration"})
        return {"kind":"cmake","root":str(root),"name":root.name,"languages":[{"name":"C/C++","version":None}],"frameworks":frameworks,"build_system":{"name":"CMake","version":m.group(1) if m else None},"manifest":str(path)}
    if path.suffix==".pro":
        qt_version=re.search(r"QT_VERSION\s*[:+?]?=\s*([^\s#]+)",text);modules=[]
        for value in re.findall(r"^\s*QT\s*\+=\s*(.+)$",text,re.M):modules.extend(value.split())
        return {"kind":"qt-qmake","root":str(root),"name":root.name,"languages":[{"name":"C++","version":None}],"frameworks":[{"name":"Qt","version":qt_version.group(1) if qt_version else None,"evidence":"qmake .pro"}],"ui_systems":sorted(set(modules)),"build_system":{"name":"qmake","version":None},"manifest":str(path)}
    if path.name=="Package.swift":
        tools=re.search(r"swift-tools-version:\s*([^\s]+)",text);platforms=re.findall(r"\.(macOS|iOS|tvOS|watchOS)\s*\(\s*\.v([0-9_]+)",text);frameworks=[]
        if "SwiftUI" in text:frameworks.append({"name":"SwiftUI","version":dict(platforms).get("iOS") or dict(platforms).get("macOS"),"evidence":"Package.swift platform"})
        if "UIKit" in text:frameworks.append({"name":"UIKit","version":dict(platforms).get("iOS"),"evidence":"Package.swift platform"})
        if "AppKit" in text:frameworks.append({"name":"AppKit","version":dict(platforms).get("macOS"),"evidence":"Package.swift platform"})
        return {"kind":"swift","root":str(root),"name":root.name,"languages":[{"name":"Swift","version":tools.group(1) if tools else None}],"frameworks":frameworks,"platforms":[{"name":x,"version":v.replace("_",".")} for x,v in platforms],"manifest":str(path)}
    if path.name=="project.pbxproj":
        ios=re.search(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*([^;]+);",text);mac=re.search(r"MACOSX_DEPLOYMENT_TARGET\s*=\s*([^;]+);",text);frameworks=[]
        if "SwiftUI.framework" in text or "SWIFT_VERSION" in text:frameworks.append({"name":"SwiftUI","version":ios.group(1).strip() if ios else (mac.group(1).strip() if mac else None),"evidence":"Xcode deployment target"})
        return {"kind":"apple-xcode","root":str(path.parent.parent),"name":path.parent.parent.name,"languages":[{"name":"Swift","version":next(iter(re.findall(r'SWIFT_VERSION\s*=\s*([^;]+);',text)),None)}],"frameworks":frameworks,"platforms":[x for x in [{"name":"iOS","version":ios.group(1).strip() if ios else None},{"name":"macOS","version":mac.group(1).strip() if mac else None}] if x["version"]],"manifest":str(path)}
    if path.name=="Gemfile":return {"kind":"ruby","root":str(root),"name":root.name,"languages":[{"name":"Ruby","version":first_text(root/".ruby-version")}],"frameworks":[{"name":"Rails","version":None}] if "rails" in text.lower() else [],"manifest":str(path)}
    if path.name=="pubspec.yaml":
        sdk=re.search(r"sdk:\s*['\"]?([^'\"\n]+)",text);flutter="flutter:" in text;metadata=safe_text(root/".metadata") if (root/".metadata").exists() else "";lock=safe_text(root/"pubspec.lock") if (root/"pubspec.lock").exists() else ""
        flutter_constraint=re.search(r"flutter:\s*['\"]?([^'\"\n]+)",text)
        fvm=safe_json(root/".fvmrc").get("flutter") or safe_json(root/".fvm/fvm_config.json").get("flutterSdkVersion")
        pinned=fvm or first_text(root/".flutter-version");lock_constraint=re.search(r"sdks:\s*(?:\r?\n)+\s*dart:\s*[^\n]+(?:\r?\n)+\s*flutter:\s*['\"]?([^'\"\n]+)",lock)
        revision=re.search(r"revision:\s*['\"]?([^'\"\n]+)",metadata)
        version=pinned or (flutter_constraint.group(1).strip() if flutter_constraint else (lock_constraint.group(1).strip() if lock_constraint else None))
        evidence="FVM/.flutter-version" if pinned else "pubspec or lock constraint" if version else "metadata revision" if revision else "not found"
        framework={"name":"Flutter","version":version,"evidence":evidence}
        if revision:framework["revision"]=revision.group(1).strip()
        return {"kind":"flutter" if flutter else "dart","root":str(root),"name":root.name,"languages":[{"name":"Dart","version":sdk.group(1).strip() if sdk else None}],"frameworks":[framework] if flutter else [],"manifest":str(path)}
    return None

def candidate_scan(root:Path,max_depth:int)->tuple[list[Path],dict[str,Any]]:
    files,metrics=walk_source_files(
        root,
        TraversalBudget(max_depth=max_depth),
        ignored_directories=frozenset(name.casefold() for name in IGNORED),
        include=lambda candidate:candidate.name in MANIFESTS or candidate.suffix in {".csproj",".pro"},
    )
    return sorted(set(files)),{"status":"COMPLETE",**metrics.__dict__}

def candidates(root:Path,max_depth:int)->list[Path]:
    budget=DiscoveryBudget(max_depth=max(0,min(max_depth,8)),max_dirs=256,max_manifests=128,max_bytes=4*1024*1024,max_entries_per_dir=512)
    report=discover_engineering_manifests(root,budget=budget)
    return [root/item["path"] for item in report["manifests"]]
def detect(root:Path,max_depth:int=6)->dict[str,Any]:
    root=root.resolve();projects=[];seen=set();oversized=0
    try:
        found,traversal=candidate_scan(root,max_depth)
    except TraversalLimitReached as exception:
        return {"schema_version":"1.0.0","repository":git_info(root),"scan_root":str(root),"projects":[],"monorepo":False,"unknown":True,"uncertainties":["源码扫描达到确定性遍历预算"],"traversal":exception.receipt()}
    for path in found:
        try:
            if path.stat().st_size>MAX_MANIFEST_BYTES:oversized+=1;continue
        except OSError:continue
        item=None
        if path.name=="package.json":item=detect_package_json(path)
        elif path.name=="ProjectVersion.txt":item=detect_unity(path)
        elif path.name in {"pyproject.toml","requirements.txt"}:item=detect_python(path)
        elif path.suffix==".csproj":item=detect_dotnet(path)
        elif path.name=="pom.xml":item=detect_maven(path)
        else:item=detect_simple(path)
        if not item:continue
        key=(str(item.get("root")),str(item.get("kind")))
        if key in seen:continue
        seen.add(key);projects.append(item)
    uncertainties=(["未安装依赖时框架版本可能保留声明范围"] if projects else ["未找到受支持的工程清单"])
    if oversized:uncertainties.append(f"{oversized} 个工程清单超过单文件读取预算")
    return {"schema_version":"1.0.0","repository":git_info(root),"scan_root":str(root),"projects":projects,"monorepo":len(projects)>1,"unknown":not projects,"uncertainties":uncertainties,"traversal":traversal}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--max-depth",type=int,default=6);ap.add_argument("--output");a=ap.parse_args();data=detect(Path(a.root),a.max_depth);text=json.dumps(data,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(text+"\n",encoding="utf-8")
    else:print(text)
    return 0
if __name__=="__main__":raise SystemExit(main())
