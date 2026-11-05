"""Execute development tasks in separate processes. This runner never opens answer keys."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from datasets import ROOT, DATA, TABLES

PILOT = tuple(f"{category}{n:02}" for category in "ABCDE" for n in (1,2))


def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write(p,data):
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str,allow_nan=False)+"\n",encoding="utf8")


def worker(folder,case,mode):
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace, DesignError
    from causalops.evaluation.v12.capture import Advice
    from causalops.evaluation.v13.capture import Metered

    class Client(Metered):
        def _content(self,response):
            text,usage=super()._content(response)
            hit=usage.get("input_tokens_details",{}).get("cached_tokens")
            if isinstance(hit,int):
                self.usage["cache_hit"]=hit
            return text,usage

    if Path(os.environ["CAUSALOPS_HOME"]).resolve() != (folder/"workspace").resolve():
        raise ValueError("工作区隔离失败")
    task=next(t for t in read(ROOT/"development_tasks.json") if t["id"]==case)
    name=task["dataset"]
    contract=read(DATA/(name+".json"))
    question=TABLES[name][0]+"\n"+task["request"]
    out=dict(id=case,mode=mode,started=datetime.now(timezone.utc).isoformat(),git=subprocess.check_output(
        ["git","rev-parse","HEAD"],text=True).strip(),setup_flows=[],before_runs=[],flows=[],runs=[],approvals=[],
        errors=[],probe={},advice=None,operator=[])
    begin=time.perf_counter()
    w=AssistantWorkspace(GeneralWorkspace(folder/"workspace"))
    service=ResearchService(w)
    sid=service.create_task(payload=(DATA/(name+".csv")).read_bytes(),name=name+".csv",title=case)
    out["sid"]=sid
    op=task["operation"]
    model=None

    def approve(f,dispatch,required_metric):
        if f["status"]!="awaiting_review" or not f.get("plan_id"):
            return False
        plan=w.get_plan(f["plan_id"])
        steps=plan["plan"]["steps"]
        if not steps or any(t["config"]["method"]!="descriptive" or required_metric not in
                t["config"].get("numeric",[]) for t in steps):
            out["operator"].append("拒绝与操作者授权范围不符的计划")
            return False
        out["operator"].append({"approve":plan["id"],"sha":plan["sha"],"dispatch":dispatch})
        service.review(f["id"],accept=True,expected_plan_id=plan["id"],expected_plan_sha=plan["sha"],
                       expected_data_sha=f["request"]["data"]["frame_sha"],human_confirmed=True,
                       use_contract_facts=True,dispatch=dispatch)
        return True

    try:
        service.contracts.save(sid,contract,expected_sha=None,human_confirmed=True)
        old=None
        if op in ("history","pending_read","stale","mixed","revision","cancel"):
            old=service.start(sid,"生成 "+contract["outcome"]+" 的描述统计分布方案。",mode="plan")
            if op in ("history","stale","mixed","revision"):
                if not approve(old,op!="stale",contract["outcome"]):
                    raise ValueError("前置方案未达到指定起点")
            elif old["status"]!="awaiting_review":
                raise ValueError("缺少已登记候选方案")
        out["setup_flows"]=[f["id"] for f in service.flows(sid)]
        out["before_runs"]=[r["run_id"] for r in w.completed_runs(sid)]
        if old:
            out["before_plan"]=[old["plan_id"],w.get_plan(old["plan_id"])["sha"]]
        if op=="stale":
            ref=service.contracts.latest(sid)
            revised=dict(ref["body"])
            revised["research"]={**revised["research"],"inclusion":"仅纳入营业泊位日（open_hours > 0）"}
            service.contracts.save(sid,revised,expected_sha=ref["sha"],human_confirmed=True)
        if mode=="deepseek":
            model=Client(os.environ["DEEPSEEK_API_KEY"],folder)
            service.model=model
            w.consent(sid,True,model.provider_config)
            try:
                out["advice"]=model.complete_json(system_instruction="请独立给出研究建议。action 可用 execute、revise、clarify、block、explain。methods 和 fields 仅填写适用项。说明必要条件与理由。你没有批准或执行权限。",
                    user_payload=dict(question=question,state=task["initial_state"],fields=list(w.ws.load_upload(
                    service.data_binding(sid)["upload_id"]).columns),dictionary=service.contracts.latest(sid)["body"]),
                    output_schema=Advice.model_json_schema())
            except Exception as exc:
                out["errors"].append("独立建议："+type(exc).__name__)
        params={"parent_flow_id":old["id"]} if old else {}
        if op=="history":
            params["run_ids"]=out["before_runs"]
        if op=="stale":
            try:
                service.gateway.execute(old["id"])
                out["probe"]["stale"]="执行入口放行"
            except DesignError as exc:
                out["probe"]["stale_refusal"]=str(exc)
        if op=="resume":
            f=service.begin(sid,"请为 "+contract["outcome"]+" 制定描述统计方案，等待我审核。")
            service.cancel(f["id"],human_confirmed=True)
            try:
                service.continue_flow(f["id"])
            except Exception as exc:
                out["probe"]["stopped"]=type(exc).__name__
            out["probe"]["while_stopped"]=len(w.completed_runs(sid))
            out["operator"].append({"resume_request":question,"flow":f["id"]})
            f=service.resume(f["id"],human_confirmed=True)
        else:
            if op=="cancel":
                service.cancel(old["id"],human_confirmed=True)
            f=service.start(sid,question,**params)
        out["target"]=f["id"]
        if op=="compute" and approve(f,True,contract["outcome"]):
            ref=next(iter(w.completed_runs(sid)),None)
            if ref:
                follow=service.start(sid,"请解释刚保存报告中目标字段的样本均值、单位和运行来源，不要重新计算。",
                                     run_ids=[ref["run_id"]],parent_flow_id=f["id"])
                out["delivery"]=follow["id"]
    except Exception as exc:
        msg=str(exc)
        secret=os.environ.get("DEEPSEEK_API_KEY")
        out["errors"].append(type(exc).__name__+"："+(msg.replace(secret,"[已移除]") if secret else msg)[:500])
    finally:
        if model:
            model.close()
        for f in reversed(service.flows(sid)):
            get=lambda key:service.output(f["id"],key) or {}
            plan=w.get_plan(f["plan_id"]) if f["plan_id"] else {}
            out["flows"].append(dict(id=f["id"],plan=f["plan_id"],plan_sha=plan.get("sha"),version=plan.get("version"),
                route=get("route"),methods=[step["config"] for step in plan.get("plan",{}).get("steps",[])],
                status=f["status"],cancelled=bool(f.get("cancel_requested")),answer=get("answer"),prior_answer=get("prior_answer"),readiness=get("readiness"),events=service.events(f["id"]),
                data=f["request"]["data"]["frame_sha"]))
        with service.ws.connection() as con:
            out["approvals"]=[json.loads(row[0]) for row in con.execute("select body from workflow_approvals")]
        for ref in w.completed_runs(sid):
            record={k:ref[k] for k in ("plan_id","plan_sha","run_id","method")}
            record["data"]=ref["contract"]["data_fingerprint"]
            if ref["kind"]=="exploration":
                record["stats"]=w.ex.load(ref["run_id"])["summary"]["numeric"]
            out["runs"].append(record)
        out["seconds"]=round(time.perf_counter()-begin,3)
        write(folder/"observation.json",out)


def launch(root,case,mode,key):
    folder=root/case
    folder.mkdir()
    env=dict(os.environ, CAUSALOPS_HOME=str(folder/"workspace"))
    env.pop("DEEPSEEK_API_KEY",None)
    if mode=="deepseek":
        env["DEEPSEEK_API_KEY"]=key
    t=time.perf_counter()
    try:
        with (folder/"worker.log").open("xb") as log:
            res=subprocess.run([sys.executable,__file__,str(folder),mode,"--worker",case],env=env,
                               stdout=log,stderr=subprocess.STDOUT,timeout=420)
        status="完成" if res.returncode==0 and (folder/"observation.json").exists() else "运行器失败"
    except subprocess.TimeoutExpired:
        status="超时"
    write(folder/"status.json",{"case":case,"mode":mode,"status":status,"wall_s":round(time.perf_counter()-t,3)})
    print(case,status,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    p.add_argument("mode",choices=["local","deepseek"])
    p.add_argument("--worker",choices=PILOT)
    args=p.parse_args()
    if args.worker:
        worker(args.folder,args.worker,args.mode)
    else:
        if args.folder.resolve().is_relative_to(ROOT.parents[2]):
            p.error("请选择仓库外的全新证据目录")
        key=(os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("Official key (hidden): ")) if args.mode=="deepseek" else ""
        args.folder.mkdir(parents=True,exist_ok=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda c:launch(args.folder,c,args.mode,key),PILOT))
