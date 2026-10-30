from pathlib import Path

import pandas as pd
import pytest

from causalops.capabilities import METHOD_CAPABILITIES, get_method_capability
from causalops.execution import UnsupportedMethodExecutionError, execute_analysis
from causalops.schemas import CausalMethod, CausalSpec


def test_every_causal_method_has_one_capability_contract() -> None:
    assert set(METHOD_CAPABILITIES) == set(CausalMethod)
    assert all(capability.method == method for method, capability in METHOD_CAPABILITIES.items())


def test_executable_methods_match_the_validated_estimator_set() -> None:
    executable = {
        method for method, capability in METHOD_CAPABILITIES.items() if capability.executable
    }
    assert executable == {
        CausalMethod.AB_TEST,
        CausalMethod.CUPED,
        CausalMethod.PSM,
        CausalMethod.IPW,
        CausalMethod.AIPW,
        CausalMethod.DID,
        CausalMethod.DOUBLE_ML,
        CausalMethod.REGRESSION_ADJUSTMENT,
    }


def test_psm_contract_hides_time_and_parallel_trend_inputs() -> None:
    capability = get_method_capability(CausalMethod.PSM)
    assert capability.uses("covariates")
    assert capability.uses("positivity")
    assert not capability.uses("time_column")
    assert not capability.uses("treatment_time")
    assert not capability.uses("parallel_trends")
    assert not capability.uses("windows")


def test_unimplemented_method_fails_with_product_message(tmp_path: Path) -> None:
    frame = pd.DataFrame({"treated": [0, 1], "outcome": [1.0, 2.0]})
    spec = CausalSpec(
        question="Describe the observed difference between the two groups.",
        analysis_unit="user",
        treatment="treated",
        outcome="outcome",
        candidate_methods=[CausalMethod.DESCRIPTIVE],
    )

    with pytest.raises(UnsupportedMethodExecutionError, match="描述性分析执行器"):
        execute_analysis(frame, spec, tmp_path)

