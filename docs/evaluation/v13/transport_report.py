"""Offline V1.3 request audit. Exports metadata only and never calls a provider."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

PRICE_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
CST = timezone(timedelta(hours=8))
LOGS = ("requests.jsonl", "responses.jsonl", "physical_attempts.jsonl")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def lines(path, issues):
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8-sig") as stream:
        for n, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or not record.get("call_id"):
                    raise ValueError("missing_call_id")
                records.append(record)
            except ValueError:
                issues.append(f"{path}:{n} invalid record")
    return records


def ratio(n, d):
    return {"n": n, "d": d, "rate": n/d if d else None}


def peak_window(at):
    d = datetime.fromisoformat(at).astimezone(CST)
    return d.weekday() < 5 and (9 <= d.hour < 12 or 14 <= d.hour < 18)


def audit_folder(folder, group, batch, issues, ledger):
    requests, responses, physical = [lines(folder / name, issues) for name in LOGS]
    by_id = defaultdict(lambda: [[], [], []])
    for i, block in enumerate((requests, responses, physical)):
        for record in block:
            by_id[record["call_id"]][i].append(record)
    for call_id, (starts, ends, events) in by_id.items():
        warnings = []
        req = starts[0] if starts else {}
        end = ends[0] if ends else {}
        if len(starts) != 1 or len(ends) != 1:
            warnings.append(f"logical start/end={len(starts)}/{len(ends)}")
        if len({r.get("request_sha256") for r in starts + ends + events}) != 1:
            warnings.append("request digest mismatch")
        numbers = sorted({e["attempt"] for e in events})
        if numbers not in ([1], [1, 2]):
            warnings.append("nonstandard attempt sequence")
        physical_rows = []
        for number in numbers:
            same = [e for e in events if e["attempt"] == number]
            start = [e for e in same if e["event"] == "started"]
            finish = [e for e in same if e["event"] == "finished"]
            if len(start) != 1 or len(finish) != 1:
                warnings.append(f"attempt {number} start/end={len(start)}/{len(finish)}")
            outcome = finish[0] if finish else {}
            row = {k: outcome.get(k) for k in ("status", "status_code", "request_id", "error", "will_retry", "latency_ms",
                                                "input_tokens", "output_tokens", "total_tokens", "model", "provider_host")}
            row.update(attempt=number, start_count=len(start), end_count=len(finish),
                       start=start[0]["at"] if start else None, end=outcome.get("at"))
            if number < max(numbers) and row["will_retry"] is not True:
                warnings.append("unannounced retry")
            physical_rows.append(row)
        if ends and physical_rows and physical_rows[-1]["status"] is not None:
            if bool(end.get("valid")) != (physical_rows[-1]["status"] == "completed"):
                warnings.append("acceptance conflicts with final physical event")
        issues.extend(f"{batch.name}/{folder.relative_to(batch)} {call_id} {w}" for w in warnings)
        ledger.append(dict(group=group, batch=batch.name, folder=folder.relative_to(batch).as_posix(),
                           call_id=call_id, schema=req.get("schema") or end.get("schema"), number=req.get("number"),
                           request_sha256=req.get("request_sha256"), valid=end.get("valid"), error=end.get("error"),
                           logical_starts=len(starts), logical_ends=len(ends), physical=physical_rows))


def summarize(rows):
    physical = [p for r in rows for p in r["physical"]]
    first = [r["physical"][0] for r in rows if r["physical"] and r["physical"][0]["attempt"] == 1]
    first_known = [p for p in first if p["status"] is not None]
    failed_first = [p for p in first_known if p["status"] != "completed"]
    network_first = [p for p in first_known if p["status"] in ("transport_error", "http_error")]
    retried = [r for r in rows if any(p["attempt"] == 2 and p["start_count"] for p in r["physical"])]
    recovered = sum(r["valid"] is True for r in retried)
    by_number={(r["batch"], r["folder"], r["number"]): r for r in rows}
    failed_contracts=[r for r in rows if any(p["status"]=="output_contract_error" for p in r["physical"])]
    followups=[]
    for r in failed_contracts:
        nxt=by_number.get((r["batch"],r["folder"],r["number"]+1))
        if nxt and nxt["schema"]==r["schema"]:
            followups.append(nxt)
    costs = [0., 0.]
    itokens = otokens = 0
    receipts = 0
    for p in physical:
        i, o = p["input_tokens"], p["output_tokens"]
        if type(i) is not int or type(o) is not int:
            continue
        receipts += 1
        itokens += i
        otokens += o
        # Bounds across unknown cache mix. During weekday daytime, public-holiday status
        # can only lower the price; use unrestricted peak for a conservative upper bound.
        span = [p[k] for k in ("start","end") if p[k]]
        upper_multiplier = 2 if not span or any(peak_window(t) for t in span) else 1
        costs[0] += (.02*i + 4*o) / 1_000_000
        costs[1] += upper_multiplier * (i + 4*o) / 1_000_000
    start_count = sum(p["start_count"] for p in physical)
    http_replies = [p for p in physical if p["status_code"] is not None]
    latency = sorted(p["latency_ms"] for p in physical if isinstance(p["latency_ms"],(int,float)))
    from math import ceil
    lat = {key: latency[ceil(q*len(latency))-1] if latency else None for key,q in (("p50",.50),("p95",.95))}

    schema = {}
    for name in sorted({str(r["schema"]) for r in rows}):
        same = [r for r in rows if str(r["schema"]) == name]
        schema[name] = {"valid":sum(r["valid"] is True for r in same), "invalid":sum(r["valid"] is False for r in same),
                        "no_result":sum(r["valid"] is None for r in same)}
    timestamps = sorted(t for p in physical for t in (p["start"],p["end"]) if t)
    return dict(logical_starts=sum(r["logical_starts"] for r in rows),logical_ends=sum(r["logical_ends"] for r in rows),
                physical_starts=start_count,physical_ends=sum(p["end_count"] for p in physical),
                first_failed=ratio(len(failed_first),len(first_known)),first_transport_or_http_failure=ratio(len(network_first),len(first_known)),
                next_same_schema_after_contract_error=ratio(len(followups),len(failed_contracts)),
                next_same_schema_valid=ratio(sum(r["valid"] is True for r in followups),len(followups)),
                first_status_missing=sum(p["status"] is None for p in first),retry_recovery=ratio(recovered,len(retried)),
                recovery_among_all_first_failures=ratio(recovered,len(failed_first)),structured_acceptance=ratio(sum(r["valid"] is True for r in rows),len(rows)),
                status=dict(Counter(p["status"] or "unknown" for p in physical)),
                latency_ms_nearest_rank=lat,http_reply_received=ratio(len(http_replies),start_count),
                request_id_missing_on_http_reply=sum(not p["request_id"] for p in http_replies),
                provider_hosts=dict(Counter(p["provider_host"] for p in physical if p["provider_host"])),
                resolved_models=dict(Counter(p["model"] for p in http_replies if p["model"])),
                errors=dict(Counter(p["error"] for p in physical if p["error"])),
                http_status=dict(Counter(str(p["status_code"]) for p in physical if p["status_code"] is not None)),
                schema=schema,request_id_receipts=ratio(sum(bool(p["request_id"]) for p in physical),start_count),
                usage_receipts=ratio(receipts,start_count),input_tokens=itokens,output_tokens=otokens,
                cost_known_usage_cny=[round(v,8) for v in costs],cost_covers_all_started=receipts==start_count,
                timestamps_cst=[datetime.fromisoformat(t).astimezone(CST).isoformat() for t in (timestamps[0],timestamps[-1])] if timestamps else [])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("implementation",type=Path)
    ap.add_argument("holdout",type=Path)
    args=ap.parse_args()
    root=args.implementation.resolve()
    ledger,issues,batches,slots=[],[],[],[]
    repair_events=Counter()
    for suite, parent in (("old",root/"old"),("holdout",args.holdout.resolve()/"batches")):
        for batch in sorted(parent.glob("deepseek-*")):
            folders=sorted({p.parent for name in LOGS for p in batch.rglob(name)})
            manifest=load(batch/"manifest.json")
            planned=manifest.get("计划",manifest.get("slots",[]))
            for folder in folders:
                smoke=bool({"probe","smoke"}.intersection(folder.relative_to(batch).parts))
                group=suite+("_smoke" if smoke else "_formal")
                audit_folder(folder,group,batch,issues,ledger)
                db=folder/"work"/"research.sqlite3"
                if db.exists():
                    with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True) as conn:
                        if conn.execute("select count(*) from sqlite_master where name='assistant_events'").fetchone()[0]:
                            repair_events[group]+=conn.execute("select count(*) from assistant_events where kind='output_contract_repair'").fetchone()[0]
            for job in planned:
                case,n=job[-2:]
                folder=(batch if suite=="old" else batch/"deepseek")/case/f"attempt-{n}"
                marker=folder/("score.json" if suite=="old" else "slot.json")
                status="no_slot_marker"
                if marker.exists():
                    info=load(marker)
                    status=info.get("status") or ("scored" if (folder/"observation.json").exists() else "scored_without_observation")
                slots.append({"suite":suite,"batch":batch.name,"case":case,"round":n,"status":status,
                              "logical_log":(folder/"requests.jsonl").is_file()})
            closed=next((s for s in ("unstarted.json","summary.json","closed.json") if (batch/s).exists()),None)
            batches.append({"suite":suite,"batch":batch.name,"commit":manifest.get("提交",manifest.get("revision")),
                            "planned":len(planned),"closure":closed,"physical_log_folders":len(folders)})
    groups={group:summarize([r for r in ledger if r["group"]==group]) for group in
            ("old_formal","holdout_formal","old_smoke","holdout_smoke")}
    for ending in ("formal","smoke"):
        groups["all_"+ending]=summarize([r for r in ledger if r["group"].endswith(ending)])
    duplicate_ids=[k for k,v in Counter(r["call_id"] for r in ledger).items() if v>1]
    issues.extend("duplicate_call_id "+i for i in duplicate_ids)
    for item in batches:
        same=[s for s in slots if s["batch"]==item["batch"]]
        item["slot_status"]=dict(Counter(s["status"] for s in same))
        item["slots_without_log"]=sum(not s["logical_log"] for s in same)
    payload=dict(batches=batches,slots=slots,groups=groups,repair_events=dict(repair_events),issues=issues,
                 pricing_source=PRICE_SOURCE,price_basis="CNY per million flash tokens. Cache composition unavailable.")
    for name,data in (("transport_metrics",payload),("transport_ledger",ledger)):
        (root/(name+".json")).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    def rate(x):
        return f"{x['n']}/{x['d']} ({x['rate']:.1%})" if x["d"] else "0/0（无适用样本）"
    report=["# V1.3 官方接口调用及已知用量","",
            "| 范围 | 逻辑开始/结束 | 物理开始/结束 | 首次未获有效结构 | 首次传输或 HTTP 失败 | 重试后恢复 | 最终结构通过 | 有用量回执 | 已知用量估价（元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    labels=["旧题正式","陌生题正式","旧题冒烟","陌生题探测","正式合计","冒烟合计"]
    for label,g in zip(labels,groups.values()):
        lo,hi=g["cost_known_usage_cny"]
        report.append(f"| {label} | {g['logical_starts']}/{g['logical_ends']} | {g['physical_starts']}/{g['physical_ends']} | {rate(g['first_failed'])} | {rate(g['first_transport_or_http_failure'])} | {rate(g['retry_recovery'])} | {rate(g['structured_acceptance'])} | {rate(g['usage_receipts'])} | {lo:.6f}–{hi:.6f} |")
    report+=["","首发失败率分母仅计有首次结束状态的逻辑调用。结构错误计入首次未获有效结构。重试恢复率分母为实际启动第二次传输的逻辑调用。应用层重新生成结构属于新的逻辑调用。物理开始指客户端已进入一次发送尝试，收到服务方请求标识单独计数。","",
             "| 批次 | 计划槽 | 无请求日志的槽 | 槽位状态 | 结束标记 |","|---|---:|---:|---|---|"]
    for b in batches:
        report.append(f"| {b['batch']} | {b['planned']} | {b['slots_without_log']} | {b['slot_status']} | {b['closure'] or '未关闭'} |")
    report+=["","“无请求日志的槽”含被冒烟门禁拦截、子进程提前失败等情况。一个题目在不同批次重新排期时会产生多个计划槽，调用统计保留每一次真实尝试。"]
    for key,title in (("all_formal","正式"),("all_smoke","冒烟")):
        g=groups[key]
        report+=["",f"{title}输入 {g['input_tokens']:,}、输出 {g['output_tokens']:,} tokens。服务方请求标识回执 {rate(g['request_id_receipts'])}。取得 HTTP 响应 {rate(g['http_reply_received'])}。客户端物理尝试耗时 P50/P95 为 {g['latency_ms_nearest_rank']['p50']}/{g['latency_ms_nearest_rank']['p95']} 毫秒。已记录的物理状态为 {g['status']}。结构错误后，同一槽下一次逻辑请求仍用同一结构的比例为 {rate(g['next_same_schema_after_contract_error'])}，这些后续请求通过 {rate(g['next_same_schema_valid'])}。未覆盖用量的实际尝试共 {g['physical_starts']-g['usage_receipts']['n']} 次。"]
    report+=["",f"本地结构修复事件按组计数为 {dict(repair_events)}。日志一致性异常 {len(issues)} 条。明细见 transport_metrics.json 和 transport_ledger.json。","",
             "人民币按 Flash 空闲价每百万输入缓存命中 0.02 元、未命中 1 元、输出 4 元估算。缓存拆分未留存，下界假设全部命中，上界假设全部未命中；北京工作日 9–12 时或 14–18 时的上界按双倍计费。缺用量回执的请求未纳入金额，无法从日志推出这些请求的费用上界。实际扣款须以服务方账单为准。"
             +f"[DeepSeek 官方价目]({PRICE_SOURCE})"]
    (root/"transport_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print([(b["batch"],b["closure"]) for b in batches], "logical calls",len(ledger),"integrity issues",len(issues))


if __name__=="__main__":
    main()
