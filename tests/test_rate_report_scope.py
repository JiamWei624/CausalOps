from types import SimpleNamespace as Obj
import pytest

from causalops.application.report_scope import scope_message, unit_answer
from causalops.results.rate_units import rate_contrast


def bundle(control, treated, *, kind="binary", method="ab_test", delta=None):
    diff = treated-control if delta is None else delta
    return Obj(plan=Obj(selected_method=Obj(value=method)),spec=Obj(outcome="visit"),
               estimate=Obj(estimate=diff, sample_size=20, confidence_interval=(diff-.01,diff+.01)),
               evidence={"interpretation_inputs":{"complete_case_rows":20, "metric_definition":{"kind":kind},
                         "outcome_binary_observed":True,"baseline_scope":"same_complete_case_raw_groups",
                         "raw_group_summary":[{"treatment":0,"n":10,"outcome_mean":control},
                                              {"treatment":1,"n":10,"outcome_mean":treated}]}})


def test_risk_difference_signed_scales():
    units=rate_contrast(bundle(.5,.4))
    assert units["pp"] == pytest.approx(-10)
    assert units["relative_pct"] == pytest.approx(-20)
    assert units["ci_pp"] == pytest.approx([-11,-9])


def test_undefined_relative_change():
    units=rate_contrast(bundle(0,.2))
    assert units["relative_pct"] is None
    assert units["pp"] == 20


@pytest.mark.parametrize("options",[{"method":"logit"},{"kind":"continuous"},{"kind":"count"},{"delta":.09}])
def test_no_conversion_without_matching_estimand(options):
    assert rate_contrast(bundle(.2,.3,**options)) is None


def test_estimator_sample_must_match():
    b=bundle(.2,.3)
    b.estimate.sample_size=19
    assert rate_contrast(b) is None


def test_old_report_scope():
    scopes=[("两周购买率","分配后两周")]
    reason=scope_message("明年增加了多少净利润？",scopes)
    assert all(word in reason for word in ["两周购买率","成本","明年","跟踪数据"])
    assert scope_message("访问率是多少个百分点？",scopes)
    assert scope_message("购买率是多少个百分点？",scopes) == ""


def test_no_unit_answer_for_unrelated_run():
    assert unit_answer({},{"run_id":"other"},"两周访问率","分配后两周") is None
