"""Versioned, human-declared data meanings; never inferred scientific facts."""
from __future__ import annotations
import json,re,uuid
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from causalops.assistant.service import digest,now,PROTECTED
from causalops.assistant.contracts import REGISTRY
from causalops.general.service import DesignError

class ResearchScope(BaseModel):
    """Human-supplied scope; it never authorizes filtering, execution or causal claims."""
    model_config=ConfigDict(extra='forbid',strict=True)
    population:str=Field(default='',max_length=600)
    inclusion:str=Field(default='',max_length=600)
    comparison:str=Field(default='',max_length=600)
    estimand:str=Field(default='',max_length=400)
    observation_period:str=Field(default='',max_length=300)
    decision:str=Field(default='',max_length=600)
    provenance:str=Field(default='',max_length=800)
    limitations:str=Field(default='',max_length=800)

class FieldMeaning(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    field:str=Field(min_length=1,max_length=200)
    meaning:str=Field(default='',max_length=600)
    unit:str=Field(default='',max_length=80)
    role:Literal['unspecified','identifier','time','treatment','outcome','covariate','measure','category']='unspecified'
    source:str=Field(default='',max_length=400)
    derivation:str=Field(default='',max_length=600)
    timing:Literal['unknown','pre_treatment','post_treatment','future','time_invariant']='unknown'

class DataContract(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    analysis_unit:str=Field(default='',max_length=80)
    structure:Literal['unknown','cross_section','panel']='unknown'
    purpose:Literal['exploratory','predictive','causal']='exploratory'
    entity:str|None=None
    time:str|None=None
    treatment_time:str|None=None
    outcome:str|None=None
    treatment:str|None=None
    instruments:list[str]=Field(default_factory=list,max_length=8)
    running:str|None=None
    cohort:str|None=None
    cutoff:float|None=None
    predictors:list[str]=Field(default_factory=list,max_length=20)
    covariates:list[str]=Field(default_factory=list,max_length=20)
    control_value:str|None=None
    treated_value:str|None=None
    metric_label:str=Field(default='',max_length=120)
    metric_unit:str=Field(default='',max_length=80)
    metric_kind:Literal['unknown','continuous','binary','count']='unknown'
    metric_window:str=Field(default='',max_length=220)
    research:ResearchScope=Field(default_factory=ResearchScope)
    fields:list[FieldMeaning]=Field(default_factory=list,max_length=200)
    method_facts:dict[str,dict]=Field(default_factory=dict)
    notes:str=Field(default='',max_length=1200)

class ContractRepository:
    def __init__(self,assistant):
        self.a=assistant;self.ws=assistant.ws
        with self.ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS workflow_data_contracts(id TEXT PRIMARY KEY,session_id TEXT,version INTEGER,data_sha TEXT,body TEXT,sha TEXT,created TEXT,UNIQUE(session_id,version))')
    def versions(self,sid):
        self.a.session(sid)
        with self.ws.connection() as c:rows=c.execute('SELECT * FROM workflow_data_contracts WHERE session_id=? ORDER BY version DESC',(sid,)).fetchall()
        result=[]
        for row in rows:
            body=json.loads(row[4])
            if digest(body)!=row[5]:raise DesignError('数据字典指纹不一致。')
            result.append(dict(id=row[0],session_id=row[1],version=row[2],data_sha=row[3],body=body,sha=row[5],created=row[6],evidence_type='human_declared_not_empirically_verified'))
        return result
    def latest(self,sid):
        rows=self.versions(sid);return rows[0] if rows else None
    def ref(self,sid):
        v=self.latest(sid)
        return {k:v[k] for k in ('id','version','sha','data_sha')} if v else None
    def save(self,sid,value,*,expected_sha=None,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('数据字典只能由使用者明确确认。')
        d=DataContract.model_validate(value);s=self.a.session(sid);frame=self.ws.load_upload(s['upload_id']);columns=set(frame)
        selected=[x for x in (d.entity,d.time,d.treatment_time,d.outcome,d.treatment,d.running,d.cohort) if x]+d.predictors+d.covariates+d.instruments+[x.field for x in d.fields]
        if set(selected)-columns:raise DesignError('数据字典引用了当前表不存在的字段。')
        if len({x.field for x in d.fields})!=len(d.fields):raise DesignError('字段说明不能重复。')
        if d.treatment and d.outcome==d.treatment:raise DesignError('处理和结果不能是同一个字段。')
        if len(set(d.predictors))!=len(d.predictors) or len(set(d.covariates))!=len(d.covariates):raise DesignError('变量角色不能重复。')
        for method,facts in d.method_facts.items():
            if method not in REGISTRY or not isinstance(facts,dict):raise DesignError('字典确认项的方法不受支持。')
            allowed=PROTECTED & set(REGISTRY[method].design_type.model_fields)
            if set(facts)-allowed:raise DesignError('字典只能登记已注册的人工确认项。')
            for field,value in facts.items():
                if field=='assignment':
                    if value not in ('unknown','observational','randomized'):raise DesignError('分配机制声明不合法。')
                elif field=='design_evidence':
                    if not isinstance(value,str) or not 12<=len(value.strip())<=3000:raise DesignError('设计依据须为明确的人工文字说明。')
                elif type(value) is not bool:raise DesignError('确认项须为明确布尔值，不接受模型文字或隐式转换。')
        body=d.model_dump(mode='json');encoded=json.dumps(body,ensure_ascii=False,allow_nan=False)
        if re.search(r'sk-[A-Za-z0-9_-]{12,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',encoded):raise DesignError('不要在数据字典中保存密钥或邮箱。')
        with self.ws.connection() as c:
            data_sha=c.execute('SELECT frame_sha FROM general_uploads WHERE upload_id=?',(s['upload_id'],)).fetchone()[0]
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_jobs'").fetchone():
                if c.execute("SELECT 1 FROM workflow_jobs WHERE session_id=? AND status IN ('queued','running','cancel_requested')",(sid,)).fetchone():raise DesignError('该任务仍在后台处理，完成或停止后再修改字典。')
            prior=c.execute('SELECT version,sha FROM workflow_data_contracts WHERE session_id=? ORDER BY version DESC LIMIT 1',(sid,)).fetchone()
            if (prior[1] if prior else None)!=expected_sha:raise DesignError('数据字典已有更新，请先查看最新版本。')
            if prior and prior[1]==digest(body):return self.latest(sid)
            version=prior[0]+1 if prior else 1
            c.execute('INSERT INTO workflow_data_contracts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,sid,version,data_sha,encoded,digest(body),now()))
        self.a.event(sid,'data_contract_registered',{'version':version,'sha':digest(body),'evidence_type':'human_declared_not_empirically_verified'})
        return self.latest(sid)
    def bound(self,flow):
        # Pre-0.9 flows remain explicitly unbound; their prior behavior is retained.
        ref=flow['request'].get('contract_ref')
        if not ref:return None
        row=next((v for v in self.versions(flow['session_id']) if v['id']==ref['id']),None)
        if not row or any(row[k]!=ref[k] for k in ('id','version','sha','data_sha')):raise DesignError('流程引用的数据字典版本不存在或已损坏。')
        return row
    def verify_current(self,flow):
        if 'contract_ref' in flow['request'] and flow['request']['contract_ref']!=self.ref(flow['session_id']):raise DesignError('数据字典已更新，请基于新版本制定计划，旧批准不再适用。')
        return self.bound(flow)
    def review_facts(self,flow,plan):
        row=self.verify_current(flow)
        if not row:return {}
        definitions={x['field']:x for x in row['body']['fields']};facts={}
        for i,step in enumerate(plan['steps']):
            cfg=step['config'];method=cfg['method']
            fields=cfg.get('covariates',[])+ (cfg.get('predictors',[]) if row['body']['purpose']=='predictive' else [])
            if any(definitions.get(f,{}).get('timing') in ('post_treatment','future') for f in fields):raise DesignError('计划使用了字典标记的处理后/未来变量，请修订设定。')
            facts[str(i)]=dict(row['body']['method_facts'].get(method,{}))
        return facts
