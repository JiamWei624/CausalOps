"""Chinese presentation helpers; original machine-readable evidence stays intact."""
from __future__ import annotations

from typing import Any


CLAIM_LABELS = {
    "descriptive": "描述性结论",
    "associational": "条件相关关系",
    "reduced_form": "受限的准实验解释",
    "identified_causal": "在所列假设下的因果解释",
}
STATUS_LABELS = {"pass": "通过", "needs_review": "需人工审核", "blocked": "已阻断"}
DOMAIN_LABELS = {
    "generic": "通用研究", "ugc": "用户生成内容平台", "experiment": "随机实验",
    "ecommerce": "电子商务", "saas": "软件服务", "creator_incentive": "创作者激励",
}
FIELD_LABELS = {
    'reply_n':'当前帖子是否收到AI回复','reply_by_24h':'发帖24小时内是否收到AI回复',
    'remention_any':'观察期内是否再次@AI','remention_7d':'7天内是否再次@AI','remention_30d':'30天内是否再次@AI',
    'post_len_log':'帖子长度对数','post_emoji_count':'表情符号数','log_account_age':'账户年龄对数',
    'log_since_first':'距首次@AI时长对数','mention_order':'当前发帖序号','lag_reply':'上一条帖子是否收到回复',
    'cum_reply_count_before_n':'此前累计回复次数','reply_streak_before_n':'此前连续回复次数',
    'roll_neg_post_rate':'此前负向帖子比例','roll_pos_post_rate':'此前正向帖子比例',
    'post_year_month_cat':'发帖年月固定效应','post_region_cat':'发帖地区固定效应','topic_cat':'当前帖子类型',
    "question": "研究问题", "domain": "业务领域", "analysis_unit": "分析单位",
    "treatment": "处理变量", "outcome": "结果变量", "covariates": "处理前协变量",
    "candidate_methods": "候选方法", "identification_assumptions": "识别假设",
    "entity_id_column": "实体标识字段", "time_column": "日期字段",
    "treatment_time_column": "首次处理日期字段", "cluster_column": "聚类字段",
    "pre_period_days": "处理前窗口天数", "post_period_days": "处理后窗口天数",
    "source_tables": "来源数据表", "assignment_mechanism": "处理分配机制",
    "data_structure": "数据结构", "has_pre_treatment_outcome": "处理前结果声明",
    "positivity_plausible": "重叠性声明", "no_interference_plausible": "无干扰声明",
    "parallel_trends_plausible": "平行趋势声明",
    "user_id": "用户标识", "event_date": "观测日期", "first_ai_reply_date": "首次人工智能回复日期",
    "ai_reply_received": "是否收到人工智能回复", "baseline_activity": "处理前活跃度",
    "total_interactions": "总互动量", "treated": "是否进入处理组",
    "post_total_interactions": "处理后总互动量", "pre_total_interactions": "处理前总互动量",
    "registration_age_days": "注册时长（天）", "pre_metric": "处理前基线指标",
    "assignment": "随机分组", "retention_7d": "七日结果指标",
    "x1": "协变量一", "x2": "协变量二", "local_dataset": "当前本地数据集",
}
UNIT_LABELS = {"user_day": "用户—日", "user": "用户", "post": "帖子", "post_event":"用户发帖事件", "session": "会话"}
ASSUMPTION_LABELS = {
    "parallel_trends": "平行趋势（待经验诊断与人工判断）",
    "no_anticipation": "无预期效应（待人工确认）",
    "conditional exchangeability given observed pre-treatment activity": "给定已观察的处理前活跃度，处理分配满足条件可交换性（待审核）",
    "conditional exchangeability given x1 and x2": "给定协变量一与协变量二，处理分配满足条件可交换性（待审核）",
}
QUESTION_LABELS = {
    "Does an AI reply increase subsequent user interactions?": "收到人工智能回复是否提高用户后续互动？",
    "Does receiving an AI reply change follow-up interactions?": "收到人工智能回复是否改变随访窗口内的互动量？",
    "Does randomized assignment change seven-day retention?": "随机分配的干预是否改变七日结果指标？",
    "Does observational treatment change the measured outcome?": "观察性干预是否改变所测量的结果？",
    "What is the causal effect of the selected treatment on the selected outcome?": "所选干预对所选结果的因果效应是什么？",
}
DIAGNOSTIC_LABELS = {
    "conditional_pair_variance": "匹配配对差方差检查",
    "aipw_score_identity":"AIPW得分复算一致性", "aipw_clipping_share":"倾向得分截断比例",
    "baseline_balance_not_assessed":"基线协变量平衡检查（未实施）",
    'clustered_regression_groups':'聚类数量检查','regression_finite_inference':'估计与推断数值检查',
    'unverified_identification':'未验证的识别条件',
    "common_treatment_timing": "共同处理时点适用性",
    "parallel_trends_joint_test": "处理前系数联合检验",
    "treated_and_control_entities": "处理组与从未处理组数量",
    "common_support": "共同支撑区间覆盖率",
    "treated_match_rate": "处理组匹配保留率",
    "maximum_absolute_smd_after_matching": "匹配后最大绝对标准化均值差",
    "propensity_overlap_005_095": "倾向得分重叠比例",
    "maximum_absolute_weighted_smd": "加权后最大绝对标准化均值差",
    "maximum_inverse_probability_weight": "最大逆概率权重",
    "cross_fitting_folds": "交叉拟合折数",
    "out_of_fold_propensity_overlap_005_095": "样本外倾向得分重叠比例",
    "randomized_group_sizes": "随机实验分组样本量",
    "maximum_absolute_covariate_smd": "基线协变量最大绝对标准化均值差",
    "cuped_variance_reduction": "基线调整后的方差降低比例",
}
MESSAGES = {
    "Zero matched-pair variance does not justify a zero p-value or a zero-width interval.": "匹配配对差方差为零时，不能据此报告零P值或零宽置信区间。",
    "Multiple treatment dates require a staggered-adoption estimator before causal interpretation.": "存在多个处理日期，作因果解释前需采用合适的交错处理估计方法。",
    "No estimable pre-treatment event-time indicators were available.": "没有可估计的处理前事件时间指标，无法进行联合检验。",
    "Pre-treatment indicators were absorbed by the fixed effects.": "处理前指标被固定效应吸收，无法进行联合检验。",
    "Pre-treatment coefficient covariance is singular; the joint test is not estimable.": "处理前系数协方差矩阵奇异，无法可靠计算联合检验。",
    "Failed to reject jointly zero pre-treatment coefficients; this supports but does not prove parallel trends.": "未拒绝处理前系数联合为零；未发现显著处理前差异，但不能据此证明平行趋势。",
    "Pre-treatment coefficients are jointly significant; causal DID interpretation is blocked.": "处理前系数联合显著，当前双重差分结果不能作因果解释。",
    "Both treated and never-treated entities are present.": "样本同时包含处理用户和从未处理用户。",
    "Share of treated observations inside the empirical common-support interval.": "处理组中位于经验共同支撑区间内的观测比例。",
    "Share of treated observations retained in 1:1 matching.": "一对一匹配后保留的处理组观测比例。",
    "Maximum absolute standardized mean difference after matching.": "匹配后各协变量绝对标准化均值差的最大值。",
    "Share of observations with propensity scores between 0.05 and 0.95.": "倾向得分位于0.05至0.95之间的观测比例。",
    "Maximum absolute weighted standardized mean difference.": "加权后各协变量绝对标准化均值差的最大值。",
    "Large inverse-probability weights indicate practical positivity problems.": "过大的逆概率权重提示实际重叠性不足。",
    "Number of cross-fitting folds used by DoubleML.": "双重机器学习采用的交叉拟合折数。",
    "Overlap measured using out-of-fold treatment probabilities.": "使用样本外处理概率衡量的重叠情况。",
    "Both randomized groups are represented.": "随机实验的两个组均有样本。",
    "Randomization balance check; imbalance is a warning, not automatic proof of invalid randomization.": "随机化基线平衡检查；不平衡会提示风险，但不能单独证明随机化失效。",
    "Relative outcome variance reduction after adjustment with pre-treatment covariates.": "使用处理前协变量调整后，结果方差相对降低的比例。",
    "Baseline balance of CUPED covariates.": "方差缩减所用处理前协变量的基线平衡情况。",
    "Failure to reject pre-trends is not proof of parallel trends; substantive justification is still required.": "处理前系数不显著不能证明平行趋势，仍需研究设计和业务事实支持。",
    "Treatment timing is staggered. TWFE can be biased under heterogeneous treatment effects; use a staggered-adoption estimator before making a final causal claim.": "存在交错处理时点。处理效应异质时，传统双向固定效应估计可能有偏；作因果解释前应采用合适的交错处理估计方法。",
    "The pre-trend diagnostic failed; the effect must not be described as causal.": "处理前趋势诊断未通过，当前估计不得表述为因果效应。",
    "PSM adjusts only for observed pre-treatment covariates; unmeasured confounding remains possible.": "倾向得分匹配仅调整已观察的处理前协变量，仍可能存在未观察混杂。",
    "The paired-difference standard error is conditional on the estimated match and does not account for propensity-score estimation; use design-appropriate matching inference for confirmatory claims.": "配对差标准误以已估计匹配为条件，未计入倾向得分估计的不确定性；确认性结论需采用适合该匹配设计的推断方法。",
    "At least one PSM quality diagnostic failed; do not make a causal claim.": "至少一项匹配质量诊断未通过，当前不能作因果解释。",
    "IPW relies on correct propensity specification and no unmeasured confounding.": "逆概率加权依赖正确的倾向得分模型设定和无未观察混杂假设。",
    "At least one IPW diagnostic failed; do not make a causal claim.": "至少一项逆概率加权诊断未通过，当前不能作因果解释。",
    "DoubleML reduces regularization bias through cross-fitting but still requires valid confounder selection, overlap, and no unmeasured confounding.": "双重机器学习通过交叉拟合降低正则化偏差，仍需合理选择混杂变量、满足重叠性及无未观察混杂假设。",
    "DoubleML overlap diagnostics failed; do not make a causal claim.": "双重机器学习重叠性诊断未通过，当前不能作因果解释。",
    "Observed baseline imbalance exceeds the conventional 0.10 SMD threshold.": "观察到的基线不平衡超过常用的标准化均值差0.10阈值。",
    "CUPED increased variance; prefer the unadjusted A/B estimate.": "基线调整后方差反而增加，建议优先采用未经调整的随机实验估计。",
}
ESTIMAND_LABELS = {
    'Cluster-adjusted conditional linear association':'按用户聚类的条件线性关联',
    "TWFE DID coefficient on post-treatment exposure": "双向固定效应双重差分的处理后暴露系数",
    "ATT among 1:1 propensity-score matched treated observations": "一对一倾向得分匹配后处理组平均效应",
    "Hájek-normalized inverse-probability-weighted ATE": "经归一化逆概率加权的平均处理效应",
    "DoubleML partially linear regression coefficient": "双重机器学习部分线性回归系数",
    "Intent-to-treat difference in means": "按随机分配组计算的意向处理均值差",
    "CUPED-adjusted intent-to-treat difference in means": "使用基线方差缩减调整的意向处理均值差",
}
CHECK_LABELS = {
    "descriptive_fallback": "描述性分析可用性", "randomized_assignment": "随机分配声明",
    "randomization_unit": "随机化单位", "pre_treatment_outcome": "处理前结果",
    "panel_structure": "纵向数据结构", "treatment_timing": "处理时点",
    "pre_post_windows": "处理前后窗口", "parallel_trends": "平行趋势声明",
    "strict_exogeneity": "严格外生性", "pre_treatment_covariates": "处理前协变量",
    "conditional_exchangeability": "条件可交换性声明", "positivity_overlap": "重叠性声明",
    "domain_pack": "领域约束",
}
CHECK_MESSAGES = {
    "Zero matched-pair variance does not justify a zero p-value or a zero-width interval.": "匹配配对差方差为零时，不能据此报告零P值或零宽置信区间。",
    "pass": "该项前置结构或声明已具备；识别假设仍需后续诊断与人工判断。",
    "needs_review": "该项仍需补充定义、研究依据或人工声明。",
    "blocked": "该项缺失或与方法要求不符，需完善研究设计后继续。",
}
EVIDENCE_LABELS = {
    "missing_columns": "缺少字段", "missing_entity_rows": "实体缺失行数",
    "invalid_time_rows": "日期无效行数", "missing_outcome_rows": "结果缺失行数",
    "duplicate_rows": "重复行数", "users_with_multiple_treatment_dates": "首次处理日期不一致用户数",
    "treated_users": "处理用户数", "never_treated_users": "从未处理用户数",
    "distinct_treatment_dates": "不同处理日期数", "staggered_adoption": "存在交错处理",
    "pre_days": "处理前相对日", "post_days": "处理后相对日",
    "complete_pre_window_users": "完整前窗用户数", "complete_post_window_users": "完整后窗用户数",
    "pre_outcome_complete_users": "前窗结果完整用户数", "pre_outcome_complete_rate": "前窗结果完整比例",
    "complete_users": "完整用户数", "missing_covariates": "缺少协变量",
    "covariates_varying_within_user": "用户内变化的协变量", "treated_range": "处理组范围",
    "control_range": "对照组范围", "range_overlap": "范围存在重叠",
    "automatic_verification": "已自动验证", "declared_cluster": "声明的聚类字段",
    "user_clusters": "用户聚类数", "calendar_dates": "日历日期数",
}


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def claim_label_zh(value: Any) -> str:
    return CLAIM_LABELS.get(_value(value), "待确认的结论等级")


def status_label_zh(value: Any) -> str:
    return STATUS_LABELS.get(_value(value), "待确认")


def domain_label_zh(value: Any) -> str:
    return DOMAIN_LABELS.get(_value(value), "其他领域")


def field_label_zh(value: str) -> str:
    return FIELD_LABELS.get(value, value)


def unit_label_zh(value: str) -> str:
    return UNIT_LABELS.get(value, value)


def research_question_zh(value: str) -> str:
    return QUESTION_LABELS.get(value, value)


def assumption_label_zh(value: str) -> str:
    return ASSUMPTION_LABELS.get(value, value)


def diagnostic_label_zh(value: str) -> str:
    return DIAGNOSTIC_LABELS.get(value, "补充方法诊断")


def message_zh(value: str) -> str:
    prefix = "Time-invariant covariates were absorbed by entity fixed effects and omitted: "
    if value.startswith(prefix):
        names = "、".join(field_label_zh(item.strip()) for item in value[len(prefix):].split(","))
        return "以下时间不变协变量被个体固定效应吸收，未单独估计系数：" + names
    return MESSAGES.get(value, value)


def display_value_zh(value: Any) -> str:
    if value is None:
        return "未设置"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.6g}"
    text = str(value)
    text = text.replace("not_estimable", "无法估计").replace("absorbed", "被固定效应吸收")
    return text.replace("treated=", "处理组=").replace("control=", "对照组=")


def format_p_value_zh(value: float | None) -> str:
    if value is None:
        return "未计算"
    if value == 0:
        return "数值舍入为0"
    return f"{value:.4g}"


def evidence_zh(value: Any) -> Any:
    if isinstance(value, dict):
        return {EVIDENCE_LABELS.get(str(k), field_label_zh(str(k))): evidence_zh(v) for k, v in value.items()}
    if isinstance(value, list):
        return [evidence_zh(item) for item in value]
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "未设置"
    if isinstance(value, str):
        return field_label_zh(value)
    return value


def diagnostic_rows_zh(diagnostics: Any) -> list[dict[str, str]]:
    return [
        {"诊断项目": ("基线协变量平衡检查" if item.name=="baseline_balance_not_assessed" else diagnostic_label_zh(item.name)), "是否通过": "未实施" if item.name=="baseline_balance_not_assessed" else "是" if item.passed else "否",
         "数值": display_value_zh(item.value),
         "判定标准": display_value_zh(item.threshold).replace("p >=", "概率值 ≥").replace(">=", "≥").replace("<=", "≤").replace(" of treated observations", "的处理组观测"),
         "诊断说明": message_zh(item.message), "是否限制因果主张": "是" if item.claim_blocking else "否"}
        for item in diagnostics
    ]


def estimand_label_zh(value: str) -> str:
    return ESTIMAND_LABELS.get(value, value)


def diagnostics_for_display(bundle):
    if bundle.plan.selected_method.value != 'ab_test' or bundle.spec.covariates:
        return bundle.diagnostics
    return [x.model_copy(update={'name':'baseline_balance_not_assessed','passed':False,'value':None,'threshold':None,
             'message':'未指定基线协变量，本次未实施协变量平衡检查；历史原始诊断保留。','claim_blocking':False})
            if x.name=='maximum_absolute_covariate_smd' else x for x in bundle.diagnostics]
