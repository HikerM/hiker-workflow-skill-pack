from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
RUN_KEY=hashlib.sha256(str(ROOT.resolve()).encode("utf-8")).hexdigest()[:12]
ARTIFACTS=Path(tempfile.gettempdir())/"Hiker"/"skill-validation"/RUN_KEY
EXCERPT_CHARS=3000
TEST_COUNT_RE=re.compile(r"\bRan\s+(\d+)\s+tests?\b")
WINDOWS_ABSOLUTE_RE=re.compile(
    r"(?i)(?<![A-Z0-9_])(?:[A-Z]:)(?:\\+|/+)[^\r\n\"'<>|?*]+"
)
UNC_PATH_RE=re.compile(r"(?<!\\)\\{2,}[^\\/\s\"'<>|?*]+(?:\\+[^\r\n\"'<>|?*]+)+")
UNIX_PRIVATE_PATH_RE=re.compile(
    r"(?<![A-Z0-9_:])(?:\\?/)(?:Users|home|tmp|private(?:\\?/)tmp|var(?:\\?/)tmp)"
    r"(?:\\?/)[^\r\n\"'<>]+",
    re.IGNORECASE,
)


def excerpt(value:str,limit:int=EXCERPT_CHARS)->str:
    if len(value)<=limit:return value
    half=max(1,(limit-80)//2)
    return value[:half]+"\n... 中间输出已写入证据日志 ...\n"+value[-half:]


def redact_public_output(value:str)->str:
    """Remove machine/user paths before output is copied into tracked evidence."""
    redacted=value
    known_paths={ROOT,Path.home(),Path(tempfile.gettempdir()),Path(sys.prefix)}
    for path in sorted(known_paths,key=lambda item:len(str(item)),reverse=True):
        raw=str(path)
        variants={raw,raw.replace("\\","/"),raw.replace("\\","\\\\")}
        for variant in sorted(variants,key=len,reverse=True):
            if variant:
                redacted=redacted.replace(variant,"<LOCAL_PATH>")
    redacted=WINDOWS_ABSOLUTE_RE.sub("<LOCAL_PATH>",redacted)
    redacted=UNC_PATH_RE.sub("<LOCAL_PATH>",redacted)
    redacted=UNIX_PRIVATE_PATH_RE.sub("<LOCAL_PATH>",redacted)
    return redacted


def executed_test_count(value:str)->int|None:
    matches=TEST_COUNT_RE.findall(value)
    return int(matches[-1]) if matches else None


def source_fingerprint(paths:list[Path])->str:
    digest=hashlib.sha256()
    for base in paths:
        for path in sorted(item for item in base.rglob("*") if item.is_file() and item.suffix.lower() in {".py",".md",".json",".yaml",".yml",".csv"} and ".codex-output" not in item.parts):
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"));digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def main()->int:
    parser=argparse.ArgumentParser(description="运行全部或指定插件的有界测试分片")
    parser.add_argument("--plugin",action="append",default=[],help="只运行指定插件；可重复")
    args=parser.parse_args()
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    available={item.name:item for item in (ROOT/"plugins").iterdir() if item.is_dir()}
    unknown=sorted(set(args.plugin)-set(available))
    if unknown:
        print(json.dumps({"ok":False,"error":"unknown plugin","plugins":unknown},ensure_ascii=False));return 2
    selected=[available[name] for name in dict.fromkeys(args.plugin)] if args.plugin else [available[name] for name in sorted(available)]
    results=[];ok=True
    for plugin in selected:
        start=time.time();p=subprocess.run([sys.executable,"-X","utf8","-m","unittest","discover","-s",str(plugin/"tests"),"-p","test*.py","-v"],text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log=ARTIFACTS/f"{plugin.name}.log";log.write_text(p.stdout,encoding="utf-8")
        public_output=redact_public_output(p.stdout)
        item={
            "plugin":plugin.name,"ok":p.returncode==0,"seconds":round(time.time()-start,3),
            "test_count":executed_test_count(p.stdout),
            "output_excerpt":excerpt(public_output),"output_chars":len(p.stdout),
            "log_reference":f"temporary/{plugin.name}.log",
            "log_sha256":hashlib.sha256(p.stdout.encode("utf-8")).hexdigest(),
        };results.append(item);ok &= item["ok"]
        print(f"{plugin.name}: {'PASS' if item['ok'] else 'FAIL'} | {item['seconds']}s | {item['output_chars']} chars | temporary evidence")
        if not item["ok"]:print(item["output_excerpt"])
    counts=[item["test_count"] for item in results]
    report={
        "ok":ok,
        "partial":bool(args.plugin),
        "plugins":[item.name for item in selected],
        "source_fingerprint":source_fingerprint(selected+[ROOT/"tools"]),
        "test_count":sum(count for count in counts if isinstance(count,int)),
        "test_count_complete":all(isinstance(count,int) for count in counts),
        "results":results,
    }
    if args.plugin:
        shard_dir=ARTIFACTS/"test-results";shard_dir.mkdir(parents=True,exist_ok=True)
        target=shard_dir/("+".join(item.name for item in selected)+".json")
    else:
        target=ROOT/"test-results.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    evidence_label=target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else f"temporary/{target.name}"
    print(f"evidence: {evidence_label} | source {report['source_fingerprint']}")
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
