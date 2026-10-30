import json

from causalops.real_data import real_external_model_authorized


def test_real_consent_requires_exact_source_official_provider_and_scope(tmp_path):
    assert not real_external_model_authorized(tmp_path, 'source-a')
    path=tmp_path/'artifacts/real-model-authorization.json'
    path.parent.mkdir()
    payload={'authorized_by':'user','provider_url':'https://api.deepseek.com',
             'scope':'questions_schema_and_aggregate_evidence_only','source_sha256':'source-a'}
    path.write_text(json.dumps(payload),encoding='utf-8')
    assert real_external_model_authorized(tmp_path,'source-a')
    assert not real_external_model_authorized(tmp_path,'source-b')
    for field,value in [('provider_url','https://unapproved.example'),
                        ('scope','raw_rows'),('authorized_by','model')]:
        path.write_text(json.dumps({**payload,field:value}),encoding='utf-8')
        assert not real_external_model_authorized(tmp_path,'source-a')
    for broken in ['{', '[]', 'null']:
        path.write_text(broken,encoding='utf-8')
        assert not real_external_model_authorized(tmp_path,'source-a')
