import json
from pathlib import Path
import pytest
import pandas as pd
from causalops.agent import CausalOpsAgent
from causalops.schemas import CausalSpec,ClaimLevel
from causalops.ui.showcase_support import checked_route,safe_error,source_fingerprint,overview_numbers,conclusion_figures,read_real_run

@pytest.fixture
def display_bundle(tmp_path):
    f=pd.DataFrame({'id':range(100),'t':[0]*50+[1]*50,'y':[1]*10+[0]*40+[1]*30+[0]*20})
    s=CausalSpec(question='随机营销邮件对两周访问的影响',domain='generic',analysis_unit='customer',treatment='t',outcome='y',entity_id_column='id',candidate_methods=['ab_test'],assignment_mechanism='randomized')
    return CausalOpsAgent().run(f,s,tmp_path/'runs',data_kind='synthetic',study_context={'metric_definition':{'label':'访问概率','unit':'概率','kind':'binary','window':'两周','direction':'higher_is_better'}}).bundle

def test_route_rejects_arbitrary_input():
    assert checked_route('experiment')=='experiment'
    assert checked_route('../../secret')=='home'

def test_fault_hint_never_echoes_exception_payload():
    payload='private-question and credential'
    hint=safe_error(ValueError(payload))
    assert payload not in json.dumps(hint)
    assert hint['action']

def test_fingerprint_detects_module_update(tmp_path):
    p=tmp_path/'src/causalops';p.mkdir(parents=True);a=p/'x.py';a.write_text('a=1')
    first=source_fingerprint(tmp_path);a.write_text('a=2')
    assert source_fingerprint(tmp_path)!=first

def test_binary_chart_uses_percentage_points_and_keeps_zero(display_bundle):
    before=display_bundle.model_dump_json();n=overview_numbers(display_bundle)
    assert n['estimate']==pytest.approx(40)
    figs=conclusion_figures(display_bundle)
    f=figs['幅度与不确定性']
    assert f.data[0].x[0]==pytest.approx(40)
    assert f.layout.xaxis.range[0]<0<f.layout.xaxis.range[1]
    assert display_bundle.model_dump_json()==before

def test_chart_does_not_upgrade_claim(display_bundle):
    b=display_bundle.model_copy(deep=True);b.claim_level=ClaimLevel.ASSOCIATIONAL
    conclusion_figures(b)
    assert b.claim_level==ClaimLevel.ASSOCIATIONAL

def test_real_view_rejects_registry_mismatch(tmp_path,display_bundle):
    base=tmp_path/'artifacts/real-panel-20261030';e=base/'full/full_any/evidence';e.mkdir(parents=True)
    b=display_bundle.model_copy(deep=True);b.claim_level=ClaimLevel.ASSOCIATIONAL
    path=e/f'run-{b.run_id}.json';path.write_text(b.model_dump_json(),encoding='utf-8')
    (base/'full-summary.json').write_text(json.dumps({'results':[{'case_id':'full_any','run_id':b.run_id,'sample_size':1}]}),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='样本口径'):read_real_run(tmp_path)
    assert path.read_bytes()==before
