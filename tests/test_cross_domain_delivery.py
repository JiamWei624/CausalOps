from causalops.demo_domains import synthetic_scenario
from causalops.execution import execute_analysis
from causalops.results.narrative import conclusion_sections
from causalops.visualization import build_regression_diagnostic_figures
from causalops.results.evidence import build_run_evidence,select_question_evidence
from causalops.results.qa import answer_contract


def test_continuous_domain_charts_do_not_claim_probability_or_ai_reply(tmp_path):
 frame,spec,_=synthetic_scenario('hidden_confounding',8913)
 bundle=execute_analysis(frame,spec,tmp_path,execution_scope='association_only',data_kind='synthetic')
 charts=build_regression_diagnostic_figures(bundle)
 raw=''.join(f.to_json() for f in charts.values())
 assert '再次互动概率' not in raw and '回复状态' not in raw
 assert all(f.layout.yaxis.tickformat!='.0%' for f in charts.values())
 assert '发帖' not in str(conclusion_sections(bundle))
 assert 'AI回复' not in str(conclusion_sections(bundle))


def test_non_did_question_context_omits_irrelevant_trend_rules(tmp_path):
 frame,spec,_=synthetic_scenario('ab',8913)
 bundle=execute_analysis(frame,spec,tmp_path,data_kind='synthetic')
 snapshot=build_run_evidence(bundle)
 ids={f['evidence_id'] for f in select_question_evidence(snapshot,'点估计的单位是什么？')}
 assert 'M001' not in ids and 'M002' not in ids
 assert {'E003','E010'}<=set(answer_contract('点估计单位是什么？',snapshot)['required_evidence'])
 assert 'E002' in answer_contract('交叉拟合的方法是什么？',snapshot)['required_evidence']