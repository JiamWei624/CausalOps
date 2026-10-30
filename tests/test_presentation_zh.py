from causalops.demo_data import get_demo_scenarios
from causalops.execution import execute_analysis
from causalops.metadata.presentation_zh import diagnostic_rows_zh, format_p_value_zh
from causalops.reporting import render_markdown_report


def test_supported_estimators_have_chinese_diagnostics_and_reports(tmp_path):
    for index, scenario in enumerate(get_demo_scenarios().values()):
        bundle = execute_analysis(scenario.frame, scenario.spec, tmp_path / str(index))
        rows = diagnostic_rows_zh(bundle.diagnostics)
        assert rows
        assert all(set(r) == {"诊断项目", "是否通过", "数值", "判定标准", "诊断说明", "是否限制因果主张"} for r in rows)
        assert all(r["诊断项目"] != "补充方法诊断" for r in rows)
        assert all(any("\u4e00" <= c <= "\u9fff" for c in r["诊断说明"]) for r in rows)
        report = render_markdown_report(bundle)
        for phrase in ("associational", "Pre-treatment coefficients", "Time-invariant covariates", "Both treated"):
            assert phrase not in report
        assert "- 当前主张等级：" in report


def test_zero_probability_is_explained_as_numerical_rounding():
    assert format_p_value_zh(0) == "数值舍入为0"
    assert format_p_value_zh(None) == "未计算"
    assert format_p_value_zh(0.025) == "0.025"
