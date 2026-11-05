"""Compare development reruns with frozen second-phase scores; never reads holdouts."""
import argparse,json,hashlib
from pathlib import Path
from statistics import mean,median
from collections import Counter
from summarize_phase2 import counts,dimensions,telemetry,read,digest

def main(root,current_name='phase3',previous_name=None):
    current=root/current_name; out=current/"final"
    rows=read(current/"calibrated-v2321.json")
    previous=read(root/previous_name/"calibrated-v2321.json") if previous_name else read(root/"phase2/first20-calibrated-v2321.json")+read(root/"phase2/remaining40-calibrated-v2321.json")
    expected={(m,f"{c}{i:02}") for m in ("local","deepseek") for c in "ABCDE" for i in range(1,7)}
    for batch in (rows,previous):
        assert len(batch)==60 and {(r["mode"],r["id"]) for r in batch}==expected
        assert all(digest(Path(r["source"]["source"]))==r["source"]["sha256"] for r in batch)
        assert all(r["scorer"]=="v23.2.1" for r in batch)
    protected=read(current/"prior-evidence-manifest.json")
    changed=[p for p,h in protected.items() if digest(root/p)!=h]
    assert not changed,changed
    if out.exists():raise ValueError("不覆盖既有汇总")
    metrics={"scorer":"v23.2.1","n":60,"attempts_per_task_per_mode":1,"holdouts_run":0,
             "historical_evidence":{"checked":len(protected),"changed":changed},
             "modes":{},"categories":{},"dimensions":{},"checks":{}}
    for mode in ("local","deepseek"):
        selected=[r for r in rows if r["mode"]==mode]
        before=[r for r in previous if r["mode"]==mode]
        seconds=[r["facts"]["status"]["wall_s"] for r in selected]
        metrics["modes"][mode]={"before":counts(before),"after":counts(selected),
          "seconds_sum":sum(seconds),"seconds_mean":mean(seconds),"seconds_median":median(seconds),
          "correct_clarify":sum(r["label"] in ("完整","正确阻断") and r["facts"]["target"].get("route",{}).get("route")=="clarify" for r in selected)}
        metrics["categories"][mode]={c:counts([r for r in selected if r["id"][0]==c]) for c in "ABCDE"}
        metrics["dimensions"][mode]=dimensions(selected)
        metrics["checks"][mode]={}
        for key in sorted({k for r in selected for k in r["facts"]["checks"]}):
            vals=[r["facts"]["checks"].get(key) for r in selected]
            metrics["checks"][mode][key]={"true":sum(v is True for v in vals),"false":sum(v is False for v in vals),"na":sum(v is None for v in vals)}
    metrics["telemetry"]=telemetry(current/"deepseek")
    advice=read(current/"review/advice30-review.json")
    assert len(advice)==30
    metrics["independent_advice"]={"labels":dict(Counter(a["label"] for a in advice)),
                                 "not_fed_to_workflow":True}
    old={(r["mode"],r["id"]):r for r in previous}
    comparison=[];details=[]
    for r in rows:
        folder=Path(r["source"]["source"]).parent
        o=read(folder/"observation.json")
        comparison.append({"id":r["id"],"mode":r["mode"],"before":old[r["mode"],r["id"]]["label"],"after":r["label"]})
        details.append({"id":r["id"],"mode":r["mode"],"label":r["label"],"scorer":r["scorer"],
          "source":r["source"],"product_commit":o["git"],"checks":r["facts"]["checks"],
          "answer":r["facts"]["answer"],"target":r["facts"]["target"],
          "numeric":r["facts"]["numeric"],"additional_visible":r["facts"]["visible_additional"],
          "new_plans":r["facts"]["new_plans"],"new_runs":r["facts"]["new_runs"],
          "approvals":o["approvals"],"errors":o["errors"],"seconds_wall":r["facts"]["status"]["wall_s"],
          "review":r["review"],"issues":r["issues"]})
    metrics["comparison"]=comparison
    out.mkdir()
    for name,obj in (("metrics.json",metrics),("attempts60.json",details),("advice30.json",advice)):
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf8")
    lines=["# 第三期30题开发集复测明细","","每题每模式首次一次；v23.2.1未变。部分、失败、待人工复核均不计正确处理。独立AI语义复核不是真人研究专家审查。","","|题号|本地：前→后|DeepSeek：前→后|本地秒|模型秒|","|---|---|---|---:|---:|"]
    for case in sorted({r["id"] for r in rows}):
        a=next(r for r in details if r["mode"]=="local" and r["id"]==case)
        b=next(r for r in details if r["mode"]=="deepseek" and r["id"]==case)
        lines.append(f'|{case}|{old["local",case]["label"]} → {a["label"]}|{old["deepseek",case]["label"]} → {b["label"]}|{a["seconds_wall"]:.3f}|{b["seconds_wall"]:.3f}|')
    lines+=["","## 逐次复核",""]
    for r in sorted(details,key=lambda x:(x["id"],x["mode"])):
        rev=r["review"]
        lines += [f'### {r["id"]} · {r["mode"]} · {r["label"]}',"",rev["reason"],"",
                  "未满足："+("；".join(rev.get("missing",[])) or "无"),"",
                  "证据文件："+r["source"]["source"],"SHA-256："+r["source"]["sha256"],"",
                  "**最终答复原文**","",r["answer"].get("text","（答复正文为空；候选方案/前置答复另见运行记录，不视为不存在。）"),""]
    (out/"CASES.md").write_text("\n".join(lines).rstrip()+"\n",encoding="utf8")
    print(json.dumps(metrics["modes"],ensure_ascii=False,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path)
    p.add_argument("--current",default="phase3");p.add_argument("--previous")
    args=p.parse_args();main(args.root,args.current,args.previous)
