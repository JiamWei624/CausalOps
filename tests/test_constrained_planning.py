"""Constrained candidates, exact bindings, no model authority; real tools for execution."""
import copy
import json
import pytest
from test_configurable_research import co,config,data,approve
from causalops.general.service import DesignError

def task(co,**kw):
    changes=kw.pop('configuration',{})
    return co.create_configurable(data().to_csv(index=False).encode(),name='user.csv',configuration=config(**changes),request_id=kw.pop('request_id','stage2'),human_confirmed=True,stage2=True,**kw)


def test_stage2_unknown_is_complete_descriptive_path_without_effect_run(co):
    t=task(co,configuration=dict(assignment='unknown',design_evidence='',source_confirmed=False))
    assert t['plan']['schema_version']=='configurable-research-stage2'
    assert [x['step_id'] for x in t['plan']['steps']]==['S01','S02','S03','S05']
    r=approve(co,t);assert not r['facts']
    assert co.run(t['id'])['status']=='completed'
    manifest=co.report(t['id']);assert manifest['status']=='descriptive_complete'
    assert len(manifest['source_runs'])==1 and manifest.get('effect') is None
    from causalops.application.diagnostics.reports import DiagnosticReportService
    report=DiagnosticReportService(co.s).post_run(t['id'],session_id=t['session_id'])
    status={x.rule.id:x.status for x in report.quality.findings}
    assert status['PD-02']=='unknown' and status['PD-07']=='not_applicable'
    assert status['PD-09']=='verified' and status['PD-14']=='verified'
    assert report.results.descriptive['difference_pp']==pytest.approx(100/6)
    assert report.results.effect is None and len(report.results.runs)==1


def test_deterministic_candidate_adoption_has_no_approval(co):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co)
    r=svc.template(t['id']);assert r['status']=='validated' and r['source']=='deterministic'
    assert r['candidate']['execution_authorized'] is False
    with pytest.raises(DesignError):svc.adopt(t['id'],r['id'],human_confirmed=False)
    newer=svc.adopt(t['id'],r['id'],human_confirmed=True)
    assert newer['status']=='candidate' and newer['plan']['candidate_ref']['id']==r['id']
    assert svc.adopt(t['id'],r['id'],human_confirmed=True)['id']==newer['id']
    with pytest.raises(DesignError):co.advance(newer['id'])
    approve(co,newer);assert co.run(newer['id'])['status']=='completed'


@pytest.mark.parametrize('fault',['method','field','randomization','authority','dependency','objective','extra_tool'])
def test_model_illegal_candidates_are_rejected_deterministically(co,fault):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co,configuration=dict(assignment='unknown',design_evidence='',source_confirmed=False)) if fault=='randomization' else task(co)
    svc=CandidatePlanning(co);raw=copy.deepcopy(svc.template(t['id'])['candidate'])
    if fault=='method':raw['steps'][1]['method']='imaginary_method'
    elif fault=='field':raw['field_bindings']['outcome']='absent'
    elif fault=='randomization':raw['declared_assignment']='randomized';raw['research_type']='randomized_two_arm_binary'
    elif fault=='authority':raw['execution_authorized']=True
    elif fault=='dependency':raw['steps'][-1]['depends_on']=[]
    elif fault=='objective':raw['objective']='修改已经确认的研究目标，不重新批准'
    else:raw['steps'].append({**raw['steps'][0],'step_id':'RUN_PYTHON'})
    r=svc.validate(t['id'],raw,source='simulated_model')
    assert r['status']=='rejected' and r['error_code']
    with pytest.raises(DesignError):svc.adopt(t['id'],r['id'],human_confirmed=True)
    with co.ws.connection() as db:
        assert db.execute('SELECT count(*) FROM automation_v2_approvals').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM analysis_runs').fetchone()[0]==0


def test_approved_or_changed_scope_cannot_be_planned_or_adopted(co):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co);r=svc.template(t['id']);approve(co,t)
    with pytest.raises(DesignError):svc.adopt(t['id'],r['id'],human_confirmed=True)
    with pytest.raises(DesignError):svc.template(t['id'])


def test_real_transport_mock_budget_and_consent(co):
    import httpx
    from causalops.application.constrained_planning import CandidatePlanning
    from causalops.llm.providers import ProviderConfig,StructuredModelClient
    t=task(co);svc=CandidatePlanning(co);raw=svc.template(t['id'])['candidate'];cfg=ProviderConfig()
    def response(req):
        body=json.loads(req.content);assert 'user.csv' not in req.content.decode() and 'subject,arm' not in req.content.decode()
        return httpx.Response(200,json={'id':'simulated-response','status':'completed','model':cfg.model,'output_text':json.dumps(raw),'usage':{'input_tokens':100,'output_tokens':200,'total_tokens':300}})
    with httpx.Client(transport=httpx.MockTransport(response)) as transport:
        client=StructuredModelClient(cfg,'test-placeholder',client=transport)
        with pytest.raises(DesignError):svc.model_candidate(t['id'],client,payload_sha=svc.payload_sha(t['id']),human_confirmed=False)
        co.a.consent(t['session_id'],True,cfg)
        r=svc.model_candidate(t['id'],client,payload_sha=svc.payload_sha(t['id']),human_confirmed=True)
        assert r['status']=='validated'
        assert co.budget(t['id'])['physical_requests']==1
        assert co.budget(t['id'])['input_tokens']==100
        assert co.task(t['id'])['status']=='candidate'
        assert svc.template(t['id'])['status']=='validated'


def test_invalid_model_schema_and_unavailable_model_allow_explicit_template(co):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co)
    assert svc.template(t['id'])['status']=='validated'
    with pytest.raises(DesignError):svc.model_candidate(t['id'],None,payload_sha=svc.payload_sha(t['id']),human_confirmed=True)
    assert co.task(t['id'])['status']=='candidate'


def test_payload_changed_since_user_review_blocks_before_request(co):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co)
    with pytest.raises(DesignError):svc.model_candidate(t['id'],None,payload_sha='0'*64,human_confirmed=True)
    assert co.budget(t['id'])['physical_requests']==0

def test_budget_exhaustion_does_not_reset_model_allowance_via_fallback(co):
    import httpx
    from causalops.application.constrained_planning import CandidatePlanning
    from causalops.llm.providers import ProviderConfig,StructuredModelClient
    t=task(co);svc=CandidatePlanning(co);cfg=ProviderConfig();ledger=co._init_control(t['id']);seen=[]
    for _ in range(12):ledger.reserve_model('controlled_reservation',cfg.model_dump(),1)
    co.a.consent(t['session_id'],True,cfg)
    with httpx.Client(transport=httpx.MockTransport(lambda r:seen.append(r))) as transport:
        client=StructuredModelClient(cfg,'test-placeholder',client=transport)
        r=svc.model_candidate(t['id'],client,payload_sha=svc.payload_sha(t['id']),human_confirmed=True)
    assert r['status']=='failed' and not seen
    assert co.task(t['id'])['status']=='paused' and co.budget(t['id'])['physical_requests']==12
    with pytest.raises(DesignError):svc.fallback(t['id'],human_confirmed=False)
    newer=svc.fallback(t['id'],human_confirmed=True)
    assert newer['status']=='candidate' and newer['plan']['candidate_ref']
    assert svc.get(t['id'],newer['plan']['candidate_ref']['id'])['source']=='deterministic'
    assert co.budget(t['id'])['physical_requests']==12
    with pytest.raises(DesignError):svc.model_candidate(newer['id'],None,payload_sha='0'*64,human_confirmed=True)
    approve(co,newer);assert co.run(newer['id'])['status']=='completed'


def test_transport_keeps_invalid_proposal_and_template_is_not_silent_substitute(co):
    import httpx
    from causalops.application.constrained_planning import CandidatePlanning
    from causalops.llm.providers import ProviderConfig,StructuredModelClient
    t=task(co);svc=CandidatePlanning(co);cfg=ProviderConfig();raw=svc.template(t['id'])['candidate'];raw['steps'][1]['method']='not_registered'
    def response(req):return httpx.Response(200,json={'status':'completed','output_text':json.dumps(raw),'model':cfg.model,'usage':{'input_tokens':1,'output_tokens':2}})
    co.a.consent(t['session_id'],True,cfg)
    with httpx.Client(transport=httpx.MockTransport(response)) as transport:
        r=svc.model_candidate(t['id'],StructuredModelClient(cfg,'test-placeholder',client=transport),payload_sha=svc.payload_sha(t['id']),human_confirmed=True)
    assert r['status']=='rejected' and r['raw']['steps'][1]['method']=='not_registered'
    assert r['request_refs'] and co.task(t['id'])['status']=='candidate'
    assert svc.template(t['id'])['status']=='validated'
    with co.ws.connection() as db:assert db.execute('SELECT count(*) FROM automation_v2_approvals').fetchone()[0]==0

@pytest.mark.parametrize('bad_id',[None,'../../outside'])
def test_candidate_identity_rejected_before_opening_lock_file(co,bad_id):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co)
    with pytest.raises(DesignError):svc.adopt(t['id'],bad_id,human_confirmed=True)


def test_approval_race_cannot_be_superseded_by_candidate_adoption(co,monkeypatch):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co);r=svc.template(t['id']);original=co.revise_configurable
    def racing(tid,**kw):
        approve(co,t)
        return original(tid,**kw)
    monkeypatch.setattr(co,'revise_configurable',racing)
    with pytest.raises(DesignError):svc.adopt(t['id'],r['id'],human_confirmed=True)
    assert co.task(t['id'])['status']=='approved'
    with co.ws.connection() as db:assert db.execute('SELECT count(*) FROM automation_v2_tasks').fetchone()[0]==1


def test_changed_contract_cannot_use_previous_payload_consent(co):
    import httpx
    from causalops.application.constrained_planning import CandidatePlanning
    from causalops.llm.providers import ProviderConfig,StructuredModelClient
    t=task(co);svc=CandidatePlanning(co);payload=svc.payload_sha(t['id']);cfg=ProviderConfig();co.a.consent(t['session_id'],True,cfg);row=co.s.contracts.latest(t['session_id'])
    co.s.contracts.save(t['session_id'],{**row['body'],'metric_window':'another window'},expected_sha=row['sha'],human_confirmed=True)
    seen=[]
    with httpx.Client(transport=httpx.MockTransport(lambda r:seen.append(r))) as transport:
        with pytest.raises(DesignError):svc.model_candidate(t['id'],StructuredModelClient(cfg,'test-placeholder',client=transport),payload_sha=payload,human_confirmed=True)
    assert not seen and co.budget(t['id'])['physical_requests']==0

def test_model_proposal_may_choose_safe_description_without_changing_registered_facts(co):
    from causalops.application.constrained_planning import CandidatePlanning,canonical
    from causalops.application.configurable_research import parse_plan
    from causalops.application.diagnostics.reports import DiagnosticReportService
    t=task(co);svc=CandidatePlanning(co)
    raw=canonical(parse_plan(t['plan']),'descriptive_binary').model_dump(mode='json')
    r=svc.validate(t['id'],raw,source='simulated_model');u=svc.adopt(t['id'],r['id'],human_confirmed=True)
    assert len(u['plan']['steps'])==4 and u['plan']['configuration']['assignment']=='randomized'
    approve(co,u);co.run(u['id']);assert len(co.report(u['id'])['source_runs'])==1
    report=DiagnosticReportService(co.s).post_run(u['id'],session_id=u['session_id'])
    assert report.context.scope.statistic_type=='descriptive_group_proportions'
    assert report.results.effect is None


def test_unbacked_model_origin_cannot_be_marked_validated(co):
    from causalops.application.constrained_planning import CandidatePlanning
    t=task(co);svc=CandidatePlanning(co);raw=svc.template(t['id'])['candidate']
    r=svc.validate(t['id'],raw,source='model_assisted',request_refs=['0'*32],request_payload_sha='0'*64)
    assert r['status']=='rejected' and r['error_code']=='model_request_receipt_missing'
