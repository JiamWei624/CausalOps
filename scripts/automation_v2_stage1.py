"""Restricted public-case service entry; no UI, free-form planner or model calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace


def main():
    parser=argparse.ArgumentParser(description="CausalOps 自动化V2：受限Hillstrom五步执行与核查恢复")
    parser.add_argument("--workspace",type=Path,required=True,help="独立本地工作区")
    sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("create",help="导入已核验公开包并编译候选，不批准或执行")
    create.add_argument("--archive",type=Path,required=True)
    create.add_argument("--request-id",required=True)
    create.add_argument("--confirm-source",action="store_true")
    approve=sub.add_parser("approve",help="人工核对输出的完整计划后批准一次")
    approve.add_argument("--task",required=True)
    approve.add_argument("--expected-plan-sha",required=True)
    approve.add_argument("--confirm-review",action="store_true")
    for name in ("run","show","export","pause","cancel","resume","budget","advance"):
        p=sub.add_parser(name);p.add_argument("--task",required=True)
        if name=="export":p.add_argument("--output",type=Path,required=True)
        if name in ("pause","cancel","resume"):p.add_argument("--confirm-control",action="store_true")
        if name=="advance":p.add_argument("--step",choices=["S01","S02","S03","S04","S05"])
    args=parser.parse_args()
    service=ResearchService(AssistantWorkspace(GeneralWorkspace(args.workspace)))
    co=service.automation_v2()
    if args.command=="create":
        result=co.create_hillstrom(args.archive.read_bytes(),request_id=args.request_id,source_confirmed=args.confirm_source)
    elif args.command=="approve":
        result=co.approve(args.task,expected_plan_sha=args.expected_plan_sha,human_confirmed=args.confirm_review)
    elif args.command=="run":
        result=co.run(args.task)
    elif args.command in ("pause","cancel","resume"):
        result=getattr(co,args.command)(args.task,human_confirmed=args.confirm_control)
    elif args.command=="budget":
        result=co.budget(args.task)
    elif args.command=="advance":
        result=co.advance(args.task,expected_step=args.step)
    else:
        result={"task":co.task(args.task),"steps":co.steps(args.task),"events":co.events(args.task),"budget":co.budget(args.task)}
        if result["task"]["status"]=="completed":result["report"]=co.report(args.task)
        if args.command=="export":
            args.output.mkdir(parents=True,exist_ok=True)
            # Exclusive creation avoids overwriting earlier acceptance evidence.
            with (args.output/"execution.json").open("x",encoding="utf8") as f:
                json.dump(result,f,ensure_ascii=False,indent=2)
            if "report" in result:
                with (args.output/"report.md").open("x",encoding="utf8") as f:
                    f.write("# 受限自动化研究报告\n\n"+result["report"]["text"]+"\n")
            result={"exported":str(args.output),"status":result["task"]["status"]}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
