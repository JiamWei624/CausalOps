from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from causalops.capabilities import format_method_label
from causalops.metadata.presentation_zh import (
    claim_label_zh, diagnostic_label_zh, field_label_zh, format_p_value_zh, message_zh, research_question_zh,
)
from causalops.schemas import ResultBundle


EVIDENCE_SCHEMA_VERSION = "run_evidence_v1"


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunFact:
    evidence_id: str
    label: str
    text_zh: str
    pointer: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_run_evidence(bundle: ResultBundle) -> dict[str, Any]:
    """An allowlisted aggregate-only view of one ResultBundle, not the source table."""
    facts: list[RunFact] = []

    def add(key: str, label: str, text: str, pointer: str, value: Any) -> None:
        facts.append(RunFact(key, label, text, pointer, value))

    spec = bundle.spec
    add("E001", "研究问题", research_question_zh(spec.question), "/spec/question", spec.question)
    add("E002", "分析方法", "本次采用" + format_method_label(bundle.plan.selected_method) + "。",
        "/plan/selected_method", bundle.plan.selected_method.value)
    add("E003", "结果指标", "结果变量为" + field_label_zh(spec.outcome) + "。", "/spec/outcome", spec.outcome)
    kind = bundle.evidence.get("data", {}).get("kind", "unspecified")
    kind_text = {
        "synthetic": "本次使用合成演示数据，不能据此声称真实平台业务效果。",
        "user_provided": "本次使用用户提供的数据；其来源、指标口径和识别条件仍需核对。",
    }.get(kind, "此运行尚未显式登记数据来源类别，不能据此作真实平台效果声明。")
    add("E004", "数据来源边界", kind_text, "/evidence/data/kind", kind)
    add("E020", "当前结论等级", "当前允许的结论等级为“" + claim_label_zh(bundle.claim_level) + "”。",
        "/claim_level", bundle.claim_level.value)
    if bundle.estimate:
        estimate = bundle.estimate
        add("E010", "主分析估计值", f"主分析估计值为{estimate.estimate:.6g}个结果指标单位。",
            "/estimate/estimate", estimate.estimate)
        add("E011", "主分析标准误", f"主分析标准误为{estimate.standard_error:.6g}。" if estimate.standard_error is not None else "主分析未计算标准误。",
            "/estimate/standard_error", estimate.standard_error)
        add("E012", "主分析置信区间", f"主分析的95%置信区间为[{estimate.confidence_interval[0]:.6g}, {estimate.confidence_interval[1]:.6g}]。" if estimate.confidence_interval else "主分析未计算置信区间。",
            "/estimate/confidence_interval", estimate.confidence_interval)
        add("E013", "主分析概率值", "主分析的P值为" + format_p_value_zh(estimate.p_value) + "。",
            "/estimate/p_value", estimate.p_value)
        add("E014", "估计样本行数", f"进入主分析估计的样本为{estimate.sample_size:,}行；行数不等于独立用户数。",
            "/estimate/sample_size", estimate.sample_size)
        if bundle.evidence.get('estimator',{}).get('outcome_binary'):
            add('E015','二元结果的百分点差异',f'本次线性概率模型对应{100*estimate.estimate:.6g}个百分点的条件差异；不是相对百分比增长或已识别的因果提升。',
                '/estimate/estimate',100*estimate.estimate)
    for index, diagnostic in enumerate(bundle.diagnostics):
        key = f"D{index + 1:03d}"
        text = message_zh(diagnostic.message)
        if diagnostic.name == "parallel_trends_joint_test":
            text = "处理前系数联合检验的P值为" + (
                format_p_value_zh(diagnostic.value) if isinstance(diagnostic.value, (int, float)) and not isinstance(diagnostic.value, bool)
                else str(diagnostic.value)
            ) + "。" + text
        add(key, diagnostic_label_zh(diagnostic.name), text, f"/diagnostics/{index}", diagnostic.model_dump(mode="json"))
    for index, warning in enumerate(bundle.warnings):
        add(f"L{index + 1:03d}", "已记录的限制", message_zh(warning), f"/warnings/{index}", warning)
    estimator = bundle.evidence.get("estimator", {})
    if estimator.get('cluster_count'):
        cluster_text=(f"本次按{estimator['cluster_count']:,}名用户聚类计算不确定性，同一用户可重复出现。" if spec.domain.value=='ugc' else f"本次按{estimator['cluster_count']:,}个分析实体聚类计算不确定性；聚类数不等于原始记录数。")
        add('E016','用户聚类数' if spec.domain.value=='ugc' else '分析实体聚类数',cluster_text,
            '/evidence/estimator/cluster_count',estimator['cluster_count'])
    context=bundle.evidence.get('study_context',{})
    for key,label in [('raw_source_rows','原始来源行数'),('reply_censored_rows','原始回复状态删失记录数'),
                      ('invalid_record_rows','原始明确质量异常记录数'),('recovered_7d_zero_labels','原始7天标签可恢复的零值数'),
                      ('recovered_30d_zero_labels','原始30天标签可恢复的零值数'),('reply_after_or_at_return','原始回复不早于再次发帖记录数')]:
        if key in context:
            add(f'R{len([f for f in facts if f.evidence_id.startswith("R")])+1:03d}',label,
                f"来源全量CSV的{label}为{context[key]:,}条；不是当前模型的样本计数。",'/evidence/study_context/'+key,context[key])
    if context.get('sample_note'):
        add('R020','本次样本口径',context['sample_note'],'/evidence/study_context/sample_note',context['sample_note'])
    for i,key in enumerate(['fixed_horizon_cohort','potential_followup_sec','timing_limit'],start=21):
        text=context.get('definitions',{}).get(key)
        if text:
            add(f'R{i:03d}','已记录的数据处理口径',text,'/evidence/study_context/definitions/'+key,text)
    if context.get('paper_reference_is_not_this_run'):
        add('P001','论文参考系数（不是本次估计）',
            f"所提供论文表3的参考系数为{context['paper_reference_coefficient']:.4f}，对应{100*context['paper_reference_coefficient']:.2f}个百分点；这是论文报告值，不是本次运行的重新估计结果。",
            '/evidence/study_context/paper_reference_coefficient',context['paper_reference_coefficient'])
    for index,group in enumerate(estimator.get('raw_group_summary',[])):
        group_label='回复状态' if spec.domain.value=='ugc' else '处理状态'
        add(f'G{index+1:03d}','未调整分组结果',f"{group_label}为{group['treatment']:g}的事件有{group['n']:,}条，未调整结果均值为{group['outcome_mean']:.6g}；分组均值不是回归系数或因果效应。",
            f'/evidence/estimator/raw_group_summary/{index}',group)
    for index, row in enumerate(estimator.get("event_study_table", [])):
        day = row["relative_day"]
        text = (
            f"相对处理日{day}是基准期，系数被归一化为零，未单独估计标准误或区间。"
            if row["is_reference"] else
            f"相对处理日{day}的系数为{row['estimate']:.6g}，逐点95%区间为[{row['ci_lower']:.6g}, {row['ci_upper']:.6g}]。"
        )
        add(f"T{index + 1:03d}", f"相对日{day}", text, f"/evidence/estimator/event_study_table/{index}", row)
    sensitivity = bundle.evidence.get("window_sensitivity") or {}
    for index, row in enumerate(sensitivity.get("rows", [])):
        text = f"前{row['pre_days']}天、后{row['post_days']}天窗口（后窗含处理当日）："
        if row.get("status") == "estimated":
            text += f"估计值{row['estimate']:.6g}，95%区间[{row['ci_lower']:.6g}, {row['ci_upper']:.6g}]，样本{row['sample_size']:,}行。"
        else:
            text += str(row.get("reason", "无法估计。"))
        add(f"W{index + 1:03d}", "预设窗口比较", text, f"/evidence/window_sensitivity/rows/{index}", row)
    # These are explicitly methodological rules, not newly executed tests.
    if bundle.plan.selected_method.value=='regression_adjustment':
        add('M001','当前方法范围','本运行是观察性回归调整，不是随机实验或双重差分；没有计算平行趋势检验。','method_rule:regression_scope','methodological_explanation')
        add('M002','聚类与识别边界',('按用户聚类调整不确定性，不验证无未观察混杂、无干扰或回复先于结果。' if spec.domain.value=='ugc' else '按分析实体聚类调整不确定性，不验证无未观察混杂、无干扰或处理先于结果。'),'method_rule:regression_limits','methodological_explanation')
    else:
        add("M001", "两类概率值的区别", "主分析检验处理后系数是否为零；处理前联合检验检验多个处理前系数是否共同为零。二者检验对象不同。", "method_rule:distinct_tests", "methodological_explanation")
        add("M002", "平行趋势解释规则", "未拒绝处理前系数共同为零，不能证明平行趋势成立；短窗口和检验功效也会影响诊断。", "method_rule:pretrend_limits", "methodological_explanation")
    add("M003", "指标单位解释规则", "线性模型的系数按结果变量单位解释；没有适当基准或模型变换时，不得直接改写为百分比提升。", "method_rule:outcome_units", "methodological_explanation")
    add("M004", "窗口比较解释规则", "预设窗口比较属于探索性敏感性分析；不得挑选显著窗口替代主分析，逐点区间未作多重比较校正。", "method_rule:window_limits", "methodological_explanation")
    payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION, "run_id": bundle.run_id,
        "bundle_sha256": canonical_sha256(bundle.model_dump(mode="json")),
        "claim_level": bundle.claim_level.value, "data_kind": kind,
        "facts": [fact.to_dict() for fact in facts], "data_rows_transmitted": False,
    }
    payload["snapshot_id"] = canonical_sha256(payload)
    # JSON normalization makes tuples/lists identical before and after SQLite persistence.
    return json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def select_question_evidence(snapshot: dict[str, Any], question: str) -> list[dict[str, Any]]:
    # Retrieval changes do not mutate the immutable run evidence snapshot.
    if snapshot.get('data_kind')=='user_provided' and any(
            f['evidence_id']=='R020' for f in snapshot['facts']):
        wanted={'E001','E002','E003','E004','E020'}
        if any(w in question for w in ('样本','原始数据','行数','事件数','用户数','聚类数','为什么数字不同')):
            wanted.update({'R001','R002','R003','R020','E014','E016'})
        if any(w in question for w in ('标签','空值','删失','随访','固定窗口')):
            wanted.update({'R004','R005','R020','R021','R022','L002'})
        if any(w in question for w in ('论文','复现','表3')):
            wanted.update({'P001','E010','E012','E015','R020','D003'})
        if any(w in question for w in ('因果','混杂','偏差','标准误','识别','条件相关')):
            wanted.update({'D003','M001','M002','L001','L002','L003','R023'})
        if any(w in question for w in ('平台','实验方向','汇报','研究发现','意义')):
            wanted.update({'E010','E012','E015','R020','D003','L002','L003','R023'})
        if any(w in question for w in ('估计','置信区间','系数','百分点','结果')) or len(wanted)==5:
            wanted.update({'E010','E012','E015'})
        if any(w in question for w in ('后续','哪些数据','时间戳','下一步')):
            wanted.update({'R023','R022','D003','L002','L003'})
        return [f for f in snapshot['facts'] if f['evidence_id'] in wanted]
    core = [f for f in snapshot["facts"] if f["evidence_id"][0] in {"E", "D", "L", "M", "R", "G", "P"}]
    method=next((f['value'] for f in snapshot['facts'] if f['evidence_id']=='E002'),None)
    if method not in {'did','event_study'}:
        core=[f for f in core if f['evidence_id'] not in {'M001','M002'} or method=='regression_adjustment']
    if any(word in question.lower() for word in ("窗口", "敏感", "稳健", "window", "比较")):
        core += [f for f in snapshot["facts"] if f["evidence_id"].startswith("W")]
    if any(word in question.lower() for word in ("动态", "逐期", "事件", "第", "event")):
        core += [f for f in snapshot["facts"] if f["evidence_id"].startswith("T")]
    return core


def build_interpreted_run_evidence(bundle):
    from .interpretation import interpret_run
    from causalops.metadata.presentation_zh import diagnostics_for_display
    payload=build_run_evidence(bundle)
    payload.pop('snapshot_id')
    interpretation=interpret_run(bundle)
    payload['schema_version']='run_evidence_v2_'+interpretation['version']
    payload['interpretation']=interpretation
    labels={'baseline':'基线与参考水平','magnitude':'绝对变化与区间','relative':'相对变化','scale':'标准化规模换算',
            'meaning':'实际含义','action':'行动建议（尚未执行）','boundary':'解释适用范围','cost':'成本与收益边界'}
    for i,(name,label) in enumerate(labels.items(),1):
        payload['facts'].append(RunFact(f'C{i:03d}',label,interpretation['texts'][name],
                       '/interpretation/texts/'+name,interpretation['texts'][name]).to_dict())
    if bundle.plan.selected_method.value=='ab_test' and not bundle.spec.covariates:
        corrected=diagnostics_for_display(bundle)
        for index,d in enumerate(corrected):
            if d.name=='baseline_balance_not_assessed':
                payload['facts']=[RunFact(f'D{index+1:03d}','基线平衡检查未实施',d.message,
                    f'/presentation/diagnostics/{index}',d.model_dump(mode='json')).to_dict() if f['evidence_id']==f'D{index+1:03d}' else f for f in payload['facts']]
    payload['snapshot_id']=canonical_sha256(payload)
    return json.loads(json.dumps(payload,ensure_ascii=False,allow_nan=False))


_legacy_select_question_evidence=select_question_evidence

def select_question_evidence(snapshot,question):
    facts=_legacy_select_question_evidence(snapshot,question)
    wants=any(w in question for w in ('基线','绝对','变化幅度','相对','每千','千人','实际含义','行动建议','业务','结论','提升','通俗','汇报'))
    if wants:
        facts += [f for f in snapshot['facts'] if f['evidence_id'].startswith('C')]
    return list({f['evidence_id']:f for f in facts}.values())
