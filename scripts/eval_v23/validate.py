"""Validate only development artifacts and the custodian's public receipt."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from datasets import DATA, ROOT, TABLES, contract, rows
from run_pilot import PILOT
from causalops.application.data_contracts import DataContract


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate():
    load=lambda p:json.loads(p.read_text(encoding="utf-8-sig"))
    tasks=load(ROOT/"development_tasks.json")
    rules=load(ROOT/"development_rubrics.json")
    keys={r["id"]:r for r in rules}
    expected={f"{a}{i:02}" for a in "ABCDE" for i in range(1,7)}
    assert len(tasks)==len(rules)==len(expected) and set(keys)=={t["id"] for t in tasks}==expected
    assert len({t["request"] for t in tasks})==len(tasks)
    assert Counter(t[0] for t in PILOT)=={a:2 for a in "ABCDE"}
    for t in tasks:
        name=t["dataset"]
        r=keys[t["id"]]
        assert t["source"]=="data/"+name+".csv" and t["scenario"] and t["initial_state"]
        assert all(r[k] for k in ("expected","conditions","acceptable","prohibited","full","partial","fail","manual","automated"))
        assert r["routes"] and all(re.compile(pattern) for pattern in r["conditions"])
        with (DATA/(name+".csv")).open(encoding="utf8") as f:
            header,*data=list(csv.reader(f))
        assert header==TABLES[name][1].split(",") and data==[[str(v) for v in row] for row in rows(name)]
        assert r["target"] in header
        body=load(DATA/(name+".json"))
        assert body==contract(name)
        DataContract.model_validate(body)
    # Independently recomputable expectations for the pilot's numerical oracles.
    vals=[row[2] for row in rows("lab")]
    receipt=load(ROOT/"holdout-receipt.json")
    assert digest(ROOT/"holdout-receipt.json")=="c127062147cb8f5c2de2e7871b3731286b7a5ee9b4919939cc619ab471e19f54"
    assert set(receipt["ids"]).isdisjoint(expected) and receipt["counts"]=={a:4 for a in "ABCDE"}
    return {"development":30,"holdout_receipt":receipt["total"],"pilot":PILOT,
            "lab_min":min(vals),"lab_mean":sum(vals)/len(vals),
            "development_hashes":{p.relative_to(ROOT).as_posix():digest(p) for p in sorted(DATA.glob("*"))+
            [ROOT/"development_tasks.json",ROOT/"development_rubrics.json",ROOT/"holdout-receipt.json"]}}


if __name__=="__main__":
    print(json.dumps(validate(),ensure_ascii=False,indent=2))
