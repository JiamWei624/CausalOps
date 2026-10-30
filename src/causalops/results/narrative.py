"""Deterministic conclusions built from the exact stored run."""
from __future__ import annotations

from causalops.capabilities import format_method_label
from causalops.metadata.presentation_zh import claim_label_zh, diagnostic_label_zh, field_label_zh, format_p_value_zh, message_zh
from causalops.schemas import ClaimLevel, ResultBundle
from causalops.metadata.presentation_zh import diagnostics_for_display


def conclusion_sections(bundle: ResultBundle) -> list[tuple[str, list[str]]]:
    from .interpretation import business_sections
    return business_sections(bundle) + technical_conclusion_sections(bundle)


def technical_conclusion_sections(bundle: ResultBundle) -> list[tuple[str, list[str]]]:
    if bundle.plan.selected_method.value=='regression_adjustment':
        return _regression_conclusions(bundle)
    spec, estimate = bundle.spec, bundle.estimate
    estimator = bundle.evidence.get("estimator", {})
    kind = bundle.evidence.get("data", {}).get("kind", "unspecified")
    provenance = {
        "synthetic": "本次输入为合成演示数据。本报告用于检验分析流程和统计实现，不能据此宣称真实平台效果。",
        "user_provided": "本次输入由用户提供。数据来源、抽样方式及指标口径需要结合研究材料核实，不能仅凭文件上传推断数据代表性。",
    }.get(kind, "本次运行未显式登记数据来源类别，因此报告不对其真实性、代表性或真实平台效果作额外声明。")
    design = [provenance, f"研究采用{format_method_label(bundle.plan.selected_method)}，处理变量为“{field_label_zh(spec.treatment)}”，结果指标为“{field_label_zh(spec.outcome)}”。"]
    if estimate:
        design.append(f"实际进入估计的观测为{estimate.sample_size:,}行；输入总行数为{bundle.evidence['data']['row_count']:,}行。两个数字不同可能来自窗口筛选，不能把观测行数直接写成独立用户数。")
    if estimator.get("entity_count") is not None:
        design.append(f"估计样本涉及{estimator['entity_count']:,}个实体，其中处理组{estimator['treated_entity_count']:,}个、对照组{estimator['control_entity_count']:,}个。")
    if spec.pre_period_days and spec.post_period_days:
        design.append(f"主分析观察处理前{spec.pre_period_days}天及处理当日起{spec.post_period_days}天，即相对日−{spec.pre_period_days}至−1，以及0至{spec.post_period_days - 1}。")

    findings: list[str] = []
    if estimate:
        direction = "正向" if estimate.estimate > 0 else "负向" if estimate.estimate < 0 else "零值"
        findings.append(f"主分析系数为{estimate.estimate:.6g}，点估计呈{direction}。系数以结果指标单位解释，不能直接改写为百分比提升。")
        if estimate.confidence_interval:
            lower, upper = estimate.confidence_interval
            findings.append(f"95%置信区间为[{lower:.6g}, {upper:.6g}]，{'包含' if lower <= 0 <= upper else '不包含'}零。区间刻画当前设定下的统计不确定性，不包含未观察混杂或测量误差造成的全部不确定性。")
        findings.append(f"主分析P值为{format_p_value_zh(estimate.p_value)}。该检验针对主分析系数，不等于对平行趋势、指标口径或无干扰假设的检验。")
    else:
        findings.append("此运行未产生估计值，不能补写数值或效果结论。")

    diagnostics = []
    for item in diagnostics_for_display(bundle):
        diagnostics.append(f"{diagnostic_label_zh(item.name)}：{'未实施' if item.name=='baseline_balance_not_assessed' else '通过当前判定规则' if item.passed else '未通过当前判定规则'}。{message_zh(item.message)}")
        if item.name == "parallel_trends_joint_test" and isinstance(item.value, (int, float)):
            diagnostics.append(f"处理前系数联合检验P值为{format_p_value_zh(item.value)}。未拒绝处理前系数共同为零，也不能证明无处理状态下的反事实趋势必然相同；短观察窗口可能限制检验功效。")
    if bundle.warnings:
        diagnostics.extend(message_zh(item) for item in bundle.warnings)

    dynamic = []
    rows = [r for r in estimator.get("event_study_table", []) if not r.get("is_reference")]
    post = [r for r in rows if r["relative_day"] >= 0]
    if post:
        dynamic.append(f"已估计的处理后逐期系数范围为[{min(r['estimate'] for r in post):.6g}, {max(r['estimate'] for r in post):.6g}]。这是当前窗口内的描述，不能外推到未观察的长期时期。")
    if rows:
        dynamic.append("动态系数以处理前第1日为基准；基准期零值是归一化设定，其余区间为按实体聚类的逐点95%区间，未进行同时推断校正。")
        dynamic.append("原始均值轨迹用于识别可疑变化和样本构成问题，未经回归调整；两条曲线外观相近不构成平行趋势的证明。")
    if not dynamic:
        dynamic.append("此运行没有可用于该说明的动态效应明细，不能补写动态机制或长期趋势。")

    sensitivity = bundle.evidence.get("window_sensitivity") or {}
    comparisons = [r for r in sensitivity.get("rows", []) if r.get("status") == "estimated"]
    windows: list[str] = []
    if comparisons:
        values = [r["estimate"] for r in comparisons]
        signs_agree = all(v > 0 for v in values) or all(v < 0 for v in values)
        windows.append(f"本次保留了{len(comparisons)}种预设窗口的估计，系数范围为[{min(values):.6g}, {max(values):.6g}]；这些窗口中的点估计{'同号' if signs_agree else '并非全部同号'}。")
        counts = [r["sample_size"] for r in comparisons]
        windows.append(f"比较中的样本行数介于{min(counts):,}至{max(counts):,}之间，比较窗口结果时须同时考虑样本覆盖和所代表时间尺度的变化。")
        failed = sum(not r.get("pretrend_passed", False) for r in comparisons)
        windows.append(f"其中{failed}种窗口未通过处理前系数联合检验。主分析结论等级由主分析自身的设计和诊断决定，不会因为其他窗口更显著而升级。")
        windows.extend(sensitivity.get("limitations", []))
    else:
        windows.append(sensitivity.get("reason", "此运行未记录窗口敏感性分析，不能声称已检验窗口稳健性。"))

    ceiling = f"本次最终结论等级为“{claim_label_zh(bundle.claim_level)}”。"
    if bundle.claim_level in {ClaimLevel.DESCRIPTIVE, ClaimLevel.ASSOCIATIONAL}:
        ceiling += "只能报告描述或条件相关关系；当前不能把系数写为已识别的因果提升。"
    elif bundle.claim_level == ClaimLevel.REDUCED_FORM:
        ceiling += "可以在明确识别假设、适用样本和观察窗口的前提下作受限的准实验解释；当前诊断不能证明全部识别假设成立。"
    else:
        ceiling += "因果解释仍以已记录的设计假设为前提，需同时报告适用范围和剩余限制。"
    conclusion = [ceiling]
    if kind == "synthetic":
        conclusion.append("当前可交付的成果是：在合成数据上完成了研究设计、版本审核、估计、诊断、敏感性比较和证据留存的可复现流程。尚不能写成真实微博用户活跃度已得到提升。")
    else:
        conclusion.append("平台应用应首先把结果转化为待验证的策略假设，例如回复覆盖、触达时点或用户分层，再通过合适的实验或更有说服力的观察性设计验证。报告本身不代表策略已经上线或产生业务收益。")
    next_steps = [
        "核对处理和结果口径，尤其确认结果是否机械包含处理本身，并验证处理前协变量的测量时点。",
        "结合实际数据检查处理时点、对照组构成、观察窗口覆盖和用户间干扰；存在交错处理时使用合适的估计方法。",
        "若要分析新增人群、其他指标或更长窗口，先保存新的研究设计，再进行审核和计算；不得用问答生成未经计算的结果。",
    ]
    return [("研究对象与分析口径", design), ("主分析发现及统计含义", findings),
            ("诊断结果逐项解释", diagnostics), ("动态效应与轨迹的解释", dynamic),
            ("窗口敏感性分析的结论", windows), ("综合结论与平台应用边界", conclusion),
            ("后续研究与验证建议", next_steps)]


def _regression_conclusions(bundle: ResultBundle) -> list[tuple[str,list[str]]]:
    if bundle.spec.domain.value!='ugc':
        return _generic_regression_conclusions(bundle)
    e=bundle.estimate;details=bundle.evidence.get('estimator',{});context=bundle.evidence.get('study_context',{})
    design=[context.get('sample_note','按保存的研究设计估计观察性数据的条件相关关系。'),
            f"分析单位为每条发帖事件；同一用户可以贡献多条记录。输入分析表{bundle.evidence['data']['row_count']:,}行，完整案例估计{e.sample_size:,}行。" if e else '本次没有有效估计。']
    if context.get('raw_source_rows'):
        design.append(f"原始CSV共有{context['raw_source_rows']:,}条记录；原始表中回复状态右删失记录{context['reply_censored_rows']:,}条、明确质量异常{context['invalid_record_rows']:,}条，分别记录而不直接覆盖原始数据。不同分析另有观察期或发帖序号限制。")
    if details.get('cluster_count'):
        design.append(f"标准误按{details['cluster_count']:,}名用户聚类。回复分组属于事件级别，同一用户可以先后进入不同回复状态，不能把两组事件数相加解释为独立用户数。")
    findings=[]
    if e:
        findings.append(f"当前设定下，回复变量的条件关联系数为{e.estimate:.6g}，聚类标准误为{e.standard_error:.6g}，95%区间为[{e.confidence_interval[0]:.6g}, {e.confidence_interval[1]:.6g}]，P值为{format_p_value_zh(e.p_value)}。")
        if details.get('outcome_binary'):
            findings.append(f"结果是二元再次互动指标，因此该系数对应{100*e.estimate:.4f}个百分点的条件差异，95%区间为[{100*e.confidence_interval[0]:.4f}, {100*e.confidence_interval[1]:.4f}]个百分点。这不是相对百分比增长，也不是已经识别的因果提升。")
    controls=['已吸收的分类固定效应：'+('、'.join(field_label_zh(c) for c in details.get('fixed_effect_columns',[])) or '无'),
              '数值控制变量：'+('、'.join(field_label_zh(c) for c in details.get('numeric_control_columns',[])) or '无'),
              '没有把当期回复类型、回复等待时间、未来发帖间隔、累计含当期变量或用户未来总发帖数当作主模型控制变量。控制变量选择不能单独排除遗漏变量偏差。']
    quality=[]
    if context.get('recovered_7d_zero_labels') is not None:
        quality.append(f"全量来源核验发现，原7天标签中有{context['recovered_7d_zero_labels']:,}个空值对应已充分观察但没有窗口内再次互动的零结果；30天对应{context['recovered_30d_zero_labels']:,}条。直接删除原标签空值会改变样本构成。")
    quality.append('固定窗口队列要求潜在观察时长覆盖完整窗口，无论是否提前发生再次互动。潜在结束点从每名用户末条右删失记录反推，依赖原始Cox观察时长口径；该口径仍应与原数据生成脚本核对。')
    if context.get('reply_after_or_at_return') is not None:
        quality.append(f"原始表中有{context['reply_after_or_at_return']:,}条记录的AI回复不早于下一次发帖。因此，不能默认“收到回复”始终发生在结果之前；另做24小时landmark关联分析也不能自动解决所有选择问题。")
    diagnostics=[message_zh(d.message) for d in bundle.diagnostics]+[message_zh(w) for w in bundle.warnings]
    comparisons=['本运行只包含当前样本和当前指标。跨样本、跨窗口的比较必须读取对应的其他运行记录，不能由问答模型补算。']
    if context.get('paper_filter_count_reconciled'):
        comparisons.append(f"论文筛选计数已核对：发帖序号不超过53时为{context['paper_sample_raw_rows']:,}条，再排除回复状态右删失为{context['paper_reply_eligible_rows']:,}条；本次又排除明确质量异常，最终模型样本可能略少。")
        comparisons.append('论文报告的0.0392是论文表中的参考系数，不是本次重新估计值。控制变量、完整案例规则与软件实现并非保证完全相同，不将方向相近描述为精确复现。')
    conclusion=['本次结论限定为条件相关关系。统计显著、控制变量和聚类推断均不等同于随机化，也不能证明无未观察混杂、无干扰或时间顺序正确。',
                '对平台的意义是形成可检验的回复覆盖、等待时长和持续互动策略假设，并识别需要进一步实验的环节。不能把回归系数直接当作上线后可实现的留存提升或商业收益。',
                '工程层面已将真实事件数据、SQL清洗、样本口径、授权范围、统计运行、图文报告与证据问答关联起来；每条解释须回到相应运行核对。']
    next_steps=['核对原始数据生成脚本中的回复删失、观察结束和时间戳口径；缺少绝对日期时不能伪造日级面板或日级DID。',
                '后续因果研究需另行明确回复分配机制、暴露时点、目标人群和对照构成；若有平台条件，预先设计随机或更可信的准实验。',
                '若扩展到回复类型、机制或人群异质性，需要新增明确的分析方案与实际运行，不能从本报告外推出未计算结果。']
    return [('研究对象与样本口径',design),('主分析发现及统计含义',findings),('回归设定与控制变量',controls),
            ('删失、时序与标签质量',quality),('诊断与剩余限制',diagnostics),('对照分析与论文关系',comparisons),
            ('综合结论与平台应用边界',conclusion),('后续研究与验证建议',next_steps)]


def _generic_regression_conclusions(bundle: ResultBundle) -> list[tuple[str,list[str]]]:
    e=bundle.estimate;d=bundle.evidence.get('estimator',{});spec=bundle.spec
    context=bundle.evidence.get('study_context',{})
    design=[context.get('sample_note','按当前声明的观察性样本进行分析。'),
            f'分析单位：{spec.analysis_unit}；处理字段：{spec.treatment}；结果字段：{spec.outcome}。']
    if e:design.append(f'完整案例样本为{e.sample_size:,}行；按{d.get("cluster_count",0):,}个分析实体聚类。')
    findings=[]
    if e:
        findings=[f'处理变量的条件关联系数为{e.estimate:.6g}，标准误为{e.standard_error:.6g}，95%区间为[{e.confidence_interval[0]:.6g}, {e.confidence_interval[1]:.6g}]，P值为{format_p_value_zh(e.p_value)}。']
        if d.get('outcome_binary'):findings.append(f'二元结果的线性系数对应{100*e.estimate:.4f}个百分点差异；不是相对百分比提升。')
    controls=['数值控制字段：'+', '.join(d.get('numeric_control_columns',[])),
              '吸收的分类效应：'+(', '.join(d.get('fixed_effect_columns',[])) or '无')]
    limits=[message_zh(x.message) for x in bundle.diagnostics]+[message_zh(w) for w in bundle.warnings]
    return [('研究对象与样本口径',design),('主分析发现及统计含义',findings),('回归设定与控制变量',controls),
            ('诊断与剩余限制',limits),('综合结论与平台应用边界',[
             '当前仅支持条件相关解释。样本来源、处理选择、测量时点和可能的遗漏混杂必须分别评估。',
             '结果可用于形成待验证的领域假设，不构成政策、教学或营销干预已产生收益的证明。']),
            ('后续研究与验证建议',['核对处理与结果的时间顺序、控制变量的测量时点和目标总体。',
             '若要因果解释，另建可辩护的随机或准实验设计；新增估计须经过新的研究版本审核。'])]
