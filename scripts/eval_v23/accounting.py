"""Summarize already-scored runs. Physical requests, advice and workflow calls stay distinct."""
import argparse
from collections import Counter
import json
from statistics import median
from pathlib import Path


def lines(p):
    return [json.loads(s) for s in p.read_text(encoding="utf8").splitlines()] if p.exists() else []


def group(folder):
    scores=json.loads((folder/"scores.json").read_text(encoding="utf8"))
    responses=[]
    physical=[]
    for s in scores:
        case=folder/s["id"]
        responses.extend(lines(case/"responses.jsonl"))
        physical.extend(lines(case/"physical_attempts.jsonl"))
    finished=[p for p in physical if p["event"]=="finished"]
    starts=[p for p in physical if p["event"]=="started"]
    usage=[r["usage"] for r in responses if r["usage"].get("input_tokens") is not None
           and r["usage"].get("output_tokens") is not None]
    inp=sum(x["input_tokens"] for x in usage)
    out=sum(x["output_tokens"] for x in usage)
    hit=sum(x.get("cache_hit",0) for x in usage)
    unknown=sum(x["input_tokens"] for x in usage if "cache_hit" not in x)
    # Price bounds over measured receipts only; neither endpoint is an account bill.
    low=((hit+unknown)*.02+(inp-hit-unknown)+out*4)/1e6
    high=(hit*.04+(inp-hit)*2+out*8)/1e6
    dimension_names=sorted({name for s in scores for name in s["dimensions"]})
    dimensions={}
    for name in dimension_names:
        valid=[s["dimensions"][name] for s in scores if s["dimensions"].get(name) is not None]
        dimensions[name]=[sum(valid),len(valid)]
    return {"尝试":len(scores),"状态":dict(Counter(s["label"] for s in scores)),"维度通过与适用数":dimensions,
            "墙钟秒合计":sum(s["wall_s"] for s in scores),"墙钟秒中位数":median(s["wall_s"] for s in scores),
            "物理请求":len(starts),"有终态请求":len(finished),"HTTP200":sum(e.get("status_code")==200 for e in finished),
            "物理耗时秒合计":sum(e.get("latency_ms",0) for e in finished)/1000,
            "结构有效独立建议":[sum(r["valid"] for r in responses if r["schema"]=="Advice"),sum(r["schema"]=="Advice" for r in responses)],
            "结构有效工作流输出":[sum(r["valid"] for r in responses if r["schema"]!="Advice"),sum(r["schema"]!="Advice" for r in responses)],
            "回执数":len(usage),"输入token":inp,"输出token":out,"确认缓存命中":hit,"缓存未知输入":unknown,
            "计价下限与上限_元":[low,high],"请求时刻UTC":[starts[0]["at"] if starts else None,max((e["at"] for e in finished),default=None)],
            "门禁前建议动作":[sum(s["advice_checks"]["动作"] for s in scores if s.get("advice_checks")),sum(bool(s.get("advice_checks")) for s in scores)],
            "门禁前必要条件全命中":[sum(all(s["advice_checks"]["必要条件命中"]) for s in scores if s.get("advice_checks")),sum(bool(s.get("advice_checks")) for s in scores)]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    a=p.parse_args()
    data={m:group(a.root/m) for m in ("local","deepseek")}
    with (a.root/"metrics.json").open("x",encoding="utf8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)
    print(json.dumps(data,ensure_ascii=False))
