from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    DataStructure,
    DomainName,
)


@dataclass(frozen=True)
class DemoScenario:
    name: str
    description: str
    frame: pd.DataFrame
    spec: CausalSpec
    known_effect: float | None = None


def _randomized_frame(seed: int = 20261027, rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pre_metric = rng.normal(size=rows)
    assignment = rng.binomial(1, 0.5, rows)
    outcome = 1.2 * assignment + 0.9 * pre_metric + rng.normal(0, 0.8, rows)
    return pd.DataFrame(
        {
            "user_id": [f"r{index:06d}" for index in range(rows)],
            "assignment": assignment,
            "revenue": outcome,
            "pre_metric": pre_metric,
        }
    )


def _observational_frame(seed: int = 20261028, rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    propensity = 1 / (1 + np.exp(-0.7 * x1 + 0.35 * x2))
    treatment = rng.binomial(1, propensity)
    outcome = 1.7 * treatment + 0.8 * x1 - 0.35 * x2 + rng.normal(0, 0.7, rows)
    return pd.DataFrame({"treatment": treatment, "outcome": outcome, "x1": x1, "x2": x2})


def _did_frame(seed: int = 20261029, entities: int = 160, periods: int = 14) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    treatment_date = dates[7]
    entity_effect = rng.normal(0, 1, entities)
    rows: list[dict[str, object]] = []
    for entity in range(entities):
        treated = entity < entities // 2
        for period, date in enumerate(dates):
            post = treated and date >= treatment_date
            rows.append(
                {
                    "user_id": f"u{entity:04d}",
                    "event_date": date,
                    "first_ai_reply_date": treatment_date if treated else pd.NaT,
                    "ai_reply_received": int(post),
                    "baseline_activity": entity_effect[entity],
                    "total_interactions": entity_effect[entity]
                    + 0.08 * period
                    + 2.0 * int(post)
                    + rng.normal(0, 0.20),
                }
            )
    return pd.DataFrame(rows)


def _psm_frame(seed: int = 20261030, rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    baseline = rng.normal(size=rows)
    account_age = rng.integers(30, 1_500, size=rows)
    pre_activity = rng.poisson(np.exp(0.4 + 0.45 * baseline))
    propensity = 1 / (1 + np.exp(-(-0.4 + 0.7 * baseline + 0.08 * pre_activity)))
    treated = rng.binomial(1, propensity)
    outcome = (
        5.0 * treated
        + 2.2 * pre_activity
        + 1.5 * baseline
        + rng.normal(0, 3.0, rows)
    )
    return pd.DataFrame(
        {
            "user_id": [f"p{index:06d}" for index in range(rows)],
            "treated": treated,
            "post_total_interactions": outcome,
            "baseline_activity": baseline,
            "registration_age_days": account_age,
            "pre_total_interactions": pre_activity,
        }
    )


def get_demo_scenarios() -> dict[str, DemoScenario]:
    randomized = _randomized_frame()
    observational = _observational_frame()
    did = _did_frame()
    psm = _psm_frame()
    experiment_base = dict(
        question="Does randomized assignment change follow-up revenue?",
        domain=DomainName.EXPERIMENT,
        analysis_unit="user",
        treatment="assignment",
        outcome="revenue",
        entity_id_column="user_id",
        covariates=["pre_metric"],
        assignment_mechanism=AssignmentMechanism.RANDOMIZED,
        has_pre_treatment_outcome=True,
    )
    observational_base = dict(
        question="Does observational treatment change the measured outcome?",
        domain=DomainName.GENERIC,
        analysis_unit="user",
        treatment="treatment",
        outcome="outcome",
        covariates=["x1", "x2"],
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
        positivity_plausible=True,
        identification_assumptions=["conditional exchangeability given x1 and x2"],
    )
    return {
        "DID：AI回复与后续互动": DemoScenario(
            name="DID：AI回复与后续互动",
            description="共同处理时点面板数据；真实合成处理效应为2.0。",
            frame=did,
            spec=CausalSpec(
                question="Does an AI reply increase subsequent user interactions?",
                domain=DomainName.UGC,
                analysis_unit="user_day",
                treatment="ai_reply_received",
                outcome="total_interactions",
                time_column="event_date",
                entity_id_column="user_id",
                treatment_time_column="first_ai_reply_date",
                covariates=["baseline_activity"],
                candidate_methods=[CausalMethod.DID],
                identification_assumptions=["parallel_trends", "no_anticipation"],
                pre_period_days=7,
                post_period_days=6,
                cluster_column="user_id",
                assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
                data_structure=DataStructure.PANEL,
                parallel_trends_plausible=True,
            ),
            known_effect=2.0,
        ),
        "PSM：AI回复与随访窗互动": DemoScenario(
            name="PSM：AI回复与随访窗互动",
            description="一人一行的观测队列；真实合成ATT为5.0。",
            frame=psm,
            spec=CausalSpec(
                question="Does receiving an AI reply change follow-up interactions?",
                domain=DomainName.UGC,
                analysis_unit="user",
                treatment="treated",
                outcome="post_total_interactions",
                entity_id_column="user_id",
                covariates=[
                    "baseline_activity",
                    "registration_age_days",
                    "pre_total_interactions",
                ],
                candidate_methods=[CausalMethod.PSM],
                identification_assumptions=[
                    "conditional exchangeability given observed pre-treatment activity"
                ],
                assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
                data_structure=DataStructure.CROSS_SECTION,
                positivity_plausible=True,
            ),
            known_effect=5.0,
        ),
        "A/B实验": DemoScenario(
            name="A/B实验",
            description="随机实验均值差；真实合成效应为1.2。",
            frame=randomized,
            spec=CausalSpec(**experiment_base, candidate_methods=[CausalMethod.AB_TEST]),
            known_effect=1.2,
        ),
        "CUPED实验": DemoScenario(
            name="CUPED实验",
            description="使用处理前指标降方差；真实合成效应为1.2。",
            frame=randomized,
            spec=CausalSpec(**experiment_base, candidate_methods=[CausalMethod.CUPED]),
            known_effect=1.2,
        ),
        "IPW观测研究": DemoScenario(
            name="IPW观测研究",
            description="倾向得分加权ATE；真实合成效应为1.7。",
            frame=observational,
            spec=CausalSpec(**observational_base, candidate_methods=[CausalMethod.IPW]),
            known_effect=1.7,
        ),
        "DoubleML观测研究": DemoScenario(
            name="DoubleML观测研究",
            description="交叉拟合部分线性模型；真实合成效应为1.7。",
            frame=observational,
            spec=CausalSpec(**observational_base, candidate_methods=[CausalMethod.DOUBLE_ML]),
            known_effect=1.7,
        ),
    }
