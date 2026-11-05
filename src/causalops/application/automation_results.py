
"""Read-only V2 workbench projection and evidence-bound export."""
from __future__ import annotations
import json
from html import escape
from causalops.assistant.service import digest
from causalops.general.service import DesignError

NAMES={"S01":"数据与设计审计","S02":"分组描述统计","S03":"上游证据核验","S04":"A/B 效果分析","S05":"报告整合"}
STATES={"candidate":"待整体审核","approved":"已批准，等待执行","pending":"未执行","running":"执行中","succeeded":"已完成","completed":"已完成","blocked":"安全阻断","interrupted":"结果需要核查","paused":"已暂停","pause_requested":"已请求暂停，将在安全边界停止","cancel_requested":"已请求取消，将在安全边界停止","cancelled":"已取消","queued":"排队中"}

def _reason(exc):
    return str(exc)[:600] if isinstance(exc,DesignError) else "证据核验未完成："+type(exc).__name__

def snapshot(co,tid):
    """Retry boundedly if worker commits while the view is being assembled."""
    for _ in range(3):
        task=co.task(tid);steps=co.steps(tid);evidence={};errors=[]
        for row in steps:
            if row["status"]=="succeeded":
                try:evidence[row["step_id"]]=co.evidence(tid,row["step_id"])
                except Exception as exc:errors.append(_reason(exc))
        try:
            if task["status"]=="candidate":co._binding(task)
            else:co._verify(task)
            binding_error=None
        except Exception as exc:binding_error=_reason(exc)
        after=co.task(tid);after_steps=co.steps(tid)
        if digest(task)!=digest(after) or digest(steps)!=digest(after_steps):continue
        for row in steps:
            row["name"]=NAMES[row["step_id"]]
            ev=evidence.get(row["step_id"])
            row["run_id"]=ev["body"].get("run_id") if ev else None
            cp=co.a.runtime.row(row["assistant_task_id"]) if row["assistant_task_id"] else None
            row["tool_attempts"]=(cp or {}).get("attempts",0)
        risks=[]
        if task["reason"]:risks.append(dict(rule="task_stop",level="阻断",detail=task["reason"]))
        if binding_error:risks.append(dict(rule="binding",level="执行不可用",detail=binding_error))
        for error in errors:risks.append(dict(rule="evidence_integrity",level="阻断",detail=error))
        if "S01" in evidence:
            a=evidence["S01"]["body"]
            risks.append(dict(rule="audit_structure",level="程序检查已通过",detail=f"必要字段无缺失，{a['rows']:,}条客户记录；实体唯一、两组和二元访问指标已核对。"))
            risks.append(dict(rule="source_confirmation",level="用户已确认",detail="随机分配和两周定义依据公开实验说明及来源确认，不是程序根据两组推断。"))
        else:risks.append(dict(rule="audit_pending",level="尚未执行",detail="正式数据与设计审计尚未完成，不将预览视为已通过审计。"))
        if "S03" in evidence:
            risks.append(dict(rule="upstream_gate",level="程序检查已通过",detail="描述统计Run的分组、有效样本、原数据及配置哈希已核对；显著性不参与放行。"))
        risks.append(dict(rule="unverified_assumptions",level="解释限制",detail="未实施基线协变量平衡检查；程序不能证明无干扰等全部识别假设。两周访问率不能直接推算长期利润。"))
        return dict(task=task,steps=steps,evidence=evidence,report=evidence.get("S05",{}).get("body") if not errors else None,
                    risks=risks,binding_error=binding_error,errors=errors,budget=co.budget(tid),events=co.events(tid))
    raise DesignError("任务状态正在更新，请稍后刷新；暂不展示可能混合的报告。")

def report_html(view):
    t=view["task"];p=t["plan"];r=view["report"];e=escape
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>.co-automation-report{font:15px/1.8 Microsoft YaHei,sans-serif;color:#203d43;max-width:980px;margin:24px auto;padding:16px}.co-automation-report h1,.co-automation-report h2{color:#136b65}.co-automation-report table{width:100%;border-collapse:collapse;margin:16px 0}.co-automation-report th,.co-automation-report td{padding:9px;border:1px solid #d4e0df;text-align:left;vertical-align:top}.co-automation-report th{background:#edf4f3}.co-automation-report .note{padding:12px;background:#f4f7f7}.co-automation-report code{overflow-wrap:anywhere}.co-automation-report a{color:#16736b}</style><article class="co-automation-report"><h1>营销邮件与两周访问率 · 整体研究报告</h1>']
    parts.append(f'<p><b>研究目标：</b>{e(p["objective"])}</p><p class="note">任务：<code>{e(t["id"])}</code> · 计划 v{p["version"]} · 状态：{e(STATES.get(t["status"],t["status"]))}</p>')
    if r:
        f=r["effect"];low,high=f["ci_pp"]
        parts.append(f'<h2>研究结论</h2><p>男装邮件组两周访问率为 <b>{f["treated_rate"]:.2%}</b>，未发邮件组为 <b>{f["control_rate"]:.2%}</b>。绝对差为 <b>{f["pp"]:.2f} 个百分点</b>，原 A/B 工具的95%区间为 <b>[{low:.3f}, {high:.3f}] 个百分点</b>。</p>')
        parts.append('<h2>数据、样本与比较口径</h2><p>来源：<a href="'+e(r["design_source"],quote=True)+'">Hillstrom 原始实验说明</a>。原始三组预先纳入男装邮件与未发邮件，女装组不在本次范围。分析单位为客户，指标为分配后两周内是否访问网站。没有自动删样本或填补缺失。</p>')
        parts.append('<table><tr><th>比较组</th><th>客户数</th><th>访问率</th></tr>')
        for g in r["group_summary"]:
            name="未发邮件" if str(g["treatment"])=="0" else "男装邮件"
            parts.append(f'<tr><td>{name}</td><td>{g["n"]:,}</td><td>{g["outcome_mean"]:.2%}</td></tr>')
        parts.append(f'</table><p>合计 {r["sample_size"]:,} 名客户。估计对象为邮件分配的意向处理访问概率差。方法为原独立组均值差、原标准误与 1.96 正态近似区间。</p>')
        parts.append('<h2>研究依据、诊断与限制</h2><p>随机分配依据公开设计资料与使用者确认。已检查必要字段缺失、实体唯一性、两组完整性、0/1指标、组内有效样本及变异，并核对两个统计Run的样本、目标、比较组、观察窗口和均值一致。未实施基线协变量平衡检查，未验证无干扰等全部识别假设。不将统计显著性作为下游执行条件，不能据此预测次年净利润或通用营销收益。</p>')
        parts.append(f'<p>描述统计 Run：<code>{e(r["source_runs"][0])}</code><br>A/B Run：<code>{e(r["source_runs"][1])}</code><br>批准：<code>{e(r["approval_id"])}</code> · 计划 v{r["plan_version"]}</p>')
    else:
        parts.append('<h2>部分完成说明</h2><p>尚无通过完整证据校验的整体报告。以下仅列已保存步骤，不生成未执行的A/B结论。</p>')
        parts.append('<p>'+e(t["reason"] or "需完成审核、执行或恢复核查。")+'</p>')
    parts.append('<h2>步骤来源与复现信息</h2><table><tr><th>步骤</th><th>状态</th><th>Run／证据哈希</th></tr>')
    for row in view["steps"]:
        parts.append('<tr><td>'+e(row["name"])+'</td><td>'+e(STATES.get(row["status"],row["status"]))+'</td><td><code>'+e(row["run_id"] or row["output_sha"] or "尚无成功证据")+'</code></td></tr>')
    parts.append('</table><p>计划：<code>'+e(p["plan_id"])+'</code><br>计划哈希：<code>'+e(t["plan_sha"])+'</code><br>数据指纹：<code>'+e(p["data"]["frame_sha"])+'</code><br>合同引用：<code>'+e(json.dumps(p["contract_ref"],ensure_ascii=False))+'</code></p>')
    parts.append('<p class="note">确定性事实报告。模型自主规划关闭，无模型生成的统计数值。完整结构化步骤、批准来源及运行清单可从工作台导出。</p></article></html>')
    return ''.join(parts)

def export_json(view):
    return json.dumps(view,ensure_ascii=False,indent=2,allow_nan=False).encode("utf8")
