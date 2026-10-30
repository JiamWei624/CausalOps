from copy import deepcopy

import pytest

from causalops.results.evidence import select_question_evidence
from causalops.results.qa import (CitationValidationError,answer_contract,
                                  validate_answer_contract,validate_and_render)


def real_snapshot():
    texts={'E004':'本次使用用户提供的数据。','E020':'条件相关关系。',
           'E010':'估计值为0.03。','E012':'95%置信区间为[0.02,0.04]。',
           'E015':'对应3个百分点。','R001':'来源记录490014条。',
           'R002':'删失1536条。','R003':'异常6条。','E014':'估计488472条。',
           'E016':'聚类256490名用户。','R020':'全量有效事件。',
           'R004':'原始7天标签的零值254297条。','R005':'原始30天标签的零值248498条。',
           'R021':'入组要求完整潜在随访。','R022':'观察结束点来自末条删失记录。',
           'P001':'论文表3参考系数0.0392。','M001':'当前不是DID。','D003':'没有验证因果识别。'}
    return {'run_id':'r','claim_level':'associational','data_kind':'user_provided',
            'facts':[{'evidence_id':k,'text_zh':v} for k,v in texts.items()]}


def test_paper_question_cannot_pass_with_unrelated_causal_answer():
    s=real_snapshot()
    with pytest.raises(CitationValidationError,match='P001'):
        validate_answer_contract({'citation_ids':['E004','E020','E010'],
                                  'sections':[{'title':'直接回答','text':'只有相关性'}]},
                                 answer_contract('论文中的3.92个百分点为什么不能称为精确复现？',s))


def test_censoring_question_requires_both_horizons_and_cohort_rule():
    s=real_snapshot();c=answer_contract('原始7天、30天标签的空值有什么问题？',s)
    assert {'R004','R005','R021','R022'}<=set(c['required_evidence'])
    refs={f['evidence_id'] for f in select_question_evidence(s,'原始7天、30天标签的空值有什么问题？')}
    assert set(c['required_evidence'])<=refs
    assert 'P001' not in refs


def test_named_windows_and_table_are_allowed_but_invented_estimates_are_not():
    s=real_snapshot()
    raw={'run_id':'r','claim_level':'associational','sections':[
        {'title':'直接回答','template':'7天标签与30天标签须区分。{{R004}}{{R005}}表3是论文参考。{{P001}}'},
        {'title':'结论边界','template':'{{E004}}{{E020}}'}]}
    assert validate_and_render(raw,s,s['facts'])['citation_validation']=='passed'
    for invented in ['提升了7个百分点。','31天标签已经恢复。','提升百分之七。']:
        bad=deepcopy(raw);bad['sections'][0]['template']+=invented
        with pytest.raises(CitationValidationError):validate_and_render(bad,s,s['facts'])


def test_brief_report_length_and_titles_are_checked():
    s=real_snapshot();c=answer_contract('把本次结果整理成简短汇报。',s)
    answer={'citation_ids':c['required_evidence'],'sections':[
        {'title':t,'text':'简短内容'} for t in c['response_format']]}
    validate_answer_contract(answer,c)
    answer['sections'][0]['text']='冗余'*500
    with pytest.raises(CitationValidationError,match='过长'):validate_answer_contract(answer,c)
    answer['sections'][0]={'title':'直接回答','text':'简短内容'}
    with pytest.raises(CitationValidationError,match='四节'):validate_answer_contract(answer,c)


def test_sample_retrieval_does_not_mix_in_other_cohort_counts():
    refs={f['evidence_id'] for f in select_question_evidence(real_snapshot(),'原始数据与主分析样本为什么不同？')}
    assert {'R001','R002','R003','E014','E016'}<=refs
    assert not {'R004','R005','P001'} & refs


def test_paper_related_data_cannot_be_asserted_unrelated():
    s=real_snapshot()
    raw={'run_id':'r','claim_level':'associational','sections':[
        {'title':'直接回答','template':'本次并非对论文数据的重新估计。{{P001}}{{E010}}'},
        {'title':'结论边界','template':'{{E004}}{{E020}}'}]}
    with pytest.raises(CitationValidationError,match='论文数据'):validate_and_render(raw,s,s['facts'])


def test_repeated_reference_is_compact_without_changing_saved_fact():
    s=real_snapshot();raw={'run_id':'r','claim_level':'associational','sections':[
        {'title':'直接回答','template':'{{E010}}{{E010}}'},
        {'title':'结论边界','template':'{{E004}}{{E020}}'}]}
    a=validate_and_render(raw,s,s['facts'])
    assert a['sections'][0]['text'].count('估计值为')==1
    assert '同前〔E010〕' in a['sections'][0]['text']
