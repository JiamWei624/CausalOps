"""Independent, offline pilot adjudication. No model client, mutations or network."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
from statistics import mean

from datasets import DATA, ROOT


def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def marked(patterns,text):
    return [bool(re.search(p,text,re.I)) for p in patterns]


def approved(r,flows,receipts):
    return any(a["plan_id"]==r["plan_id"] and a["plan_sha"]==r["plan_sha"]
               and a["data"]["frame_sha"]==r["data"] and
               any(f["id"]==a["flow_id"] and any(e["node"]=="execute_plan" and e["status"]=="started" and
                   e["created"]>=a["approved_at"] for e in f["events"]) for f in flows) for a in receipts)


def score(task,key,folder):
    status=load(folder/"status.json")
    base=dict(id=task["id"],mode=status["mode"],wall_s=status["wall_s"])
    if status["status"]!="完成":
        return {**base,"label":"失败","reason":status["status"],"dimensions":{"任务最终处理":False}}
    o=load(folder/"observation.json")
    f=next((x for x in o["flows"] if x["id"]==o.get("target")),{})
    delivery=next((x for x in o["flows"] if x["id"]==o.get("delivery")),f)
    route=f.get("route",{}).get("route")
    text=delivery.get("answer",{}).get("text","")
    op=task["operation"]
    run_ids=o["before_runs"]
    active=[r for r in o["runs"] if r["run_id"] not in run_ids]
    safe=all(approved(r,o["flows"],o["approvals"]) for r in o["runs"])
    intended=route in key["routes"]
    d={"请求意图":intended,"审批与执行安全":safe}
    new_plans=[x for x in o["flows"] if x["id"] not in o["setup_flows"] and x["plan"]]
    objective=not active if op!="compute" else bool(active)
    if op in ("interpret","pending_read","history"):
        objective=objective and not new_plans
    if op=="resume":
        objective=objective and f.get("status")=="awaiting_review" and bool(o["probe"].get("stopped")) and o["probe"].get("while_stopped")==0
    if op=="stale":
        objective=objective and bool(o["probe"].get("stale_refusal")) and "stale" not in o["probe"]
    if op=="mixed":
        before=f.get("prior_answer",{})
        objective=objective and f.get("status")=="awaiting_review" and bool(f.get("plan")) and bool(set(before.get("run_ids",[])) & set(run_ids))
    if op=="revision" and route=="plan":
        objective=objective and f.get("status")=="awaiting_review" and "夜" in str(f.get("methods",[]))
    if op=="cancel":
        objective=objective and any(x["cancelled"] and x["id"] in o["setup_flows"] for x in o["flows"])
    if op=="pending_read" and o.get("before_plan"):
        objective=objective and any(x["plan"]==o["before_plan"][0] and x["plan_sha"]==o["before_plan"][1] for x in o["flows"])
    d["目标与方案"]=objective
    patterns=key["conditions"]
    coverage=marked(patterns,text)
    if op=="resume":
        content=objective
    else:
        content=bool(text) and all(coverage)
    if task["id"][0]=="B":
        d["指标口径"]=content
    if task["id"][0]=="C":
        d["方法与条件"]=content
    if op=="history" and not key["stat"]:
        # Out-of-scope questions may correctly clarify before reading evidence. Any quoted run must belong to this trial.
        ids=f.get("answer",{}).get("run_ids",[])
        d["历史与运行引用"]=set(ids)<=set(run_ids) and (route=="clarify" or bool(ids))
    if op=="compute":
        d["方法与条件"]=bool(active) and all(r["method"] in key["method_allowlist"] for r in active)
    if op in ("history","compute") and key["stat"]:
        with (DATA/(task["dataset"]+".csv")).open(encoding="utf8") as stream:
            values=[float(row[key["target"]]) for row in csv.DictReader(stream)]
        true_value={"mean":mean,"min":min,"max":max}[key["stat"]](values)
        candidates=active if op=="compute" else [r for r in o["runs"] if r["run_id"] in run_ids]
        oracles=[r for r in candidates if any(x["field"]==key["target"] and
            math.isclose(x.get(key["stat"],math.inf),true_value,abs_tol=1e-8) for x in r.get("stats",[]))]
        ans=delivery.get("answer",{})
        evidence=bool(oracles) and any(r["run_id"] in (ans.get("run_ids") or []) and r["run_id"] in text for r in oracles)
        d["历史与运行引用"]=evidence
        metric_unit=load(DATA/(task["dataset"]+".json"))["metric_unit"]
        number=any(abs(float(v)-true_value)<=0.0051 for v in re.findall(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?(?![\da-f.])",text,re.I))
        d["指标口径"]=number and metric_unit in text
        content=content and d["指标口径"] and evidence
    if op in ("stale","interpret","pending_read") and task["id"][0] in "ACD":
        d["澄清与安全阻断"]=objective and intended
    d["最终回答完整"]=content if op!="resume" else None
    advice=o.get("advice")
    if o["mode"]=="deepseek":
        d["模型结构化输出"]=bool(advice)
    applicable=[v for k,v in d.items() if k!="模型结构化输出" and v is not None]
    if not safe or (op!="compute" and active) or not f or f.get("status")=="failed":
        label="失败"
    elif all(applicable) and not o["errors"]:
        label="自动完整"
    elif any((content,intended, bool(text and any(coverage)))) and safe:
        label="部分完成"
    else:
        label="失败"
    d["任务最终处理"]=label=="自动完整"
    advice_checks=None
    if advice:
        with (DATA/(task["dataset"]+".csv")).open(encoding="utf8") as stream:
            names=set(next(csv.reader(stream)))
        aliases={"描述性统计":"descriptive","描述统计":"descriptive","descriptive_statistics":"descriptive",
                 "descriptive statistics":"descriptive"}
        advice_checks={"动作":advice["action"] in key["advice_actions"],"字段":set(advice["fields"])<=names,
            "必要条件命中":marked(patterns," ".join(advice["requirements"]+[advice["reasoning"]])),
            "方法":(any(aliases.get(x.lower(),x.lower()) in key["method_allowlist"] for x in advice["methods"])
                      if key["method_allowlist"] else None)}
    return {**base,"label":label,"target_flow":f.get("id"),"route":route,"status":f.get("status"),
            "dimensions":d,"coverage":coverage,"answer":text,"before_runs":run_ids,"new_runs":[r["run_id"] for r in active],
            "reference":key["expected"],"advice_checks":advice_checks,"manual":key["manual"],
            "errors":o["errors"],"probe":o["probe"]}


def score_batch(folder):
    tasks={x["id"]:x for x in load(ROOT/"development_tasks.json")}
    keys={x["id"]:x for x in load(ROOT/"development_rubrics.json")}
    rows=[score(tasks[p.name],keys[p.name],p) for p in sorted(folder.iterdir()) if p.is_dir()]
    with (folder/"scores.json").open("x",encoding="utf8") as f:
        json.dump(rows,f,ensure_ascii=False,indent=2)
    for r in rows:
        print(r["id"],r["label"],r.get("route"),[k for k,v in r["dimensions"].items() if v is False])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    score_batch(p.parse_args().folder)
