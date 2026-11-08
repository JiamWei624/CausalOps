"""Bounded compiler for one-table, two-arm, binary research. No model or new estimator."""
from __future__ import annotations
import hashlib
import re
import uuid
from urllib.parse import urlsplit
from typing import Literal
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from causalops.application.automation_contracts import PlanV2, fixed_steps, StepSpec
from causalops.application.data_contracts import DataContract
from causalops.general.exploration import ExplorationDesign
from causalops.general.service import GeneralDesign, DesignError
from causalops.results.interpretation import MetricDefinition
from causalops.assistant.service import digest, now
from causalops.assistant.runtime import execution_source_sha
from causalops.application.locking import flow_lock

SCHEMA="configurable-research-stage1"
ROW_KEY="__causalops_record_id"

class BinaryResearchConfig(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True,strict=True)
    objective:str=Field(min_length=8,max_length=600)
    analysis_unit:str=Field(min_length=1,max_length=80)
    entity:str|None=None
    record_grain:str=Field(min_length=4,max_length=300)
    independent_records_confirmed:bool=False
    treatment:str=Field(min_length=1,max_length=200)
    control_value:str=Field(min_length=1,max_length=100)
    treated_value:str=Field(min_length=1,max_length=100)
    control_label:str=Field(min_length=1,max_length=100)
    treated_label:str=Field(min_length=1,max_length=100)
    outcome:str=Field(min_length=1,max_length=200)
    negative_value:str=Field(min_length=1,max_length=100)
    positive_value:str=Field(min_length=1,max_length=100)
    metric:str=Field(min_length=1,max_length=120)
    unit:Literal["概率","比例","百分比"]="概率"
    window:str=Field(min_length=2,max_length=220)
    assignment:Literal["unknown","randomized"]="unknown"
    source_url:str=Field(default="",max_length=600)
    design_evidence:str=Field(default="",max_length=800)
    source_confirmed:bool=False

    @model_validator(mode="after")
    def coherent(self):
        if not self.independent_records_confirmed:raise ValueError("请明确确认记录粒度及独立观察单位；不能把重复记录视为独立样本。")
        if len({self.treatment,self.outcome,self.entity or ROW_KEY})!=3:raise ValueError("标识、分组和结果字段必须各自独立。")
        if self.control_value==self.treated_value or self.control_label==self.treated_label:raise ValueError("两个比较组及其含义必须明确区分。")
        if self.negative_value==self.positive_value:raise ValueError("二元结果的否定与肯定编码不能相同。")
        if self.source_url:
            u=urlsplit(self.source_url)
            if u.scheme not in ("https","http") or not u.netloc or u.username or u.password:raise ValueError("来源须是无凭据的公开网页地址；私人目录不能作为公开设计来源。")
        if self.assignment=="randomized" and (not self.source_confirmed or not self.source_url or len(self.design_evidence.strip())<12):
            raise ValueError("随机分配必须有具体设计来源、依据说明及使用者显式核对；两组标签不是随机化证据。")
        return self

    def scope(self):
        return dict(analysis_unit=self.analysis_unit,entity=self.entity or ROW_KEY,outcome=self.outcome,
                    metric=self.metric,unit="概率",window=self.window,treatment=self.treatment,
                    groups={self.control_value:self.control_label,self.treated_value:self.treated_label},
                    control_value=self.control_value,treated_value=self.treated_value,
                    inclusion="全部已上传记录；不自动筛选、删样本或填补",missing_policy="stop",
                    assignment_source=self.source_url,assignment=self.assignment,record_grain=self.record_grain,
                    coding={self.negative_value:0,self.positive_value:1},display_unit=self.unit)

    def contract(self):
        return DataContract(analysis_unit=self.analysis_unit,structure="cross_section",purpose="causal",
            entity=self.entity or ROW_KEY,treatment=self.treatment,outcome=self.outcome,
            control_value=self.control_value,treated_value=self.treated_value,control_label=self.control_label,treated_label=self.treated_label,
            metric_label=self.metric,metric_unit="概率",metric_kind="binary",metric_window=self.window,
            research=dict(population=self.record_grain,inclusion="全部记录；严格缺失策略，不删除或填补",comparison=self.treated_label+" 对比 "+self.control_label,
                          estimand="已确认分配范围内的二元概率差" if self.assignment=="randomized" else "描述性比例差，不解释为因果效应",
                          observation_period=self.window,provenance=self.source_url+" "+self.design_evidence,
                          limitations="独立记录由使用者确认；程序不证明所有识别假设。"),
            method_facts={"ab_test":{"assignment":self.assignment}},
            notes="原始结果编码映射："+str({self.negative_value:0,self.positive_value:1})+"；"+self.record_grain+
                  ("；技术记录键由用户确认的记录粒度生成，不证明人员身份唯一。" if not self.entity else "；使用已选择的唯一标识。")
        ).model_dump(mode="json")


def prepared(frame,c):
    required=[c.treatment,c.outcome]+([c.entity] if c.entity else [])
    if set(required)-set(frame):raise DesignError("缺少配置引用的必要字段。")
    if not frame.columns.is_unique or ROW_KEY in frame:raise DesignError("字段重复或与系统记录键冲突。")
    if frame[required].isna().any().any():raise DesignError("必要字段存在缺失；不自动删样本或填补。")
    if frame[c.treatment].astype(str).map(len).max()>100:raise DesignError("组别编码过长。")
    if set(frame[c.treatment].astype(str))!={c.control_value,c.treated_value}:raise DesignError("必须恰有两个已确认组别，不自动排除其他组。")
    if not set(frame[c.outcome].astype(str)) <= {c.negative_value,c.positive_value}:raise DesignError("结果包含未登记的编码，必须是已确认的二元指标。")
    if c.entity and frame[c.entity].duplicated().any():raise DesignError("唯一标识重复；本流程不支持重复测量或纵向面板。")
    if len(frame)<10 or frame.groupby(c.treatment).size().min()<2:raise DesignError("样本至少10条，每组至少2条；这是现有工具最低条件，不代表推断充分。")
    f=frame.copy();f[c.treatment]=f[c.treatment].astype(str)
    f[c.outcome]=f[c.outcome].astype(str).map({c.negative_value:0,c.positive_value:1}).astype("int64")
    if not c.entity:f[ROW_KEY]=range(len(f))
    return f


def configured_steps(c):
    rows=[x.model_dump(mode="json") for x in fixed_steps()]
    rows[1]["config"]=ExplorationDesign(question=c.objective,method="descriptive",numeric=[c.outcome],categorical=[c.treatment],group=c.treatment).model_dump(mode="json")
    effect=GeneralDesign(question=c.objective,analysis_unit=c.analysis_unit,method="ab_test",treatment=c.treatment,control_value=c.control_value,treated_value=c.treated_value,
                         outcome=c.outcome,entity=c.entity or ROW_KEY,metric=MetricDefinition(label=c.metric,unit="概率",kind="binary",direction="higher_is_better",ratio_scale=True,
                         window=c.window,source=c.source_url or "使用者登记的数据；分配机制未知")).model_dump(mode="json")
    effect.pop("assignment");rows[3]["config"]=effect
    return tuple(StepSpec.model_validate(x) for x in rows)

class ConfigurablePlan(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True)
    schema_version:Literal[SCHEMA]=SCHEMA
    plan_id:str=Field(pattern=r"^[a-f0-9]{32}$")
    version:int=Field(ge=1,le=100)
    objective:str
    data:dict
    contract_ref:dict
    scope:dict
    configuration:BinaryResearchConfig
    source_sha:str
    steps:tuple[StepSpec,...]
    model_requests:Literal[0]=0
    @model_validator(mode="after")
    def bounded(self):
        if self.objective!=self.configuration.objective or self.scope!=self.configuration.scope() or self.steps!=configured_steps(self.configuration):
            raise ValueError("计划必须由当前受限配置编译，不能改变步骤、工具、参数或依赖。")
        return self


STAGE2="configurable-research-stage2"

def plan_steps(c,path):
    if path=="randomized_two_arm_binary":return configured_steps(c)
    rows=[s for s in configured_steps(c) if s.step_id!="S04"]
    rows[2]=rows[2].model_copy(update={"config":{"rule":"descriptive_binary_cohort_v1"}})
    rows[-1]=rows[-1].model_copy(update={"depends_on":("S01","S02","S03"),"inputs":rows[-1].inputs[:3]})
    return tuple(rows)

class ConfigurablePlan2(ConfigurablePlan):
    schema_version:Literal[STAGE2]=STAGE2
    research_path:Literal["descriptive_binary","randomized_two_arm_binary"]
    candidate_ref:dict|None=None

    @model_validator(mode="after")
    def bounded(self):
        c=self.configuration
        if (self.objective!=c.objective or self.scope!=c.scope() or self.steps!=plan_steps(c,self.research_path)
            or self.research_path=="randomized_two_arm_binary" and c.assignment!="randomized"):
            raise ValueError("候选计划不属于合同允许的描述性或随机双组路径。")
        if self.candidate_ref is not None and set(self.candidate_ref)!={"id","task_id","sha"}:
            raise ValueError("候选来源引用不完整。")
        return self


def parse_plan(p):
    if p.get("schema_version")==STAGE2:return ConfigurablePlan2.model_validate(p)
    return ConfigurablePlan.model_validate(p) if p.get("schema_version")==SCHEMA else PlanV2.model_validate(p)


def approval_schema(t):return "configurable-research-approval-1" if is_configurable(t["plan"]) else "automation-v2-approval-1"
def authorized_facts(t):
    return {"S04":{"assignment":"randomized"}} if t["plan"]["scope"].get("assignment","randomized")=="randomized" and any(s["step_id"]=="S04" for s in t["plan"]["steps"]) else {}


def create(co,payload,*,name,configuration,request_id,human_confirmed=False,version=1,predecessor=None,import_event_id=None,stage2=False,research_path=None,candidate_ref=None):
    if human_confirmed is not True:raise DesignError("请先明确确认数据合同；合同确认不等于统计执行批准。")
    if not isinstance(request_id,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}",request_id):raise DesignError("需要稳定且非敏感的提交编号。")
    c=BinaryResearchConfig.model_validate(configuration)
    uid=co.ws.ingest(payload,name)
    if import_event_id is None:import_event_id=co.record_import(uid)
    raw=co.ws.load_upload(uid);f=prepared(raw,c)
    submission_body=dict(file_sha=hashlib.sha256(payload).hexdigest(),configuration=c.model_dump(mode="json"),predecessor=predecessor)
    path=research_path or ("randomized_two_arm_binary" if c.assignment=="randomized" else "descriptive_binary")
    if stage2:
        if path not in ("descriptive_binary","randomized_two_arm_binary"):raise DesignError("研究路径不受支持。")
        if path=="randomized_two_arm_binary" and c.assignment!="randomized":raise DesignError("未知随机化不能编译A/B执行步骤。")
        submission_body.update(stage2=True,research_path=path,candidate_ref=candidate_ref)
    elif research_path is not None or candidate_ref is not None:raise DesignError("旧版配置不能接受新规划参数。")
    submission=digest(submission_body)
    request_key=digest({"configurable_request_id":request_id})
    with flow_lock(co.ws.root,request_key):
        with co.ws.connection() as db:old=db.execute("SELECT id,source FROM automation_v2_tasks WHERE request_key=?",(request_key,)).fetchone()
        if old:
            import json
            if json.loads(old[1]).get("submission_sha")!=submission:raise DesignError("该提交编号已绑定其他数据或口径；请新建候选计划并重新审核。")
            return co.task(old[0])
        from io import BytesIO
        buf=BytesIO();f.to_parquet(buf,index=False)
        sid=co.s.create_task(payload=buf.getvalue(),name="configured_analysis.parquet",title=c.objective)
        co.s.contracts.save(sid,c.contract(),expected_sha=None,human_confirmed=True)
        binding=co.s.data_binding(sid)
        from causalops.execution import _data_fingerprint
        source=dict(adapter="configurable_binary_v1",adapter_source_sha=execution_source_sha(),derived_data=binding,scope=c.scope(),
                    raw_upload_id=uid,raw_frame_sha=_data_fingerprint(raw),raw_file_sha256=hashlib.sha256(payload).hexdigest(),submission_sha=submission,
                    source_url=c.source_url,human_source_confirmed=c.source_confirmed,predecessor_task=predecessor)
        if stage2:source["candidate_ref"]=candidate_ref
        fields=dict(plan_id=uuid.uuid4().hex,version=version,objective=c.objective,data=binding,contract_ref=co.s.contracts.ref(sid),scope=c.scope(),
                    configuration=c,source_sha=digest(source),steps=plan_steps(c,path) if stage2 else configured_steps(c))
        plan=(ConfigurablePlan2(**fields,research_path=path,candidate_ref=candidate_ref) if stage2 else ConfigurablePlan(**fields)).model_dump(mode="json")
        task=co._save_candidate(request_key,sid,source,plan)
        with co.ws.connection() as db:
            n=db.execute("UPDATE configurable_user_events SET task_id=? WHERE id=? AND upload_id=? AND task_id IS NULL",(task["id"],import_event_id,uid)).rowcount
            if n!=1:raise DesignError("导入事件与数据来源不一致。")
        for action in ("conditions_confirmed","plan_created"):co.user_event(task["id"],action)
        if stage2 and candidate_ref is None:
            from .constrained_planning import CandidatePlanning
            CandidatePlanning(co).template(task["id"])
        return task


def binding(co,t,p,*,contract_body=None):
    c=p.configuration;source=t["source"]
    if source.get("adapter")!="configurable_binary_v1" or source.get("scope")!=p.scope or source.get("derived_data")!=p.data:
        raise DesignError("原始数据、配置与计划来源不匹配。")
    from causalops.execution import _data_fingerprint
    raw=co.ws.load_upload(source["raw_upload_id"])
    if _data_fingerprint(raw)!=source["raw_frame_sha"] or _data_fingerprint(prepared(raw,c))!=p.data["frame_sha"]:
        raise DesignError("原始数据、编码映射或实际分析数据已变化，批准不能沿用。")
    row=co.s.contracts.latest(t["session_id"]) if contract_body is None else {"body":contract_body}
    if not row or row["body"]!=c.contract():raise DesignError("数据合同、指标、研究单位、设计依据或窗口已变化，须重新审核。")
    if isinstance(p,ConfigurablePlan2):
        if source.get("candidate_ref")!=p.candidate_ref:raise DesignError("候选来源与正式计划不一致。")
        if p.candidate_ref:
            from .constrained_planning import CandidatePlanning
            CandidatePlanning(co).verify_reference(t,p.candidate_ref)



def revise(co,tid,*,configuration,request_id,human_confirmed=False,payload=None,name=None,stage2=None,research_path=None,candidate_ref=None,require_unapproved=False):
    from io import BytesIO
    t=co.task(tid);p=parse_plan(t["plan"])
    if not isinstance(p,ConfigurablePlan):raise DesignError("固定公开案例不能原地改写为用户数据研究。")
    # Reserve a new candidate first, then revoke the obsolete authorization under
    # the same task lock used by execution. A running task is never silently edited.
    with flow_lock(co.ws.root,tid):
        if require_unapproved:
            current=co.task(tid)
            with co.ws.connection() as db:approved=db.execute("SELECT 1 FROM automation_v2_approvals WHERE task_id=?",(tid,)).fetchone()
            if current["status"] not in ("candidate","paused") or approved:raise DesignError("任务已进入审批流程，候选不得替换；原计划和批准保留。")
            co._binding(current)
        if co.task(tid)["status"] in ("running","pause_requested","cancel_requested"):raise DesignError("请先在安全边界停止执行，再修改研究范围。")
        new_config=BinaryResearchConfig.model_validate(configuration)
        old_raw=co.ws.load_upload(t["source"]["raw_upload_id"])
        if new_config.window!=p.configuration.window:
            if payload is None:raise DesignError("观察窗口变化必须上传实际覆盖新窗口的数据；不能只改窗口文字后沿用旧表。")
            new_uid=co.ws.ingest(payload,name)
            from causalops.execution import _data_fingerprint
            if _data_fingerprint(co.ws.load_upload(new_uid))==_data_fingerprint(old_raw):
                raise DesignError("新窗口仍对应相同原始记录，无法核验变化；请补充正确窗口的数据。")
        if payload is None:
            buf=BytesIO();co.ws.load_upload(t["source"]["raw_upload_id"]).to_parquet(buf,index=False);payload=buf.getvalue();name="original_input.parquet"
        newer=create(co,payload,name=name,configuration=configuration,request_id=request_id,human_confirmed=human_confirmed,version=p.version+1,predecessor=tid,stage2=isinstance(p,ConfigurablePlan2) if stage2 is None else stage2,research_path=research_path,candidate_ref=candidate_ref)
        with co.ws.connection() as db:
            db.execute("UPDATE automation_v2_approvals SET revoked=1 WHERE task_id=?",(tid,))
            if t["status"] not in ("completed","cancelled"):db.execute("UPDATE automation_v2_tasks SET status='cancelled',reason=? WHERE id=?",("研究范围已修订；旧批准失效，历史结果保留。",tid))
        co._event(tid,None,"superseded",{"successor_task_id":newer["id"]})
        return newer


def is_configurable(plan):
    return plan.get("schema_version") in (SCHEMA,"configurable-research-stage2")
