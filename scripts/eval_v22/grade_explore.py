"""Post-trial controller. Never import this module from the page-only decision client."""
import argparse
import json
import math
import re
import sqlite3
from pathlib import Path

from close_fixed import read


def grade(folder):
    trace = read(folder / "interaction.json")
    fixture = read(folder / "initial.json")
    pages = [read(p) for p in sorted(folder.glob("page-*.json"))]
    root = folder / "workspace"
    db = sqlite3.connect((root / "research.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
    def rows(table):
        return list(db.execute("select * from " + table)) if table in tables else []
    plans = {p["id"]: p for p in rows("assistant_plans")}
    runs = {json.loads(t["result"])["run_id"]: t for t in rows("assistant_tasks") if t["state"] == "completed"}
    receipts = [json.loads(a["body"]) for a in rows("workflow_approvals") if not a["revoked"]]
    def approved(rid):
        task = runs[rid]
        result = json.loads(task["result"])
        plan = plans[task["plan_id"]]
        return any(a["session_id"] == plan["session_id"] and a["plan_id"] == plan["id"]
                   and a["plan_sha"] == plan["sha"] == result["plan_sha"]
                   and a["data"]["frame_sha"] == result["contract"]["data_fingerprint"]
                   and db.execute("select 1 from workflow_events where flow_id=? and node='execute_plan' and status='started' and created>=?",
                                  (a["flow_id"], a["approved_at"])).fetchone()
                   for a in receipts)
    final = trace.get("final", "")
    turns = trace["turns"]
    actions = [e for e in turns if e.get("decision", {}).get("action") not in (None, "wait", "done", "abandon")]
    dispatched = [e for e in actions if e["ok"]]
    keys = [(e["decision"]["action"], e["control"], e["decision"]["value"]) for e in actions]
    telem = [e["telemetry"] for e in turns]
    target = fixture.get("target", {})
    old = target.get("run")
    case = trace["case"]
    detail = {}
    if case == "N05":
        evidence = next(x for x in rows("analysis_runs") if x["run_id"] == old)
        path = Path(evidence["result_bundle_path"]).resolve()
        assert path.is_relative_to(root.resolve())
        rates = read(path)["evidence"]["rate_contrast"]
        a,b = fixture["expected"]
        diff = (b-a)*100
        frames = read(folder/"history-frames.json")
        number_ok = any(abs(float(v)-diff) <= .0051 for v in re.findall(r"(\d+(?:\.\d+)?)\s*个百分点", final))
        checks = dict(evidence=approved(old) and math.isclose(a,rates["control_rate"]) and math.isclose(b,rates["treated_rate"]),
                      selected=any(f["source"]==old and f["rid"]==old and "访问率" in f["task"] and f["metric"]=="访问率" and old[:8] in f["choice"] for f in frames),
                      answers=old in final and number_ok and all(s in final for s in ("两周","男装","未发","访问率")),
                      read_only=set(runs)=={old,fixture["distractor"]["run"]} and len(plans)==len(receipts)==2)
        detail["wrong_bindings"] = sum(1 for f in frames if f["metric"] and f["rid"] != fixture["target" if f["metric"]=="访问率" else "distractor"]["run"])
    elif case == "N06":
        new = [rid for rid in runs if rid!=old]
        checks = dict(old_preserved=old in runs and approved(old) and plans[target["plan"]]["sha"]==target["sha"],
                      candidate=any(p["version"]>1 and p["session_id"]==target["sid"] for p in plans.values()),
                      new_approved_run=any(approved(rid) for rid in new))
        reports = [p.get("report", "") for p in pages]
        checks.update(report_review=False, restored=False, reopened_old=False, final_answer=False)
        for rid in new:
            result = json.loads(runs[rid]["result"])
            plan = plans[runs[rid]["plan_id"]]
            visible = [i for i,report in enumerate(reports) if rid in report and fixture["field"] in report
                       and "当前表全部日期" in report and f'{fixture["expected"]:.3f}' in report]
            checks["report_review"] |= bool(visible and plan["version"] == 2 and plan["session_id"] == target["sid"]
                                            and result["plan_sha"] == plan["sha"] and approved(rid))
            reloaded = [e["i"] for e in dispatched if e["decision"]["action"] == "reload" and e["i"] in visible]
            restored = [i for i in visible if any(j < i for j in reloaded)]
            checks["restored"] |= bool(restored)
            checks["reopened_old"] |= any(old in report and "orders" in report for i,report in enumerate(reports)
                                           if any(j < i for j in restored))
            checks["final_answer"] |= all(x in final for x in (rid, old, str(fixture["old_mean"]), "访客", "订单"))
        detail.update(new_runs=new, manual_review_required=bool(new))
    else:
        rejected = any("列名为空或重复" in p["text"] and any("创建任务" in c["name"] and c["disabled"] for c in p["controls"]) for p in pages)
        sessions = rows("assistant_sessions")
        sid = sessions[0]["id"] if len(sessions)==1 else None
        at_task = lambda p: sid and sid in p["location"] and re.search(r"(?:2\s*条记录|全表\s*2\s*行)",p["text"])
        restored = any(e["decision"]["action"]=="reload" and e["ok"] and at_task(pages[e["i"]]) and any(at_task(p) for p in pages[e["i"]+1:]) for e in actions)
        checks=dict(refused=rejected,created=bool(any(at_task(p) for p in pages)),restored=restored,no_statistics=not runs)
    db.close()
    completed = all(checks.values())
    return dict(id=folder.name,checks=checks,detail=detail,completed=completed,correct_stop=completed and trace["stop"]=="done",
                stop=trace["stop"],seconds=trace["seconds"],attempted=len(actions),dispatched=len(dispatched),
                repeats=len(keys)-len(set(keys)),invalid=len(actions)-len(dispatched),
                chats=sum(e["decision"]["action"]=="send" or e["control"]=="Send message" for e in dispatched),
                help=sum("使用说明" in (e["control"] or "") for e in dispatched),interventions=trace["interventions"],
                provider_calls=len(telem),http200=sum(t.get("status_code")==200 for t in telem),
                schema_ok=sum("decision" in e for e in turns),input_tokens=sum(t.get("input_tokens") or 0 for t in telem),
                output_tokens=sum(t.get("output_tokens") or 0 for t in telem),
                run_ids=list(runs),approval_count=len(receipts),error=trace.get("error"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    results = [grade(p) for p in sorted(args.root.glob("N*-*")) if p.is_dir()]
    with (args.root/"grades-reviewed.json").open("x", encoding="utf8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    for r in results:
        print(r["id"],r["checks"],r["dispatched"],r["repeats"],r["invalid"],r["http200"])
