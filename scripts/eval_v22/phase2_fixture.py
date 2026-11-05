"""Controller-side preconditions. Never pass reference answers into the browser script."""
import hashlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/eval_v20/controller"))


def seed(task, home):
    import pandas as pd
    from fixture_data import materials
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace
    from causalops.sample_data.hillstrom import ARCHIVE_SHA, contract

    s = ResearchService(AssistantWorkspace(GeneralWorkspace(home)))

    def approved(frame, dictionary, title, query):
        sid = s.create_task(payload=frame.to_csv(index=False).encode(), name=title+".csv", title=title)
        s.contracts.save(sid, dictionary, expected_sha=None, human_confirmed=True)
        flow = s.start(sid, query, mode="plan")
        assert flow["status"] == "awaiting_review", flow["status"]
        p = s.a.get_plan(flow["plan_id"])
        s.review(flow["id"], accept=True, expected_plan_id=p["id"], expected_plan_sha=p["sha"],
                 expected_data_sha=flow["request"]["data"]["frame_sha"], human_confirmed=True, use_contract_facts=True)
        run, = s.a.completed_runs(sid)
        return dict(sid=sid, flow=flow["id"], plan=p["id"], sha=p["sha"], run=run["run_id"],
                    binding=flow["request"]["data"], title=title, dataset=title+".csv")

    if task == "N05":
        archive = Path(os.environ["CAUSALOPS_HILLSTROM_ARCHIVE"])
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA
        full = pd.read_csv(archive)
        sub = full.loc[full.segment.isin(["Mens E-Mail","No E-Mail"])]
        frame = pd.DataFrame(dict(entity_id=sub.index, assigned=sub.segment.eq("Mens E-Mail").astype(int),
                                  visit=sub.visit, conversion=sub.conversion))
        refs = []
        for metric, label in [("visit","访问率"),("conversion","购买率")]:
            dic = contract()
            dic.update(outcome=metric, metric_label="两周"+label)
            dic["fields"].append(dict(field="conversion",meaning="两周内是否购买",unit="0/1",timing="post_treatment"))
            dic["research"]["estimand"]="两组客户两周"+label+"的绝对差"
            title="营销邮件 · 两周"+label
            refs.append(approved(frame, dic, title, "使用 A/B 随机实验比较男装邮件与未发邮件客户的两周"+label+"并给出差异。"))
        return dict(target=refs[0], distractor=refs[1], expected=frame.groupby("assigned").visit.mean().tolist())
    if task in ("N06","N07"):
        frame, dic = materials("B05" if task=="N06" else "B06")
        ref=approved(frame,dic,"门店日指标研究","生成 orders 每日订单数的描述统计分布报告。")
        sample=frame if task=="N06" else frame.tail(5)
        col="visitors" if task=="N06" else "orders"
        return dict(target=ref, old_mean=float(frame.orders.mean()), expected=float(sample[col].mean()),
                    n=len(sample), field=col, window=[sample.day.iloc[0],sample.day.iloc[-1]])
    return {}

