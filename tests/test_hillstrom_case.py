from io import BytesIO
import os
from pathlib import Path

import pandas as pd
import pytest

from causalops.sample_data.hillstrom import COUNTS, cohort


def test_marketing_case_rejects_unknown_source():
    with pytest.raises(ValueError, match='公开实验'):
        cohort(b'not the verified archive')


def test_marketing_real_source_counts():
    location = os.environ.get('CAUSALOPS_HILLSTROM_ARCHIVE')
    if not location:
        pytest.skip('Set CAUSALOPS_HILLSTROM_ARCHIVE to run the real-source check')
    data = pd.read_csv(BytesIO(cohort(Path(location).read_bytes())))
    assert data.entity_id.is_unique
    assert len(data) == 42613
    for group, label in enumerate(('未发邮件', '男装邮件')):
        values = data.loc[data.assigned == group, 'visit']
        assert (values.sum(), len(values)) == COUNTS[label]

def test_real_case_approval_report_and_followup(tmp_path):
    import math
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace
    from causalops.sample_data.hillstrom import contract, QUESTION
    from causalops.results.rate_units import rate_contrast
    from causalops.ui.assistant_app import make_report
    from causalops.application.task_conclusions import build_task_conclusion

    location = os.environ.get('CAUSALOPS_HILLSTROM_ARCHIVE')
    if not location:
        pytest.skip('Real source archive required')
    a = AssistantWorkspace(GeneralWorkspace(tmp_path))
    service = ResearchService(a)
    sid = service.create_task(payload=cohort(Path(location).read_bytes()), name='case.csv', title='公开营销实验')
    service.contracts.save(sid, contract(), expected_sha=None, human_confirmed=True)
    f = service.start(sid, QUESTION, mode='plan')
    assert f['status']=='awaiting_review' and not a.completed_runs(sid)
    p = a.get_plan(f['plan_id'])
    service.review(f['id'], accept=True, expected_plan_id=p['id'], expected_plan_sha=p['sha'],
                   expected_data_sha=f['request']['data']['frame_sha'], human_confirmed=True,
                   use_contract_facts=True, dispatch=True)
    ref = next(r for r in a.completed_runs(sid) if r['method']=='ab_test')
    rid = ref['run_id']
    b, _ = a.ws.bundle(rid)
    rates = rate_contrast(b)
    c, t = 2262/21306, 3894/21307
    assert rates['pp'] == pytest.approx(100*(t-c))
    assert b.estimate.standard_error == pytest.approx(math.sqrt(c*(1-c)/(21306-1)+t*(1-t)/(21307-1)),rel=1e-4)
    report = make_report(a, ref, sid, build_task_conclusion(a, sid, rid))
    assert '7.66' in report and '18.28%' in report and '10.62%' in report
    before = len(a.completed_runs(sid))
    qa = service.start(sid, '解释当前报告，两周访问率差是多少个百分点？', mode='results',run_ids=[rid])
    answer = service.output(qa['id'], 'answer')
    assert rid in answer['run_ids'] and answer['facts'] and len(a.completed_runs(sid))==before
