"""Aggregate saved development attempts only; never execute tasks or read holdouts."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from statistics import mean, median

LABELS = ("完整","正确阻断","部分","失败","待人工复核")
DIMENSIONS = ("意图","方案方法","关键条件","指标语义","答复完整","解释严谨","安全","最终处理")
PRICE_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def counts(rows):
    c = Counter(r["label"] for r in rows)
    return {"n":len(rows), **{k:c[k] for k in LABELS},
            "正确处理":c["完整"]+c["正确阻断"]}

def dimensions(rows):
    result = {}
    for key in DIMENSIONS:
        values=[r["review"].get("semantic_dimensions",{}).get(key) for r in rows]
        valid=[v for v in values if v is not None]
        result[key]={"适用数":len(valid),"不适用或未裁决":len(values)-len(valid),
                     "完整":sum(v==1 for v in valid),"部分":sum(v==.5 for v in valid),
                     "失败":sum(v==0 for v in valid),
                     "说明":"独立AI语义复核维度；不将维度均值替代端到端标签"}
    return result

def telemetry(folder):
    responses = [json.loads(line) for p in folder.glob("*/responses.jsonl")
                 for line in p.read_text(encoding="utf8").splitlines() if line]
    physical = [json.loads(line) for p in folder.glob("*/physical_attempts.jsonl")
                for line in p.read_text(encoding="utf8").splitlines() if line]
    ends = [r for r in physical if r["event"]=="finished"]
    costs=[]
    for r in responses:
        # Rates verified on 2026-11-05; applies to this dated benchmark only.
        local=datetime.fromisoformat(r["at"]).astimezone(timezone(timedelta(hours=8)))
        if local.date().isoformat()!="2026-11-05":
            raise ValueError("价格表仅核实本批日期；其他日期需要重新确认")
        peak=9<=local.hour<12 or 14<=local.hour<18
        hit,miss,out=(.04,2,8) if peak else (.02,1,4)
        u=r.get("usage",{})
        cost=((u.get("input_tokens",0)-u.get("cache_hit",0))*miss+
              u.get("cache_hit",0)*hit+u.get("output_tokens",0)*out)/1_000_000
        costs.append({"call_id":r["call_id"],"at":r["at"],"schema":r["schema"],
                      "valid":r["valid"],"usage":u,"seconds":r["seconds"],
                      "tariff":"高峰" if peak else "空闲","estimated_cny":cost,
                      "request_id":r.get("telemetry",{}).get("request_id")})
    schemas=defaultdict(lambda:{"requests":0,"valid":0})
    for r in responses:
        schemas[r["schema"]]["requests"]+=1
        schemas[r["schema"]]["valid"]+=bool(r["valid"])
    return {"logical_calls":len(responses),"physical_calls":len(ends),
            "http_200":sum(r.get("status_code")==200 for r in ends),
            "transport_retry_calls":sum(r.get("attempt",1)>1 for r in ends),
            "structured_valid":sum(r["valid"] for r in responses),"schemas":dict(schemas),
            "tokens":{k:sum(r.get("usage",{}).get(k,0) for r in responses)
                      for k in ("input_tokens","output_tokens","cache_hit")},
            "call_seconds_sum":sum(r["seconds"] for r in responses),
            "estimated_cny":sum(c["estimated_cny"] for c in costs),
            "cost_basis":{"source":PRICE_SOURCE,"checked":"2026-11-05","currency":"CNY",
                          "invoice_verified":False,"excludes":"独立Codex复核与计算机成本"},
            "calls":costs}

def main(root,output):
    if output.exists():
        raise ValueError("不覆盖已有汇总")
    original=read(root/"phase2/first20-calibrated-v2321.json")
    remaining=read(root/"phase2/remaining40-calibrated-v2321.json")
    rows=original+remaining
    expected={(m,f"{c}{i:02}") for m in ("local","deepseek") for c in "ABCDE" for i in range(1,7)}
    actual=[(r["mode"],r["id"]) for r in rows]
    if set(actual)!=expected or len(actual)!=len(set(actual)):
        raise ValueError("非恰好30题×两种模式，或含重复/保留题")
    for r in rows:
        if digest(Path(r["source"]["source"]))!=r["source"]["sha256"]:
            raise ValueError("原始观测发生变化")
    audit=read(root/"phase2/first-phase-evidence-hashes.json")
    changed=[name for name,h in audit.items() if digest(root/"phase1"/name)!=h]
    if changed:
        raise ValueError("第一期证据变化："+str(changed))
    metrics={"scorer":"v23.2.1","n":len(rows),"modes":{},"categories":{},"dimensions":{},
             "phase1_evidence_unchanged":{"checked_files":len(audit),"changed":[]}}
    detail=[]
    for mode in ("local","deepseek"):
        selected=[r for r in rows if r["mode"]==mode]
        durations=[r["facts"]["status"]["wall_s"] for r in selected]
        metrics["modes"][mode]={**counts(selected),"seconds_sum":sum(durations),
                                "seconds_mean":mean(durations),"seconds_median":median(durations),
                                "seconds_min":min(durations),"seconds_max":max(durations)}
        metrics["categories"][mode]={c:counts([r for r in selected if r["id"][0]==c]) for c in "ABCDE"}
        metrics["dimensions"][mode]=dimensions(selected)
    metrics["mechanical_checks"]={}
    for key in sorted({k for r in rows for k in r["facts"].get("checks",{})}):
        values=[r["facts"].get("checks",{}).get(key) for r in rows]
        metrics["mechanical_checks"][key]={"true":sum(v is True for v in values),
                                         "false":sum(v is False for v in values),
                                         "not_applicable":sum(v is None for v in values)}
    metrics["new_runs"]=sum(len(r["facts"].get("new_runs",[])) for r in rows)
    metrics["new_plans"]={m:sum(len(r["facts"].get("new_plans",[])) for r in rows if r["mode"]==m)
                          for m in ("local","deepseek")}
    metrics["telemetry"]={phase:telemetry(root/phase/"deepseek") for phase in ("phase1","phase2")}
    advice=read(root/"phase2/review/advice30-review.json")
    assert len(advice)==30 and {r["id"] for r in advice}=={f"{c}{i:02}" for c in "ABCDE" for i in range(1,7)}
    metrics["independent_advice"]=dict(Counter(r["label"] for r in advice))
    metrics["phase1_comparison"]=[]
    for mode in ("local","deepseek"):
        old={r["id"]:r for r in read(root/"phase1"/mode/"scores.json")}
        for r in original:
            if r["mode"]==mode:
                metrics["phase1_comparison"].append({"id":r["id"],"mode":mode,
                                                     "original":old[r["id"]]["label"],
                                                     "calibrated":r["label"],"reason":r["review"]["reason"]})
    for r in rows:
        folder=Path(r["source"]["source"]).parent
        o=read(folder/"observation.json")
        p=folder/"responses.jsonl"
        calls=[json.loads(l) for l in p.read_text(encoding="utf8").splitlines()] if p.exists() else []
        detail.append({"id":r["id"],"mode":r["mode"],"label":r["label"],"scorer":r["scorer"],
                       "code_commit":o["git"],"source":r["source"],
                       "seconds_wall":r["facts"]["status"]["wall_s"],"calls":len(calls),
                       "structured_valid":sum(c["valid"] for c in calls),
                       "model_config":calls[0].get("config") if calls else None,
                       "model_call_seconds":sum(c["seconds"] for c in calls),
                       "tokens":{k:sum(c.get("usage",{}).get(k,0) for c in calls)
                                 for k in ("input_tokens","output_tokens","cache_hit")},
                       "schema_validity":[{"call_id":c["call_id"],"schema":c["schema"],"valid":c["valid"]} for c in calls],
                       "estimated_cny":sum(c["estimated_cny"] for batch in metrics["telemetry"].values()
                                           for c in batch["calls"] if c["call_id"] in {v["call_id"] for v in calls}),
                       "answer":r["facts"].get("answer",{}),
                       "additional_visible":r["facts"].get("visible_additional",{}),
                       "target":r["facts"].get("target",{}),"checks":r["facts"].get("checks",{}),
                       "review":r["review"],"errors":o["errors"],
                       "approvals":o["approvals"],"runs":o["runs"],"operator":o["operator"]})
    output.mkdir(parents=True)
    for name,obj in (("metrics.json",metrics),("attempts60.json",detail),("advice30.json",advice)):
        (output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    lines=["# 30题开发集逐题结果（评分 v23.2.1）","",
           "每模式每题首次一次；部分与待人工复核均不计正确处理。不是浏览器或真人测试。","",
           "|题号|本地|DeepSeek|本地秒数|DeepSeek秒数|模型请求数|","|---|---|---|---:|---:|---:|"]
    for case in sorted({r["id"] for r in detail}):
        a=next(r for r in detail if r["id"]==case and r["mode"]=="local")
        b=next(r for r in detail if r["id"]==case and r["mode"]=="deepseek")
        lines.append(f"|{case}|{a['label']}|{b['label']}|{a['seconds_wall']:.3f}|{b['seconds_wall']:.3f}|{b['calls']}|")
    lines+=["","## 逐次判定与原文依据",""]
    for r in sorted(detail,key=lambda r:(r["id"],r["mode"])):
        review=r["review"]
        lines += [f"### {r['id']} · {r['mode']} · {r['label']}","",review["reason"],"",
                  "证据："+r["source"]["source"]+"；SHA-256："+r["source"]["sha256"],""]
        for q in review.get("quotes",[])[:3]:
            lines += [f"> {q['path']}：{q['quote']}",""]
    (output/"逐题结果.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print(json.dumps({k:metrics[k] for k in ("modes","categories","mechanical_checks","new_runs","new_plans","independent_advice","phase1_evidence_unchanged")},ensure_ascii=False,indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("evidence_root",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    main(args.evidence_root,args.output)

