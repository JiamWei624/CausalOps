"""Provider-neutral structured JSON transport. No agent tools or implicit provider fallback."""
from __future__ import annotations
import json,re,time,hashlib,ipaddress
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

PRESETS={
 'deepseek':{'label':'DeepSeek 官方','base_url':'https://api.deepseek.com','api_mode':'responses','model':'deepseek-flash','json_mode':'json_object','docs':'https://api-docs.deepseek.com/zh-cn/'},
 'openai':{'label':'OpenAI 官方','base_url':'https://api.openai.com/v1','api_mode':'responses','model':'','json_mode':'json_object','docs':'https://developers.openai.com/api/docs/guides/structured-outputs'},
 'anthropic':{'label':'Anthropic 官方','base_url':'https://api.anthropic.com/v1','api_mode':'anthropic_messages','model':'','json_mode':'prompt_json','docs':'https://platform.claude.com/docs/en/api/messages/create'},
 'qwen':{'label':'阿里云百炼 / 千问','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','api_mode':'chat_completions','model':'','json_mode':'json_object','docs':'https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope'},
 'gemini':{'label':'Gemini 官方兼容接口','base_url':'https://generativelanguage.googleapis.com/v1beta/openai','api_mode':'chat_completions','model':'','json_mode':'json_object','docs':'https://ai.google.dev/gemini-api/docs/openai'},
 'custom':{'label':'自定义 HTTPS 兼容接口','base_url':'','api_mode':'chat_completions','model':'','json_mode':'json_object','docs':''}}

class ProviderError(RuntimeError):pass
class OutputContractError(ProviderError):
    """A completed textual response failed local JSON/schema validation; no HTTP retry."""
    pass
class ProviderConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    provider:Literal['deepseek','openai','anthropic','qwen','gemini','custom']='deepseek'
    base_url:str='https://api.deepseek.com'
    model:str=Field(default='deepseek-flash',min_length=1,max_length=160)
    api_mode:Literal['responses','chat_completions','anthropic_messages']='responses'
    json_mode:Literal['json_object','json_schema','prompt_json']='json_object'
    max_output_tokens:int=Field(default=5000,ge=256,le=8192)
    timeout_seconds:float=Field(default=60,ge=5,le=180)
    max_retries:int=Field(default=0,ge=0,le=1)
    deepseek_reasoning:Literal['none','high']='none'
    anthropic_version:str=Field(default='2026-10-21',pattern=r'^\d{4}-\d{2}-\d{2}$')
    @model_validator(mode='after')
    def valid(self):
        u=urlsplit(self.base_url)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.port not in (None,443):raise ValueError('API地址须为不含账户、查询参数和片段的HTTPS Base URL，端口限443。')
        if re.search(r'\s|\\|%|sk-',self.base_url) or re.search(r'\s|[<>\x00-\x1f]',self.model):raise ValueError('地址或模型标识含无效内容。')
        host=u.hostname.lower()
        try:
            if not ipaddress.ip_address(host).is_global:raise ValueError('不连接本机、内网或元数据IP；本版只接入外部HTTPS服务。')
        except ValueError as exc:
            if '不连接' in str(exc):raise
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')):raise ValueError('不连接本机或内网域名。')
        fixed={'deepseek':('api.deepseek.com',''),'openai':('api.openai.com','/v1'),'anthropic':('api.anthropic.com','/v1'),'gemini':('generativelanguage.googleapis.com','/v1beta/openai')}
        if self.provider in fixed and (host,u.path.rstrip('/'))!=fixed[self.provider]:raise ValueError('所选官方服务与API地址不匹配；第三方服务请明确选择自定义接口。')
        if self.provider=='qwen':
            hosts={'dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com'}
            tenant=bool(re.fullmatch(r'[a-z0-9-]+\.(cn-beijing|us-east-1|ap-southeast-1|ap-northeast-1)\.maas\.aliyuncs\.com',host))
            if not (host in hosts or tenant) or u.path.rstrip('/')!='/compatible-mode/v1':raise ValueError('百炼地址须为官方地域/业务空间的compatible-mode/v1地址。')
        if self.base_url.rstrip('/').endswith(('/chat/completions','/responses','/messages')):raise ValueError('请填写Base URL，不要填写具体接口路径。')
        if self.provider=='anthropic' and (self.api_mode!='anthropic_messages' or self.json_mode!='prompt_json'):raise ValueError('Anthropic使用原生Messages协议和本地JSON模式校验。')
        if self.api_mode=='anthropic_messages' and self.provider!='anthropic':raise ValueError('原生Messages目前仅接入Anthropic官方地址。')
        return self
    def binding(self):
        return {'provider':self.provider,'base_url':self.base_url.rstrip('/'),'model':self.model,'api_mode':self.api_mode,'json_mode':self.json_mode,'anthropic_version':self.anthropic_version if self.api_mode=='anthropic_messages' else None}
    @property
    def fingerprint(self):return hashlib.sha256(json.dumps(self.binding(),sort_keys=True).encode()).hexdigest()

DEFAULT_BINDING=ProviderConfig().binding()
def model_binding(model):
    cfg=getattr(model,'provider_config',None)
    if cfg is not None:return cfg.binding()
    # Compatibility for legacy official DeepSeek adapters and deterministic test doubles only.
    return ProviderConfig(provider='deepseek',base_url=getattr(model,'base_url',''),model=getattr(model,'model','deepseek-flash'),api_mode=getattr(model,'api_mode','responses')).binding()
def model_label(model):return PRESETS[model_binding(model)['provider']]['label'].replace(' ','')

def strict_object(text):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('JSON包含重复字段。')
            d[k]=v
        return d
    def bad_constant(value):raise ValueError('JSON不能含非有限数值。')
    text=text.strip();m=re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```',text,re.S|re.I)
    if m:text=m.group(1)
    result=json.loads(text,object_pairs_hook=pairs,parse_constant=bad_constant)
    if not isinstance(result,dict):raise ValueError('输出须为单一JSON对象。')
    return result

class StructuredModelClient:
    def __init__(self,config:ProviderConfig,api_key:str,*,client=None,sleep=time.sleep):
        import httpx
        if not isinstance(api_key,str) or not api_key or api_key!=api_key.strip() or any(c.isspace() or ord(c)<33 for c in api_key):raise ValueError('API密钥为空或含空格/控制字符；只输入密钥本身。')
        if api_key in config.model or api_key in config.base_url:raise ValueError('认证信息不能填入模型名或API地址。')
        self.provider_config=config;self.base_url=config.base_url.rstrip('/');self.model=config.model;self.api_mode=config.api_mode
        self._api_key=api_key;self._sleep=sleep;self.last_telemetry={};self._owns_client=client is None
        self._client=client or httpx.Client(timeout=config.timeout_seconds,follow_redirects=False)
    def close(self):
        if self._owns_client:self._client.close()
    def _request(self,system,payload,schema):
        cfg=self.provider_config
        instruction=system+'\nReturn exactly one JSON object matching this schema. Do not call tools or execute anything. Local validation is authoritative:\n'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
        headers={'Authorization':'Bearer '+self._api_key,'Content-Type':'application/json'}
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
        body={'model':cfg.model,'stream':False}
        if cfg.api_mode=='responses':
            body.update(instructions=instruction,input=encoded,max_output_tokens=cfg.max_output_tokens)
            if cfg.provider=='deepseek':body['reasoning']={'effort':cfg.deepseek_reasoning}
            if cfg.json_mode!='prompt_json':
                body['text']={'format':{'type':'json_object'} if cfg.json_mode=='json_object' else {'type':'json_schema','name':'causalops_output','schema':schema,'strict':False}}
            path='/responses'
        elif cfg.api_mode=='chat_completions':
            if cfg.provider=='deepseek':body['thinking']={'type':'disabled' if cfg.deepseek_reasoning=='none' else 'enabled'}
            body['messages']=[{'role':'system','content':instruction},{'role':'user','content':encoded}]
            body['max_completion_tokens' if cfg.provider=='openai' else 'max_tokens']=cfg.max_output_tokens
            if cfg.json_mode!='prompt_json':body['response_format']={'type':'json_object'} if cfg.json_mode=='json_object' else {'type':'json_schema','json_schema':{'name':'causalops_output','schema':schema,'strict':False}}
            path='/chat/completions'
        else:
            headers['anthropic-version']=cfg.anthropic_version;body.update(system=instruction,messages=[{'role':'user','content':encoded}],max_tokens=cfg.max_output_tokens);path='/messages'
        # No tools, file upload, automatic redirects or hidden alternate provider.
        return path,headers,body
    def _observe_attempt(self, event):
        """Optional metadata-only observer. Physical attempts are distinct from schema repairs."""

    def complete_json(self,*,system_instruction,user_payload,output_schema):
        import httpx
        from jsonschema.validators import validator_for
        started=time.monotonic()
        path,headers,body=self._request(system_instruction,user_payload,output_schema)
        base={'provider':self.provider_config.provider,'provider_host':urlsplit(self.base_url).hostname,
              'model':self.model,'api_mode':self.api_mode}
        self.last_telemetry={}
        for attempt in range(1,self.provider_config.max_retries+2):
            physical_started=time.monotonic()
            event={**base,'attempt':attempt}
            # Task scope reaches every physical HTTP attempt, including transport retries
            # and callers' separate JSON repair calls. No reservation is refunded.
            from causalops.application.automation_budget import active_budget
            budget_scope=active_budget()
            reservation=None
            if budget_scope:
                ledger,purpose,binding,enabled=budget_scope
                if not enabled:
                    from causalops.application.automation_budget import BudgetExceeded
                    raise BudgetExceeded("当前固定自动化计划未批准模型调用，已在HTTP发送前阻断。")
                if binding is not None and binding!=self.provider_config.binding():
                    raise ProviderError("预算任务绑定的模型服务不同，禁止静默切换。")
                config=self.provider_config.model_dump(mode='json')
                reservation=ledger.reserve_model(purpose,config,len(json.dumps(body,ensure_ascii=False).encode('utf8')))
            self._observe_attempt({**event,'event':'started'})
            retry=False
            try:
                with self._client.stream('POST',self.base_url+path,headers=headers,json=body,follow_redirects=False,timeout=self.provider_config.timeout_seconds) as response:
                    event['status_code']=response.status_code
                    rid=response.headers.get('x-request-id')
                    if rid and self._api_key not in rid:event['request_id']=rid[:180]
                    if response.status_code>=300:
                        event['status']='http_error'
                        retry=response.status_code in (429,500,502,503,504) and attempt<=self.provider_config.max_retries
                        if not retry:
                            labels={400:'请求参数或接口模式不兼容',401:'密钥未通过认证',403:'账户或模型权限不足',404:'API路径或模型不可用',429:'限流或额度限制'}
                            raise ProviderError('API返回HTTP '+str(response.status_code)+'：'+labels.get(response.status_code,'服务未完成请求')+'。未切换服务商；请核对当前配置。')
                    else:
                        chunks=[];size=0
                        for chunk in response.iter_bytes():
                            size+=len(chunk)
                            if size>2*1024*1024:raise ProviderError('响应超过本地大小限制，停止解析。')
                            chunks.append(chunk)
                        outer=strict_object(b''.join(chunks).decode('utf-8'))
                        rid=event.get('request_id') or outer.get('id')
                        if isinstance(rid,str) and self._api_key not in rid:event['request_id']=rid[:180]
                        event['status']='response_received'
                if not retry:
                    text,usage=self._content(outer)
                    if len(self._api_key)>=8 and self._api_key in text:raise ProviderError('模型输出包含认证信息，已阻止保存与展示。')
                    resolved=str(outer.get('model',self.model))
                    def tokens(*keys):
                        value=next((usage[k] for k in keys if k in usage),None)
                        return value if type(value) is int and value>=0 else None
                    event.update(model=resolved[:160] if self._api_key not in resolved else self.model,
                        requested_model=self.model,output_contract=self.provider_config.json_mode+'_with_local_schema_validation',
                        input_tokens=tokens('input_tokens','prompt_tokens'),output_tokens=tokens('output_tokens','completion_tokens'),
                        total_tokens=tokens('total_tokens'))
                    try:value=strict_object(text)
                    except ValueError:raise OutputContractError('返回文本不是有效的单一JSON对象；仅允许按原结构修复一次。') from None
                    validator=validator_for(output_schema);validator.check_schema(output_schema)
                    error=next(validator(output_schema).iter_errors(value),None)
                    if error is not None:raise OutputContractError('模型JSON未通过本地结构校验（规则：'+str(error.validator)+'）；请重新输出完整且字段类型正确的JSON。')
                    event['status']='completed'
                    return value
            except httpx.TransportError as exc:
                event.update(status='transport_error',error=type(exc).__name__)
                # Only transient I/O failures qualify. Protocol/configuration violations do not.
                retry=isinstance(exc,(httpx.TimeoutException,httpx.NetworkError,httpx.RemoteProtocolError)) and attempt<=self.provider_config.max_retries
                if not retry:raise ProviderError('模型网络请求未完成：'+type(exc).__name__+'；未切换服务商。') from None
            except OutputContractError:
                event['status']='output_contract_error'
                raise
            except ProviderError:
                if event.get('status')!='http_error':event['status']='response_rejected'
                raise
            except (ValueError,UnicodeError,KeyError,TypeError,AttributeError):
                event['status']='response_rejected'
                raise ProviderError('模型返回内容不完整或JSON格式无效，未采纳输出。') from None
            finally:
                self.last_telemetry={**event,'attempts':attempt,'latency_ms':round((time.monotonic()-started)*1000)}
                finished={**event,'event':'finished','will_retry':retry,'latency_ms':round((time.monotonic()-physical_started)*1000)}
                if reservation:ledger.receipt(reservation,finished)
                self._observe_attempt(finished)
            if retry:self._sleep(1)
        raise ProviderError('已达到请求尝试上限。')
    def _content(self,r):
        if self.api_mode=='responses':
            if r.get('status')!='completed':raise ProviderError('模型响应未完成；请检查输出上限或服务状态。')
            texts=[]
            for item in r.get('output',[]):
                if item.get('type') not in ('message','reasoning'):raise ProviderError('当前接口只接受结构化文本，不接受模型工具调用。')
                if item.get('type')=='message':
                    for c in item.get('content',[]):
                        if c.get('type')=='refusal':raise ProviderError('模型拒绝返回该内容。')
                        if c.get('type')=='output_text':texts.append(c.get('text',''))
            text=r.get('output_text') or ''.join(texts)
        elif self.api_mode=='chat_completions':
            choices=r.get('choices') or []
            if not choices or choices[0].get('finish_reason')!='stop':raise ProviderError('对话输出未正常结束，不使用截断或工具调用内容。')
            message=choices[0].get('message',{})
            if message.get('refusal') or message.get('tool_calls'):raise ProviderError('当前接口只接受结构化文本，不接受拒绝或工具调用。')
            text=message.get('content','')
        else:
            if r.get('stop_reason')!='end_turn' or (r.get('stop_details') or {}).get('type')=='refusal':raise ProviderError('Messages输出未正常结束或被拒绝。')
            if any(c.get('type')=='tool_use' for c in r.get('content',[])):raise ProviderError('不接受模型工具调用。')
            text=''.join(c.get('text','') for c in r.get('content',[]) if c.get('type')=='text')
        if not isinstance(text,str) or not text.strip():raise ProviderError('模型未返回可解析文本。')
        return text,r.get('usage') or {}
    def probe(self):
        schema={'type':'object','properties':{'ok':{'type':'boolean','const':True}},'required':['ok'],'additionalProperties':False}
        result=self.complete_json(system_instruction='Return JSON {"ok":true} only.',user_payload={'purpose':'fixed configuration test; no research data'},output_schema=schema)
        return {'ok':result=={'ok':True},'binding':self.provider_config.binding(),'telemetry':self.last_telemetry,'research_data_sent':False}
