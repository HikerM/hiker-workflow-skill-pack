from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
from workspacelib import common_dir

def main()->int:
    try:p=json.load(sys.stdin)
    except Exception:p={}
    root=Path(p.get("cwd") or ".").resolve();event=p.get("hook_event_name")
    try:
        log=common_dir(root)/"ai-engineering"/"agent-events.jsonl";log.parent.mkdir(parents=True,exist_ok=True)
        with log.open("a",encoding="utf-8") as f:f.write(json.dumps({"at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"event":event,"session_id":p.get("session_id"),"agent_id":p.get("agent_id"),"agent_type":p.get("agent_type"),"tail":str(p.get("last_assistant_message") or "")[-2000:]},ensure_ascii=False)+"\n")
    except Exception:pass
    if event=="SubagentStart":
        print("[工作区规则] 子Agent只处理被分配的有边界任务；写入任务必须确认独立Worktree和允许目录；将原始日志留在子线程，只向主线程返回结论、证据和风险。")
    else:print(json.dumps({"continue":True}))
    return 0
if __name__=="__main__":raise SystemExit(main())
