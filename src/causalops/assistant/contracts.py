"""Public analysis contracts. Adapters preserve each validated statistical engine."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from causalops.general.exploration import ExplorationDesign,LABELS as EX_LABELS
from causalops.general.service import GeneralDesign,METHODS,DesignError
from causalops.advanced.service import AdvancedDesign,LABELS as ADV_LABELS

@dataclass(frozen=True)
class MethodSpec:
    method:str
    label:str
    tool:str
    design_type:type
    review:str
    limits:str
    def json(self):
        return {'method':self.method,'label':self.label,'tool':self.tool,'review':self.review,'limits':self.limits}

REGISTRY={}
for m,label in EX_LABELS.items():
    REGISTRY[m]=MethodSpec(m,label,'exploration',ExplorationDesign,'分布/相关无需因果审批；回归须核对独立单位、缺失与暴露。','单表探索；相关/回归不解释为干预收益。')
for m,label in METHODS.items():
    REGISTRY[m]=MethodSpec(m,label,'research',GeneralDesign,'人工登记分配机制、协变量时序及方法识别依据。','按原引擎检查两组、分析单位、重叠和面板支持；不自动确认事实。')
for m,label in ADV_LABELS.items():
    REGISTRY[m]=MethodSpec(m,label,'advanced',AdvancedDesign,'人工提供具体设计依据及 IV/RD/交错 DID 所需声明。','保留已验证引擎的样本、聚类、窗口与推断边界。')

class ToolResult(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    contract_version:Literal['1']='1'
    run_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    upload_id:str
    method:str
    kind:Literal['exploration','research','advanced']
    data_fingerprint:str
    result_fingerprint:str
    claim:str
    plan_id:str|None=None
    plan_sha:str|None=None
    ordinal:int|None=None
    ref:dict

class AnalysisTools:
    def __init__(self,assistant):self.a=assistant
    def method(self,tool,method):
        spec=REGISTRY.get(method)
        if not spec or spec.tool!=tool:raise DesignError('方法与执行工具不匹配，未进入执行白名单。')
        return spec
    def catalog(self):return [s.json() for s in REGISTRY.values()]
    def schema(self,method,protected=()):
        s=REGISTRY[method].design_type.model_json_schema()
        s['properties']={k:v for k,v in s['properties'].items() if k not in protected}
        s['properties']['method']={'type':'string','enum':[method]}
        s['required']=[k for k in s.get('required',[]) if k not in protected]
        return s
    def schemas(self,protected=()):
        grouped={}
        for method,spec in REGISTRY.items():
            if spec.tool not in grouped:grouped[spec.tool]=self.schema(method,protected)
            grouped[spec.tool]['properties']['method']['enum']=[m for m,v in REGISTRY.items() if v.tool==spec.tool]
        return grouped
    def prepare(self,uid,step,facts,checkpoint=None):
        import uuid
        spec=self.method(step['tool'],step['config'].get('method'));cfg={**step['config'],**facts}
        design=spec.design_type.model_validate(cfg);checkpoint=dict(checkpoint or {})
        if spec.tool=='exploration':
            study,v=self.a.ex.save(uid,design,study_id=checkpoint.get('study_id'))
            checkpoint.update(kind=spec.tool,study_id=study,version=v,run_id=checkpoint.get('run_id') or uuid.uuid4().hex)
        elif spec.tool=='advanced':
            if not facts:raise DesignError('扩展方法须登记本步骤人工设计依据。')
            checkpoint.update(kind=spec.tool,run_id=checkpoint.get('run_id') or uuid.uuid4().hex)
        else:
            if not facts:raise DesignError('研究步骤须人工登记分配机制、指标与识别依据。')
            study,rev=self.a.ws.save(uid,design,sid=checkpoint.get('study_id'))
            checkpoint.update(kind=spec.tool,study_id=study,revision_id=rev.revision_id)
        return design,checkpoint
    def reconcile(self,uid,checkpoint):
        if not checkpoint:return None
        kind=checkpoint['kind']
        if kind=='exploration':
            with self.a.ws.connection() as c:exists=c.execute('SELECT 1 FROM exploration_runs WHERE run_id=?',(checkpoint['run_id'],)).fetchone()
            if exists:return self.envelope(uid,dict(checkpoint))
        elif kind=='advanced':
            with self.a.ws.connection() as c:exists=c.execute('SELECT 1 FROM advanced_runs WHERE run_id=?',(checkpoint['run_id'],)).fetchone()
            if exists:return self.envelope(uid,dict(checkpoint))
        else:
            runs=[r for r in self.a.ws.runs(checkpoint['study_id']) if r.revision_id==checkpoint['revision_id']]
            if len(runs)>1:raise DesignError('同一步骤存在多条可匹配运行，须核对后处理，不自动择优。')
            if runs:return self.envelope(uid,{**checkpoint,'run_id':runs[0].run_id})
        return None
    def execute(self,uid,design,checkpoint):
        kind=checkpoint['kind']
        if kind=='exploration':self.a.ex.run(checkpoint['study_id'],checkpoint['version'],run_id=checkpoint['run_id'])
        elif kind=='advanced':self.a.advanced.run(uid,design,reviewed=True,run_id=checkpoint['run_id'])
        else:
            b=self.a.ws.execute(checkpoint['study_id'],checkpoint['revision_id'],reviewed=True,actor='assistant_exact_plan_human_review')
            checkpoint={**checkpoint,'run_id':b.run_record.run_id}
        return self.envelope(uid,checkpoint)
    def envelope(self,uid,ref,**binding):
        from causalops.assistant.service import digest
        kind=ref['kind'];rid=ref['run_id']
        if kind=='exploration':
            b=self.a.ex.load(rid);actual=b['upload_id'];method=b['method'];fp=b['data_fingerprint'];claim=b['claim_level']
        elif kind=='advanced':
            b=self.a.advanced.load(rid);actual=b['upload_id'];method=b['method'];fp=b['data_fingerprint'];claim=b['claim']
        else:
            bundle,record=self.a.ws.bundle(rid);actual=self.a.ws.upload_for(record.session_id)
            b=bundle.model_dump(mode='json');method=bundle.spec.candidate_methods[0].value;fp=bundle.evidence['data']['fingerprint_sha256'];claim=bundle.claim_level.value
        if uid!=actual:raise DesignError('运行证据不属于当前数据集。')
        self.method(kind,method)
        return ToolResult(run_id=rid,upload_id=uid,kind=kind,method=method,data_fingerprint=fp,result_fingerprint=digest(b),claim=claim,ref=ref,**binding)
