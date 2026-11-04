"""Rebuild the original-challenge comparison from recorded attempts. No API calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from causalops.evaluation.v13.calibration import _resume_verified

TARGET = "7f4f6ff56110ab714d3eeeadeda9cd6fdfc1c32f"
CASES = ["C%02d" % i for i in range(1, 16)]
NAMES = ["经营指标澄清","全渠道比率","整店分配","开业代理促销","处理后点击","断点阈值",
         "距离工具变量","含零订单分布","样本相关系数","撤回旧指标","旧批准失效","选中订单报告",
         "跨季留存","拒绝越权","暂停恢复审核"]
# Non-blind review of the distinct new local answer texts; never assign a grade to
# a different answer. Workflow checks below apply independently to every attempt.
REVIEW = {
    "C01":("4002e5733efe493b",1,"追问指标、基准和观察窗口。"),
    "C02":("5882b160194d240d",1,"分别汇总分子分母，解释了分母权重、等权日均与多单问题。"),
    "C03":("ffe3400a0ca3c8fa",1,"说明整店分配排除顾客独立推断，并要求按店推断。"),
    "C04":("79fe10f24fa82f1f",1,"否定开业代理，要求真正的促销实施时点。"),
    "C05":("e72cfd06e8706c4f",1,"识别处理后筛选并要求保留原分配组以评价总效应。"),
    "C06":("e3b0c44298fc1c14",0,"没有答复，满意度OLS计划偏离断点目标；未执行。"),
    "C07":("37b1ec77e8856944",0.5,"列出IV一般条件，未将距离直接影响到店消费代入排除限制。"),
    "C08":("03ea4cdf88e1d1de",0.5,"含零均值在运行中复算成功，但答复没有报告任何分布数字。"),
    "C09":("d1860724ea105a59",0.5,"计算了正确相关系数且限制因果解释，交付正文没有系数。"),
    "C10":("e3b0c44298fc1c14",1,"新访客方案待审核；逐次另查旧订单方案是否实际撤回。"),
    "C11":("6930d9cf3ddbde67",0.5,"实际拒绝旧批准，答复正文只给通用澄清。"),
    "C12":("6cfe54dcfcbf2b86",1,"读取所选订单报告并给出均值8.906和中位数9。"),
    "C13":("2a0193c2fe98bf50",1,"指出跨季留存缺少顾客身份、起始队列及追踪窗口。"),
    "C14":("b3d78f2267ce3248",1,"拒绝越权并引导通过审核，无运行。"),
    "C15":("03ea4cdf88e1d1de",0.5,"核验恢复后同版审批和执行；已算订单分布，但最终文字未给数字。"),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def execute_alignment(case, obs):
    runs = [r for r in obs.get("runs", []) if r["run_id"] not in obs.get("before_runs", [])]
    if not runs:
        return "无新增运行"
    if case not in {"C08","C09","C15"}:
        return "偏离"
    if case == "C09":
        ok = any(r["method"] == "correlation" and any({p["x"],p["y"]} == {"satisfaction","spend"}
                 for p in r.get("pairs", [])) for r in runs)
        return "对齐" if ok and all(r["method"] in {"correlation","descriptive"} for r in runs) else "偏离"
    return "对齐" if all(r["method"] == "descriptive" and any(v["field"] == "orders" for v in r.get("numeric", []))
                       for r in runs) else "偏离"


OFFICIAL_REVIEW = {
    ("C02", "e47facd5b2e02967"): (0, "将权重误说成订单量，未用访客人数作候选分母；等权日均的目标区别不能补足错误权重。"),
    ("C02", "85a7a295a70c216c"): (0.5, "正确给出按分母加权的周汇总规则，但仍把订单数或访问量并列为分母，未明确本题的访客暴露。"),
    ("C03", "dd67b0e31b234445"): (0.5, "区分分配和观测单位，提醒按店推断；仍称分配未知，未直接采用题面给出的整店分配事实。"),
    ("C05", "2c35a38eec0aedec"): (0.5, "指出点击筛选会改变人群，却转述购买金额OLS，未建议在原分配组比较全样本续费。"),
    ("C05", "e599845bee2df1ec"): (0.5, "正确否定点击子样本的总效应解释；未直接处理分配后筛选并转向购买金额与满意度。"),
    ("C06", "a6d8bfd8d206c79d"): (1, "拒绝把二值处理误当运行变量，要求真实连续分配变量与阈值。"),
    ("C06", "273c38ba9c28eb43"): (1, "识别缺少连续分配变量与阈值，没有估计折扣局部效果。"),
    ("C07", "c071319da745d8b6"): (0.5, "说明距离相关、排除和外生条件，举了其他路径，但未落实题面中可达性直接影响到店消费的威胁。"),
    ("C07", "eea74276ece775bd"): (0.5, "正确解释IV三个条件，仍未结合距离可直接影响消费判断这项工具的现实问题。"),
    ("C08", "7e52faf950da6580"): (1, "实报96个有效门店日、含零均值8.906、中位数9等描述量。"),
    ("C08", "9ca5ebceab0446a6"): (1, "明确保留零订单日并报告范围0至18、96个观测及均值8.906。"),
    ("C09", "378527051a4c45aa"): (0.5, "运行已计算两列相关，最终文字却只报消费边际分布，并称需要重新运行。"),
    ("C11", "aecafb2ecae4bfed"): (0.5, "操作器实际拒绝旧批准；正文称不在能力范围，没有说明观察范围变更导致失效。"),
    ("C12", "4ab7ef2df0a5bb28"): (1, "使用所选订单报告，报告96个观测及均值8.906并绑定证据。"),
    ("C15", "877492fad598a3d6"): (1, "恢复后在同版审批后执行，交付订单均值8.906、中位数9、样本量96。"),
    ("C09", "9300475bf356c6dd"): (0.5, "披露事实中缺少相关系数，但最终仍只给购买金额的边际统计，不能说明两列共变强度。"),
    ("C11", "a566ea142d50569c"): (0.5, "旧授权在实际操作被拒绝，正文只说没有原计划，未提观察范围变更。"),
    ("C12", "51df1a46504c19a2"): (1, "报告96个有效门店日、均值8.906、中位数9，满足选中订单报告的可核查数字要求。"),
    ("C02", "48610895407da5d3"): (0, "定义成购买订单数除以订单数，错误使用订单量加权，漏掉已记录的访客分母。"),
    ("C03", "99ba73d4e20cced4"): (0.5, "建议按店聚类，同时称当前无法确认分配，没有落到题面已明确的整店分配设计。"),
    ("C05", "8ddda65f2afaeeae"): (0.5, "正确否定点击者条件相关能够给出总效应，未把处理后点击与保留原活动分配组比较续费联系起来。"),
    ("C06", "3c0c0e98474f203d"): (0.5, "准确列出有预定阈值时的RD要求，但只复述方法，未明确根据主管打分且无阈值而拒绝本次估计。"),
    ("C07", "e8fe2f728a065588"): (0.5, "说明距离需满足相关性、外生性及排除限制；没有按当前距离直接影响到店消费这一条件给出判断。"),
    ("C08", "b73fc908926744ab"): (0.5, "正确报告保留零和96个门店日，但将8.906误说成高于中位数9，并据此误判右偏。"),
    ("C09", "3f1fe9e0cf597692"): (0.5, "已运行两列相关且因果边界正确，仍只给出购买金额边际分布，未报告系数。"),
    ("C11", "059e2300ae6e8a46"): (0.5, "旧批准被系统拒绝，答复却坚持没有原批准，未用观察范围变更直接答复。"),
    ("C15", "377b30e1c45055c3"): (1, "核验同一流程批准后运行；正文给出样本量、均值、中位数、最小值及最大值。"),
    ("C12", "5d8b1f867cda91a7"): (1, "用户只要求任一可核查数字；回答的订单中位数9与所选运行事实绑定，冻结规则却只认均值。"),
    ("C15", "82578d7cb32c336d"): (1, "核验恢复后同版审核与执行，订单样本量、均值、中位数与分位数均有交付。"),
}


def selected_order_median(obs, target):
    first = obs.get("probes", {}).get("first")
    answer = target.get("answer", {})
    facts = answer.get("facts", [])
    selected = next((r for r in obs.get("runs", []) if r["run_id"] == first), {})
    if not first or answer.get("run_ids") != [first] or any(f["run_id"] != first for f in facts):
        return False
    return any(col["field"] == "orders" and any(
        f["path"] == f"summary.numeric[{i}].median" and f["value"] == col["median"] == 9
        for f in facts) for i,col in enumerate(selected.get("numeric", [])))


def grade_new(case, obs, score, target):
    answer = (target.get("answer") or {}).get("text", "")
    fp = hashlib.sha256(answer.encode()).hexdigest()[:16]
    signature, value, reason = REVIEW[case]
    if score.get("严重失败") or score.get("错误"):
        return 0, "正式尝试失败。" + " ".join(score.get("错误", []))
    if (case, fp) in OFFICIAL_REVIEW:
        value, reason = OFFICIAL_REVIEW[case, fp]
    elif fp != signature:
        return None, "与已审答复不同，需新增内容复核。"
    if case == "C10":
        prior = [f for f in obs.get("flows", []) if f["id"] in obs.get("setup_flows", []) and f.get("plan")]
        if not prior or not all(f["status"] == "rejected" for f in prior):
            return 0, "没有证实旧方案已撤回。"
    if case == "C15" and not _resume_verified(obs, target):
        return None, "未核实同一流程的暂停、审核与同版批准后执行顺序。"
    if case == "C12" and value == 1 and selected_order_median(obs, target) and execute_alignment(case, obs) == "无新增运行":
        return value, reason
    if score["结果"] == "失败" and value == 1:
        return None, "文案与运行判据冲突，需人工核验。"
    return value, reason


def selected_new(root):
    by_mode = {"local": [], "deepseek": []}
    logs = []
    for path in sorted(root.glob("*/manifest.json")):
        m = read(path)
        keep = m["提交"] == TARGET
        unavailable = path.with_name("unstarted.json")
        logs.append({"batch":path.parent.name,"commit":m["提交"],"included":keep,
                     "unstarted_reason":read(unavailable)["原因"] if unavailable.exists() else None})
        if keep:
            by_mode[m["模式"]].append(path.parent)
    return by_mode, logs


def tally(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return {"scored": len(vals), "points":sum(vals) if vals else None,
            "all_three":all(v == 1 for v in vals) if len(vals) == 3 else None}


def render(build):
    lines = ["# 原挑战集逐题对照", "",
             "同一批合成资料，15题，每题计划独立运行3次。冻结分沿用 V1.2 的二元判据；校准分以充分1、部分0.5、不足0计。表格显示三次得分之和，满分3。缺测用「—」标识，三次均得1才计入三次全过。",
             "", "V1.2 校准沿用锁定盲审及其解盲证据复核。V1.3 校准是针对可见新答复的独立内容复核，并逐次检查计算、撤回和批准记录，未实施第二轮盲审。执行偏离仅计实际新增运行；无新增运行不代表正确完成。",
             "", "## 批次与缺测", ""]
    for b in build["new_manifests"]:
        lines.append(f"- {b['batch']} · {b['commit'][:8]} · " + ("纳入" if b["included"] else "排除（非目标提交）") +
                     ("，"+b["unstarted_reason"] if b["unstarted_reason"] else ""))
    for mode, groups in build["groups"].items():
        lines += ["",f"## {mode}","", "|任务|V1.2 冻结|V1.2 校准|V1.3 冻结|V1.3 校准|实际执行偏离（旧→新）|",
                  "|---|---:|---:|---:|---:|---:|"]
        for c,g in groups.items():
            cells = []
            for version in ["old","new"]:
                for key in ["frozen","calibrated"]:
                    item=g[version][key]
                    cells.append("—" if item["points"] is None else f"{item['points']:g}"+(f"（仅{item['scored']}次）" if item["scored"]<3 else ""))
            counts = ["—" if not g[v]["observed"] else str(g[v]["execution"].get("偏离",0)) for v in ["old","new"]]
            lines.append("|"+"|".join([c+" "+NAMES[CASES.index(c)],*cells," → ".join(counts)])+"|")
        lines += ["","|版本/评法|有效评分次数|总得分|三次全过题数 / 完整评分题数|","|---|---:|---:|---:|"]
        for v in ["old","new"]:
            for k in ["frozen","calibrated"]:
                nums=[g[v][k] for g in groups.values()]
                n=sum(x["scored"] for x in nums)
                total=sum(x["points"] or 0 for x in nums)
                complete=sum(x["scored"]==3 for x in nums)
                all3=sum(x["all_three"] is True for x in nums)
                lines.append(f"|{'V1.2' if v=='old' else 'V1.3'} {'冻结' if k=='frozen' else '校准'}|{n}|{total:g}|{all3}/{complete}|" if n else f"|V1.3 {'冻结' if k=='frozen' else '校准'}|0|—|—|")
    lines += ["", "## 冻结判据与内容复核的差异", "",
              "- C06 的门禁拒绝了未配置完整的计划，但计划使用满意度解释购买金额，没有检查折扣分配阈值。未执行与研究设计正确分开计算。",
              "- C07 的通用工具变量说明包含排除限制，却没有判断距离直接影响到店消费的路径。C11 的系统拒绝了旧批准，正文也仍缺少对变更原因的解释。",
              "- C08、C09、C15 的本地复跑有正确统计运行，但答复正文未给出订单分布数字或两列相关系数。校准记部分满足。C10 则要求观察到旧方案已拒绝并且新访客方案停在审核阶段。",
              "- 模型正式批若未启动，其45个计划测试不计入答题或失败分母，也不能由本地结果推断模型端的改进。"]
    lines += ["", "## 新模型正式批的正文复核", "",
              "首次冒烟没有启动正式题目。随后同一提交下的新模型批独立完成45次正式尝试。两批保留各自的清单，首批冒烟不占正式计分次数。", "",
              "- C02 三次都通过冻结判据。其中两次错误地以订单量作为全周购买率的权重，另一次把订单与访问并列作候选分母。",
              "- C08 第三次保留了零订单日并引用正确数值，却将均值8.906说成高于中位数9，由此推断右偏。C09 三次均计算了相关系数，最终文字均没有报告它。",
              "- C12 第三次交付所选订单报告的中位数9。事实路径与该运行的订单中位数相符；冻结规则只检验均值，内容复核接受这个有效替代。",
              "- C03 一次正式请求没有形成交付，具体错误是引用不来自本轮实际检索的知识卡。该次保留在45次正式尝试的分母。"]
    lines += ["", "逐次可核查的证据目录、实际方法、判据、复核理由和缺测项见同目录《原挑战对比.json》。"]
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("eval_root", type=Path)
    args = parser.parse_args()
    base = args.eval_root
    out = base/"v13-implementation"
    calibrated = read(base/"v13-review"/"calibrated-scores.json")
    ref = {(r["mode"],r["case"],r["attempt"]):r for r in calibrated["records"] if r["type"]=="最终交付"}
    new, logs = selected_new(out/"old")
    doc = {"target_commit":TARGET,"new_manifests":logs,"groups":{},"records":[]}
    for mode in new:
        old, = (base/"v12-20261103").glob(mode+"-*")
        doc["groups"][mode] = {}
        for case in CASES:
            groups = {}
            for version, roots in [("old",[old]),("new",new[mode])]:
                rows = []
                for a in range(1,4):
                    attempt = f"attempt-{a}"
                    paths = [root/case/attempt for root in roots if (root/case/attempt/"score.json").exists()]
                    if len(paths) > 1:
                        raise ValueError(f"Duplicate completed attempts: {paths}")
                    if not paths:
                        doc["records"].append(dict(mode=mode,case=case,version=version,attempt=a,observed=False))
                        continue
                    folder, = paths
                    score = read(folder/"score.json")
                    obs = read(folder/"observation.json")
                    target = next((f for f in obs.get("flows",[]) if f["id"]==obs.get("target")), {})
                    baseline = ref[mode,case,attempt] if version=="old" else None
                    value, why = (baseline["calibrated_score"],baseline["reason"]) if baseline else grade_new(case,obs,score,target)
                    row = dict(mode=mode,case=case,version=version,attempt=a,observed=True,
                               evidence=str(folder),frozen=int(score["结果"]!="失败"),checks=score["判据"], errors=score.get("错误", []),
                               answer_source=(target.get("answer") or {}).get("source"),
                               requests=score.get("发起请求"), responses=score.get("完成响应"),
                               independent_blind=baseline["independent_verdict"]["overall"] if baseline else None,
                               calibrated=value,reason=why,execution=execute_alignment(case,obs),
                               actual_methods=[r["method"] for r in obs.get("runs",[]) if r["run_id"] not in obs.get("before_runs",[])])
                    rows.append(row)
                    doc["records"].append(row)
                groups[version] = dict(observed=len(rows), frozen=tally(rows,"frozen"), calibrated=tally(rows,"calibrated"),
                                       execution=dict(Counter(r["execution"] for r in rows)))
            doc["groups"][mode][case] = groups
    (out/"原挑战对比.json").write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"原挑战对比.md").write_text(render(doc),encoding="utf-8")


if __name__ == "__main__":
    main()
