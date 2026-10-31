import json,copy
import httpx,pytest,numpy as np,pandas as pd
from causalops.llm.providers import ProviderConfig,StructuredModelClient,ProviderError,PRESETS,model_binding
from causalops.assistant.service import AssistantWorkspace,DesignError
from causalops.general.service import GeneralWorkspace
from causalops.protocols.evidence_review import validate_fact_citations,review_exported_evidence

TEST_KEY='unit-'+'credential'
SCHEMA={'type':'object','properties':{'ok':{'type':'boolean','const':True}},'required':['ok'],'additionalProperties':False}

def config(provider='custom',**values):
    p=PRESETS[provider]
    return ProviderConfig(provider=provider,base_url=p['base_url'] or 'https://model.example.com/v1',model=p['model'] or 'account-model-id',api_mode=p['api_mode'],json_mode=p['json_mode'],**values)

def response(mode,content='{"ok":true}',**override):
    if mode=='responses':r={'id':'test-response','status':'completed','model':'resolved-model','output':[{'type':'message','content':[{'type':'output_text','text':content}]}],'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}
    elif mode=='chat_completions':r={'id':'test-chat','choices':[{'finish_reason':'stop','message':{'content':content}}],'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13}}
    else:r={'id':'test-message','stop_reason':'end_turn','content':[{'type':'text','text':content}],'usage':{'input_tokens':10,'output_tokens':3}}
    r.update(override);return r

@pytest.mark.parametrize('provider',list(PRESETS))
def test_provider_request_and_real_parser_contract(provider):
    cfg=config(provider);requests=[]
    def handle(req):requests.append(req);return httpx.Response(200,json=response(cfg.api_mode))
    with httpx.Client(transport=httpx.MockTransport(handle)) as h:
        m=StructuredModelClient(cfg,TEST_KEY,client=h);assert m.complete_json(system_instruction='test',user_payload={'safe':'summary only'},output_schema=SCHEMA)=={'ok':True}
    req=requests[0];body=json.loads(req.content);assert req.headers['Authorization']=='Bearer '+TEST_KEY
    assert body['model']==cfg.model and 'tools' not in body
    assert m.last_telemetry['provider']==provider and m.last_telemetry['status']=='completed'
    if cfg.api_mode=='responses':
        assert req.url.path.endswith('/responses') and body['text']['format']['type']=='json_object'
        assert body.get('reasoning')==({'effort':'none'} if provider=='deepseek' else None)
    elif cfg.api_mode=='chat_completions':assert req.url.path.endswith('/chat/completions') and body['response_format']['type']=='json_object'
    else:assert req.url.path.endswith('/messages') and req.headers['anthropic-version']=='2026-10-21' and 'response_format' not in body

@pytest.mark.parametrize('mode',['responses','chat_completions'])
@pytest.mark.parametrize('fmt',['json_object','json_schema','prompt_json'])
def test_protocol_format_matrix(mode,fmt):
    cfg=config().model_copy(update={'api_mode':mode,'json_mode':fmt});seen=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req:(seen.append(json.loads(req.content)) or httpx.Response(200,json=response(mode))))) as h:
        StructuredModelClient(cfg,TEST_KEY,client=h).complete_json(system_instruction='test',user_payload={},output_schema=SCHEMA)
    body=seen[0]
    if fmt=='prompt_json':assert 'text' not in body and 'response_format' not in body
    else:
        form=body['text']['format'] if mode=='responses' else body['response_format'];assert form['type']==fmt
        if fmt=='json_schema':assert (form if mode=='responses' else form['json_schema'])['strict'] is False

@pytest.mark.parametrize('url',['http://model.example.com/v1','https://user:pass@model.example.com/v1','https://model.example.com/v1?token=x','https://model.example.com/v1#fragment','https://127.0.0.1/v1','https://169.254.169.254/v1','https://localhost/v1','https://host.local/v1','https://model.example.com:8443/v1','https://model.example.com/v1/chat/completions'])
def test_invalid_endpoint_rejected(url):
    with pytest.raises(ValueError):ProviderConfig(provider='custom',base_url=url)

def test_preset_does_not_mislabel_third_party():
    with pytest.raises(ValueError):ProviderConfig(provider='openai',base_url='https://thirdparty.example/v1')
    assert ProviderConfig(provider='custom',base_url='https://thirdparty.example/v1').provider=='custom'
    assert config('qwen').base_url.startswith('https://dashscope')
    assert ProviderConfig(provider='qwen',base_url='https://space123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',api_mode='chat_completions').provider=='qwen'

@pytest.mark.parametrize('status',[301,307,400,401,403,404,429,503])
def test_error_redaction_and_no_cross_provider_fallback(status):
    cfg=config();urls=[]
    def handle(req):urls.append(str(req.url));return httpx.Response(status,json={'error':{'message':TEST_KEY+' confidential failure'}},headers={'Location':'https://other.example.com/v1'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as h:
        with pytest.raises(ProviderError) as exc:StructuredModelClient(cfg,TEST_KEY,client=h).complete_json(system_instruction='test',user_payload={},output_schema=SCHEMA)
    assert len(urls)==1 and all(u.startswith(cfg.base_url) for u in urls)
    assert TEST_KEY not in str(exc.value) and 'confidential' not in str(exc.value)

def test_bounded_transient_retry_and_probe_has_no_research_data():
    cfg=config(max_retries=1);requests=[]
    def handle(req):
        requests.append(req);return httpx.Response(503,json={}) if len(requests)==1 else httpx.Response(200,json=response(cfg.api_mode))
    with httpx.Client(transport=httpx.MockTransport(handle)) as h:
        m=StructuredModelClient(cfg,TEST_KEY,client=h,sleep=lambda _:None);r=m.probe()
    assert r['ok'] and not r['research_data_sent'] and len(requests)==2
    assert 'user_id' not in requests[1].content.decode() and 'dataset' not in requests[1].content.decode()

@pytest.mark.parametrize('content',['{"ok":false}','{"ok":true,"extra":1}','{"ok":true,"ok":false}','[true]','{"ok":NaN}','before {"ok":true} after'])
def test_invalid_json_or_schema_not_adopted(content):
    cfg=config()
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response(cfg.api_mode,content)))) as h:
        with pytest.raises(ProviderError):StructuredModelClient(cfg,TEST_KEY,client=h).complete_json(system_instruction='test',user_payload={},output_schema=SCHEMA)

@pytest.mark.parametrize('mode,override',[('responses',{'status':'incomplete'}),('chat_completions',{'choices':[{'finish_reason':'length','message':{'content':'{"ok":true}'}}]}),('anthropic_messages',{'stop_reason':'tool_use'})])
def test_truncation_or_tool_use_rejected(mode,override):
    cfg=config('anthropic') if mode=='anthropic_messages' else config().model_copy(update={'api_mode':mode})
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response(mode,**override)))) as h:
        with pytest.raises(ProviderError):StructuredModelClient(cfg,TEST_KEY,client=h).complete_json(system_instruction='test',user_payload={},output_schema=SCHEMA)

@pytest.fixture
def workspace(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));uid=a.ws.ingest(pd.DataFrame({'x':np.arange(30)/7,'y':np.arange(30)/9}).to_csv(index=False).encode(),'synthetic.csv');return a,a.create(uid)

def test_provider_switch_requires_new_consent(workspace):
    a,sid=workspace;old=config('deepseek');new=config('openai');a.consent(sid,True,old)
    assert a.consent_enabled(sid,old) and not a.consent_enabled(sid,new)
    calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req:(calls.append(req) or httpx.Response(200,json=response(new.api_mode))))) as h:
        m=StructuredModelClient(new,TEST_KEY,client=h)
        with pytest.raises(DesignError):a._call(sid,m,'test',{},SCHEMA)
        assert calls==[];a.consent(sid,True,new);assert a._call(sid,m,'test',{},SCHEMA)=={'ok':True}
        assert not a.consent_enabled(sid,old)
    sid2=a.create(a.session(sid)['upload_id']);assert not a.consent_enabled(sid2,new)

def test_model_or_protocol_change_requires_consent(workspace):
    a,sid=workspace;c=config();a.consent(sid,True,c)
    assert not a.consent_enabled(sid,c.model_copy(update={'model':'another-account-model'}))
    assert not a.consent_enabled(sid,c.model_copy(update={'api_mode':'responses'}))
    assert a.consent_enabled(sid,c.model_copy(update={'max_output_tokens':2048})) # same recipient, not more data scope

def test_budget_wrapper_preserves_provider_binding(workspace):
    from causalops.assistant.observation import CallBudget
    import time
    cfg=config('openai')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response(cfg.api_mode)))) as h:
        m=StructuredModelClient(cfg,TEST_KEY,client=h);wrapper=CallBudget(m,3,time.monotonic()+10);assert model_binding(wrapper)==cfg.binding()

def test_readonly_evidence_review_is_not_causal_approval():
    rid='a'*32;f={'id':rid+':p','run_id':rid,'value':.02,'path':'p_value','claim':'associational'};export={'status':'found','run_id':rid,'facts':[f]}
    assert validate_fact_citations(export,[f['id']])['status']=='valid'
    assert validate_fact_citations(export,['b'*32+':p'])['status']=='invalid'
    r=review_exported_evidence(export);assert r['all_machine_checks_passed'] and not r['assumptions_verified'] and not r['execution_performed']
    bad=copy.deepcopy(export);bad['facts'][0]['value']=1.2;r=review_exported_evidence(bad);assert not r['all_machine_checks_passed']
    bad=copy.deepcopy(export);bad['facts'][0]['run_id']='b'*32;assert not review_exported_evidence(bad)['all_machine_checks_passed']


def test_credential_echo_is_not_adopted():
    cfg=config();schema={'type':'object','properties':{'note':{'type':'string'}},'required':['note'],'additionalProperties':False}
    def handle(req):return httpx.Response(200,json=response(cfg.api_mode,json.dumps({'note':TEST_KEY})))
    with httpx.Client(transport=httpx.MockTransport(handle)) as h:
        with pytest.raises(ProviderError) as exc:StructuredModelClient(cfg,TEST_KEY,client=h).complete_json(system_instruction='test',user_payload={},output_schema=schema)
    assert TEST_KEY not in str(exc.value)

def test_empty_export_is_not_review_success():
    assert not review_exported_evidence({'status':'found','run_id':'a'*32,'facts':[]})['all_machine_checks_passed']


def test_reviewer_does_not_reuse_other_workspace(monkeypatch,tmp_path):
    from causalops.protocols import local_services as m
    monkeypatch.setattr(m,'card',lambda port:{'name':'CausalOps Method Reviewer','version':'0.7.0'})
    monkeypatch.setattr(m,'reviewer_identity',lambda port:{'workspace_fingerprint':m.workspace_identity(tmp_path/'other')})
    with pytest.raises(RuntimeError,match='工作区'):m.ensure_reviewer(tmp_path)
    monkeypatch.setattr(m,'reviewer_identity',lambda port:{'workspace_fingerprint':m.workspace_identity(tmp_path)})
    assert m.ensure_reviewer(tmp_path)['status']=='already_running'
