from __future__ import annotations
import argparse,json,shutil,tempfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent;NAMES=[p.name for p in (ROOT/"plugins").iterdir() if p.is_dir()]
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--yes",action="store_true");a=ap.parse_args()
    if not a.yes:raise SystemExit("这是卸载操作，请使用 --yes 明确确认。")
    home=Path.home();market=home/".agents/plugins/marketplace.json"
    for n in NAMES:shutil.rmtree(home/".codex/plugins"/n,ignore_errors=True)
    try:data=json.loads(market.read_text(encoding="utf-8"));data["plugins"]=[x for x in data.get("plugins",[]) if x.get("name") not in NAMES];market.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    except Exception:pass
    print(json.dumps({"ok":True,"removed":NAMES},ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
