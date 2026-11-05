"""Post-close controller. Reads isolated workspaces in SQLite read-only mode."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse, parse_qs


def read(p):return json.loads(p.read_text(encoding="utf-8-sig"))
def has(s,*terms):return all(t in s for t in terms)
def mean_label(s,v):
    return any(math.isclose(float(x),v,abs_tol=.00051) for x in
               re.findall(r"均值(?:为)?\s*(-?\d+(?:\.\d+)?)",s))

def close(folder):
    r=read(folder/"result.json"); init=read(folder/"initial.json")
    w=folder/"workspace"; c=sqlite3.connect((w/"research.sqlite3").resolve().as_uri()+"?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    def rows(query,*args):return [dict(x) for x in c.execute(query,args)]
    tables={x["name"] for x in rows("select name from sqlite_master where type='table'")}
    plans={p["id"]:p for p in rows("select * from assistant_plans")} if "assistant_plans" in tables else {}
    runs={}; receipts=[]; evidence={}
    if "workflow_approvals" in tables:
        receipts=[json.loads(x["body"]) for x in rows("select body from workflow_approvals where revoked=0")]
    if plans:
        for t in rows("select * from assistant_tasks where state='completed'"):
            result=json.loads(t["result"]); rid=result["run_id"];p=plans[t["plan_id"]]
            runs[rid]={**result,"session":p["session_id"],"version":p["version"],"pid":p["id"]}
            if result["kind"]=="exploration":
                f=rows("select path,sha from exploration_runs where run_id=?",rid)[0];path=w/f["path"]
                assert hashlib.sha256(path.read_bytes()).hexdigest()==f["sha"]
            else:path=Path(rows("select result_bundle_path from analysis_runs where run_id=?",rid)[0]["result_bundle_path"])
            assert path.resolve().is_relative_to(w.resolve())
            evidence[rid]=read(path)
    def matched(rid):
        run=runs[rid];p=plans[run["pid"]]
        for a in receipts:
            if a["session_id"]!=p["session_id"] or a["plan_id"]!=p["id"] or not(p["sha"]==a["plan_sha"]==run["plan_sha"]):continue
            if a["data"]["frame_sha"]!=run["contract"]["data_fingerprint"]:continue
            flow=rows("select request from workflow_flows where id=? and plan_id=?",a["flow_id"],p["id"])
            if not flow:continue
            req=json.loads(flow[0]["request"])
            if req["data"]!=a["data"] or req["contract_ref"]!=a["contract_ref"]:continue
            if rows("select seq from workflow_events where flow_id=? and node='execute_plan' and status='started' and created>=?",a["flow_id"],a["approved_at"]):return req
        return {}
    checks={"浏览器到达路线终点":r["state"]=="路线结束待核验"}
    case=r["case"]; end=next(folder.glob("*-end.txt")).read_text(encoding="utf8")
    duration=None; drift=None; answer=r.get("answer","");papers=r.get("papers",{})
    if case=="N01":
        checks.update(空导入页=has(end,"导入分析表","创建任务并检查数据"),没有创建研究=not rows("select id from assistant_sessions") and not runs)
    if case=="N03":
        checks.update(程序与声明分开=has(end,"程序核对","研究声明与识别限制","待人工审核","分组如何产生","两周","未发邮件","男装邮件","blog.minethatdata.com"),
                      仍待审核=len(plans)==1 and list(plans.values())[0]["state"]=="candidate" and not runs and not receipts)
    if case=="N05":
        t=init["target"];rid=t["run"];req=matched(rid);rates=evidence[rid]["evidence"]["rate_contrast"];a,b=init["expected"]
        checks.update(所选任务和运行=parse_qs(urlparse(r["end_url"]).query).get("assistant")==[t["sid"]] and papers.get("selected",{}).get("run")==rid,
                      访问指标与估计=bool(req) and req["data"]==t["binding"] and evidence[rid]["spec"]["outcome"]=="visit" and math.isclose(rates["control_rate"],a) and math.isclose(rates["treated_rate"],b),
                      报告口径=has(papers.get("selected",{}).get("body",""),rid,"男装邮件","未发邮件","两周","7.66","百分点"),
                      用户可见答复=has(answer,rid,"男装邮件","未发邮件","两周","10.62","18.28","7.66 个百分点"),
                      历史无新运行=set(runs)=={rid,init["distractor"]["run"]} and len(plans)==len(receipts)==2 and all(matched(i) for i in runs))
        drift=rid not in r.get("history_text","")
    if case in ("N06","N07"):
        t=init["target"];rid=papers.get("new",{}).get("run");old=t["run"]
        body=papers.get("new",{}).get("body","");expected=init["expected"]
        fld=init["field"];unit="人" if case=="N06" else "单"
        if rid in runs:
            v=runs[rid];duration=v["seconds"];req=matched(rid);scope=req.get("analysis_scope",{})
            summary=evidence[rid]["summary"]["numeric"];row=next((n for n in summary if n["field"]==fld),{})
            checks.update(审批及版本=bool(req) and v["session"]==t["sid"] and v["version"]==2 and v["pid"]!=t["plan"] and req["data"]==t["binding"],
                          指标与数值=scope.get("outcome")==fld and row.get("finite_n")==init["n"] and math.isclose(row.get("mean",1e30),expected),
                          新报告字段单位=has(body,rid,fld,unit) and (mean_label(body,expected) or f"{expected:.3f}\n均值" in body),
                          观察期=(scope.get("covered_days")==5 and [scope.get("start"),scope.get("end")]==init["window"] and has(body,*init["window"])) if case=="N07" else "当前表全部日期" in body,
                          最终答复=has(answer,rid,fld,unit) and mean_label(answer,expected) and (has(answer,*init["window"]) if case=="N07" else "当前表全部日期" in answer),
                          刷新相同=papers.get("restored")==papers.get("new"))
        else:checks["新运行"]=False
        old_report=papers.get("original",{})
        checks.update(旧记录=old_report.get("run")==old and old_report==papers.get("reopened") and matched(old).get("data")==t["binding"] and plans[t["plan"]]["sha"]==t["sha"] and has(old_report.get("body",""),"orders","当前表全部日期") and mean_label(old_report.get("body",""),init["old_mean"]),
                      无额外运行=len(runs)==len(receipts)==len(plans)==2)
    model=len(rows("select id from assistant_events where kind='model_request'")) if "assistant_events" in tables else 0
    c.close()
    return dict(case=case,passed=all(checks.values()),checks=checks,history_intermediate_mismatch=drift,runs=list(runs),
                receipt_count=len(receipts),analysis_step_s=duration,model_requests=model,
                dispatched=sum(x["ok"] for x in r["actions"]),attempted=len(r["actions"]),turns=r["turns"],
                seconds=r.get("seconds"),explicit_wait_s=sum(x["seconds"] for x in r["waits"]),started=r.get("started"),ended=r["ended"],
                browser_events=read(folder/"browser-events.json"),failure=r.get("failure") or r.get("infrastructure"))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",type=Path);a=p.parse_args()
    results=[close(a.folder/case) for case in ["N01","N03","N05","N06","N07"]]
    with (a.folder/"close.json").open("x",encoding="utf8") as f:json.dump(results,f,indent=2,ensure_ascii=False)
    for x in results:print(x["case"],x["passed"],[k for k,v in x["checks"].items() if not v])

