"""Summarize model attempts without changing the frozen browser endpoint grader."""
import argparse
import json
from collections import Counter
from pathlib import Path

from close_fixed import read
from grade_explore import grade

def grade_batch(directory):
    rows=[]
    for folder in sorted(directory.glob("N*-*")):
        trace=read(folder/"interaction.json")
        if trace.get("started"):
            rows.append(grade(folder))
        else:
            assert not trace["turns"] and trace["error"]
            rows.append(dict(id=folder.name,completed=False,correct_stop=False,stop="setup_timeout",
                             seconds=None,error=trace["error"],checks={"start_page_ready":False},detail={},
                             attempted=0,dispatched=0,invalid=0,repeats=0,chats=0,help=0,interventions=0))
    with (directory/"grades-reviewed.json").open("x",encoding="utf8") as out:
        json.dump(rows,out,ensure_ascii=False,indent=2)


def summarize(directory):
    grades = read(directory / "grades-reviewed.json")
    rows = []
    for grade in grades:
        trace = read(directory / grade["id"] / "interaction.json")
        requests = []
        for event in trace["turns"]:
            if "requests" in event:
                requests.extend(event["requests"])
                continue
            telemetry = event["telemetry"]
            status = "valid" if "decision" in event else {
                "output_contract_error": "format", "response_rejected": "incomplete"
            }.get(telemetry.get("status"), "transport")
            requests.append(dict(status=status, telemetry=telemetry, repair=False))
        counts = Counter(r["status"] for r in requests)
        telemetry = [r["telemetry"] for r in requests]
        rows.append(dict(
            id=grade["id"], completed=grade["completed"], correct_stop=grade["correct_stop"], stop=grade["stop"],
            calls=len(requests), http200=sum(t.get("status_code")==200 for t in telemetry),
            valid=counts["valid"], statuses=dict(counts), repairs=sum(r["repair"] for r in requests),
            repairs_ok=sum(r["repair"] and r["status"]=="valid" for r in requests),
            wire_schema_ok=sum(t.get("status")=="completed" for t in telemetry),
            terminal=trace.get("error"), actions=grade["dispatched"], invalid=grade["invalid"], repeats=grade["repeats"],
            chats=grade["chats"], help=grade["help"], interventions=grade["interventions"],
            seconds=trace.get("seconds"), task_seconds=trace.get("task_elapsed_s"),
            latency_ms=sum(t.get("latency_ms") or 0 for t in telemetry),
            input_tokens=sum(t.get("input_tokens") or 0 for t in telemetry),
            output_tokens=sum(t.get("output_tokens") or 0 for t in telemetry),
            checks=grade["checks"], detail=grade["detail"],
            dispatch_errors=[e.get("failure_type", e.get("error")) for e in trace["turns"] if e.get("error")],
        ))
    totals = {k:sum(r[k] for r in rows if r[k] is not None) for k in ("completed","correct_stop","calls","http200","valid","repairs",
              "repairs_ok","wire_schema_ok","actions","invalid","repeats","chats","help","interventions",
              "seconds","latency_ms","input_tokens","output_tokens")}
    totals["timed_n"] = sum(r["seconds"] is not None for r in rows)
    totals["statuses"] = dict(sum((Counter(r["statuses"]) for r in rows), Counter()))
    return {"totals":totals,"rows":rows}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    for directory in args.directories:
        if not (directory/"grades-reviewed.json").exists():
            grade_batch(directory)
    data={d.name:summarize(d) for d in args.directories}
    with args.out.open("x", encoding="utf8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
    for name,group in data.items():
        print(name,group["totals"])
