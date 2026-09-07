#!/usr/bin/env python3
import argparse, json, shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--generated",type=Path,required=True); p.add_argument("--backlog",type=Path,required=True); p.add_argument("--processed",type=Path,required=True); p.add_argument("--pending",type=Path,required=True); a=p.parse_args()
    a.generated.mkdir(parents=True, exist_ok=True)
    processed=set(json.loads(a.processed.read_text())) if a.processed.exists() else set()
    available=[]
    for path in sorted(a.backlog.glob("*.json")):
        data=json.loads(path.read_text(encoding="utf-8"))
        if data["id"] not in processed: available.append((path,data["id"]))
    selected=available[:4]
    if len(selected)<4: print(f"Backlog has {len(selected)} remaining; generated standalone stories fill the rest")
    generated_standalones=sorted(a.generated.glob("daily-*.json"))
    for path in generated_standalones[:len(selected)]: path.unlink()
    for path,_ in selected: shutil.copy2(path,a.generated/path.name)
    pending=json.loads(a.pending.read_text(encoding="utf-8"))
    chapter_ids=[x for x in pending["generated_ids"] if x.startswith("spare-key-")]
    remaining_generated=[]
    for path in a.generated.glob("daily-*.json"): remaining_generated.append(json.loads(path.read_text())["id"])
    pending["generated_ids"]=chapter_ids+[story_id for _,story_id in selected]+remaining_generated
    a.pending.write_text(json.dumps(pending,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Selected {len(selected)} legacy backlog stories")
if __name__=="__main__": main()
