import pandas as pd
import pytest
from causalops.general.exploration import ExplorationDesign, compute
from causalops.general.exploration_report import figures, render_report
from causalops.ui.assistant_app import primary_chart_key


@pytest.mark.parametrize("values", [[1., 4., 3., None, float("inf")], [1., 1., 1., None, float("inf")]])
def test_two_variable_report_uses_saved_paired_evidence(values):
    data = pd.DataFrame({"x": range(5), "y": values})
    design = ExplorationDesign(question="分析两个变量的相关程度", method="correlation", numeric=["x", "y"])
    bundle = compute(data, design)
    bundle["design_version"] = 1
    pair = bundle["summary"]["correlations"][0]
    charts = figures(bundle)
    key = primary_chart_key(bundle, None, charts)
    assert key == next(iter(charts)) == "两变量相关系数"
    assert "相关矩阵" not in charts
    assert pair["pairwise_n"] == 3
    assert "成对有效样本 3" in charts[key].layout.title.text
    if pair["pearson"] is None:
        assert not charts[key].data
        assert "未计算" in bundle["conclusions"][1]
    else:
        assert list(charts[key].data[0].x) == pytest.approx([pair["pearson"], pair["spearman"]])
        assert "Pearson" in bundle["conclusions"][1]
    report = render_report(bundle)
    assert report.index("结论与下一步") < report.index("图表（由保存汇总数据绘制）") < report.index("<h2>数据质量")

def test_uploaded_data_requires_explicit_design():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string("""
import pandas as pd
import streamlit as st
from causalops.ui.app import _request_initial_spec
spec = _request_initial_spec(pd.DataFrame({'record_id':[1], 'score':[4]}), 'sample')
if spec: st.success(spec.analysis_unit)
""").run()
    assert not app.exception and all(w.value is None for w in app.selectbox)
    app.button[0].click().run()
    assert app.error and not app.success
    app.text_input[0].set_value('样本分组与观测得分的关系如何')
    app.text_input[1].set_value('检测样本')
    app.selectbox[0].select('score')
    app.selectbox[1].select('score')
    app.button[0].click().run()
    assert app.error and not app.success
    app.selectbox[0].select('record_id')
    app.button[0].click().run()
    assert not app.exception and app.success[0].value == '检测样本'
