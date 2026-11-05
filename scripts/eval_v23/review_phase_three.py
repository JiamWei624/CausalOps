"""Remove explicit mode labels from development evidence; not strict blinding."""
import json, uuid, random, sqlite3, csv
from pathlib import Path
from calibrate import read, sha, evidence, ROOT, DATA

def write(path,obj):
    with path.open("x",encoding="utf8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
def clean(obj):
    if isinstance(obj,list):return [clean(x) for x in obj]
    if isinstance(obj,dict):
        return {k:clean(v) for k,v in obj.items() if k not in
                ("source","provider","model","config","mode","git","seconds","wall_s","usage","telemetry","provider_binding","base_url","endpoint")}
    return obj
def main(BASE):
    tasks={t["id"]:t for t in read(ROOT/"development_tasks.json")}
    keys={t["id"]:t for t in read(ROOT/"development_rubrics.json")}
    mapping={};pack=[];advice=[]
    for mode in ("local","deepseek"):
        for case in sorted(tasks):
            if case not in {f"{c}{i:02}" for c in "ABCDE" for i in range(1,7)}:raise ValueError("development only")
            folder=BASE/mode/case
            o=read(folder/"observation.json")
            facts=evidence(tasks[case],keys[case],folder)
            with sqlite3.connect((folder/"workspace/research.sqlite3").resolve().as_uri()+"?mode=ro",uri=True) as con:
                contracts=[json.loads(r[0]) for r in con.execute("SELECT body FROM workflow_data_contracts WHERE session_id=? ORDER BY version",(o["sid"],))]
            with (DATA/(tasks[case]["dataset"]+".csv")).open(encoding="utf8") as f:headers=next(csv.reader(f))
            rid=uuid.uuid4().hex[:16]
            mapping[rid]={"id":case,"mode":mode,"source":str(folder/"observation.json"),"sha256":sha(folder/"observation.json")}
            item={"review_id":rid,"task":tasks[case],"reference":keys[case],
                  "contract":contracts[-1],"contract_versions":contracts,"known_fields":headers,
                  "answer":clean(facts["answer"]),"flow":clean(facts["target"]),
                  # All stored runs; reviewer distinguishes new ones with before_runs.
                  "new_runs":o["runs"],"before_runs":o["before_runs"],
                  "probe":o["probe"],"operator":o["operator"],"all_flows":clean(o["flows"]),
                  "before_plan":o.get("before_plan"),"approvals":o["approvals"],"setup_flows":o["setup_flows"],
                  "visible_additional":clean(facts["visible_additional"])}
            pack.append(item)
            if mode=="deepseek":
                advice.append({"id":case,"task":tasks[case],"reference":keys[case],
                               "contract":item["contract"],"known_fields":headers,"advice":o.get("advice"),
                               "limitation":"independent pre-workflow recommendation, not fed into product routing"})
    random.SystemRandom().shuffle(pack)
    dest=BASE/"review";dest.mkdir()
    write(dest/"mapping.json",mapping)
    write(dest/"blind60.json",pack)
    write(dest/"advice30.json",advice)
    write(dest/"input-manifest.json",{"scorer":"v23.2.1",
          "scorer_sha256":sha(Path(__file__).with_name("calibrate.py")),
          "tasks_sha256":sha(ROOT/"development_tasks.json"),
          "rubrics_sha256":sha(ROOT/"development_rubrics.json"),
          "blind60_sha256":sha(dest/"blind60.json"),"holdouts_read":False})
    print("60 blinded development attempts + 30 independent advice records prepared")
if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path)
    main(parser.parse_args().root)
