"""User-owned data intake and versioned analysis, independent of example schemas."""
from __future__ import annotations
import csv,io,json,hashlib,sqlite3,uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from typing import Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel,Field,ConfigDict
from causalops.config import workspace_root
from causalops.schemas import CausalSpec,ResultBundle
from causalops.research import ResearchRepository,RevisionSource,DraftStatus
from causalops.execution import _data_fingerprint
from causalops.identification import route_identification
from causalops.results.interpretation import MetricDefinition
from causalops.ui.controller import run_versioned_workflow,run_versioned_association_workflow

METHODS={'ab_test':'A/B随机实验','cuped':'CUPED随机实验','regression_adjustment':'观察性关联回归','psm':'倾向得分匹配PSM','ipw':'逆概率加权IPW','double_ml':'双重机器学习DML','did':'日级面板DID','aipw':'交叉拟合AIPW（IRM-ATE）'}
class DesignError(ValueError):pass
class GeneralDesign(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=8,max_length=1000)
    analysis_unit:str=Field(min_length=1,max_length=60)
    method:Literal['ab_test','cuped','regression_adjustment','psm','ipw','double_ml','did','aipw']
    treatment:str
    control_value:str
    treated_value:str
    outcome:str
    entity:str
    covariates:list[str]=Field(default_factory=list)
    cluster:str|None=None
    assignment:Literal['unknown','randomized','observational']='unknown'
    time:str|None=None
    treatment_time:str|None=None
    pre_days:int=Field(default=7,ge=2,le=365)
    post_days:int=Field(default=7,ge=2,le=365)
    allow_complete_case:bool=False
    covariates_reviewed:bool=False
    overlap_declared:bool=False
    exchangeability_declared:bool=False
    parallel_declared:bool=False
    no_anticipation_declared:bool=False
    panel_confirmed:bool=False
    metric:MetricDefinition

def read_table(payload:bytes,name:str,encoding='utf-8-sig',separator=',',max_rows=100000)->pd.DataFrame:
    if len(payload)>50*1024*1024:raise DesignError('文件超过50MB。本版请在本地先准备分析表。')
    suffix=Path(name).suffix.lower()
    if suffix=='.csv':
        if encoding not in ('utf-8-sig','gb18030') or separator not in (',',';','\t'):raise DesignError('CSV编码或分隔符不受支持。')
        try:text=payload.decode(encoding)
        except UnicodeDecodeError:raise DesignError('CSV编码不匹配；请选择UTF-8或GB18030。') from None
        header=next(csv.reader(io.StringIO(text),delimiter=separator),[])
        if not header or any(not x.strip() for x in header) or len(set(header))!=len(header):raise DesignError('列名为空或重复，请先修正文件表头。')
        frame=pd.read_csv(io.StringIO(text),sep=separator,nrows=max_rows+1)
    elif suffix in ('.parquet','.pq'):
        import pyarrow.parquet as pq
        if pq.ParquetFile(io.BytesIO(payload)).metadata.num_rows>max_rows:raise DesignError('本版交互上传最多100,000行，请先准备分析队列。')
        frame=pd.read_parquet(io.BytesIO(payload))
    else:raise DesignError('仅支持CSV和Parquet；不执行脚本、Excel宏或Pickle。')
    if frame.empty or len(frame)>max_rows or len(frame.columns)>200:raise DesignError('数据为空或超过100,000行/200列的首版限制。')
    if not all(isinstance(x,str) and x.strip() for x in frame.columns) or len(set(frame.columns))!=len(frame.columns):raise DesignError('必须使用非空、不重复的字符串列名。')
    if frame.memory_usage(deep=True).sum()>256*1024*1024:raise DesignError('解码后的表超过256MB，请缩小分析队列。')
    for c in frame.select_dtypes(include=['object']).columns:
        if frame[c].dropna().map(lambda x:isinstance(x,(dict,list,tuple,set,np.ndarray))).any():raise DesignError('本版不支持嵌套对象列。')
    return frame.reset_index(drop=True)

def prepare(frame:pd.DataFrame,d:GeneralDesign):
    if d.control_value==d.treated_value:raise DesignError('处理组和对照组必须是不同取值。')
    if len(set(d.covariates))!=len(d.covariates):raise DesignError('协变量不能重复。')
    if d.entity in {d.treatment,d.outcome} or (d.cluster and d.cluster in {d.treatment,d.outcome}):raise DesignError('实体或聚类标识不能同时是处理或结果。')
    if d.entity in d.covariates or (d.cluster and d.cluster in d.covariates):raise DesignError('实体标识或聚类标识不能作为协变量。')
    if d.treatment in d.covariates or d.outcome in d.covariates or d.treatment==d.outcome:raise DesignError('处理、结果与协变量角色冲突。')
    required=list(dict.fromkeys([d.treatment,d.outcome,d.entity,*d.covariates,*([d.cluster] if d.cluster else [])]))
    if d.method=='did':
        if not d.time or not d.treatment_time or not d.panel_confirmed:raise DesignError('DID须确认日级面板，并明确日期和首次处理日期字段。')
        required+=list(dict.fromkeys([d.time,d.treatment_time]))
    if set(required)-set(frame):raise DesignError('所选字段不在当前数据中，请重新映射。')
    if d.covariates and not d.covariates_reviewed:raise DesignError('请先核对控制变量角色与测量时点；不要包含结果或未来信息。')
    if d.method in ('cuped','psm','ipw','double_ml','aipw','regression_adjustment') and not d.covariates:raise DesignError('所选方法需要明确协变量；不应凭空补充。')
    data=frame.copy();values=data[d.treatment].dropna().map(str);observed=set(values.unique())
    if observed!={d.control_value,d.treated_value}:raise DesignError('处理字段必须恰有两个已选择的非空组别；本版不会自动剔除其他实验组。')
    data[d.treatment]=data[d.treatment].map(lambda v:np.nan if pd.isna(v) else int(str(v)==d.treated_value))
    numeric=[d.outcome]+([c for c in d.covariates if pd.api.types.is_numeric_dtype(data[c])] if d.method=='regression_adjustment' else d.covariates)
    for c in numeric:
        try:data[c]=pd.to_numeric(data[c],errors='raise')
        except (ValueError,TypeError):raise DesignError('结果和所选方法使用的数值协变量必须可解析为数值。') from None
        if np.isinf(data[c].dropna().astype(float)).any():raise DesignError('分析字段含正负无穷，请先修正。')
    if d.method=='regression_adjustment':
        if any(data[c].nunique()>50 for c in d.covariates if not pd.api.types.is_numeric_dtype(data[c])):raise DesignError('分类协变量超过50类，请先合并或重新设计。')
    nullable={d.treatment_time} if d.method=='did' else set()
    needed=[c for c in required if c not in nullable];complete=data[needed].notna().all(axis=1);dropped=int((~complete).sum())
    if dropped and not d.allow_complete_case:raise DesignError(f'必要字段缺失会排除{dropped}行。请明确同意完整案例规则，或先处理缺失。')
    data=data.loc[complete].reset_index(drop=True)
    if len(data)<10:raise DesignError('完整案例少于10行，当前估计与推断不适用。')
    if d.metric.kind=='binary' and not data[d.outcome].isin([0,1]).all():raise DesignError('指标声明为二元结果，但结果字段不全为0/1。')
    if d.metric.kind=='count' and ((data[d.outcome]<0).any() or not np.allclose(data[d.outcome],np.floor(data[d.outcome]))):raise DesignError('计数指标须为非负整数。')
    if d.method in ('ab_test','cuped','psm','ipw','double_ml','aipw') and data[d.entity].duplicated().any():raise DesignError('本方法首版要求每个分析/随机化单位一行；重复单位需先聚合或使用合适的面板设计。')
    if d.method in ('ab_test','cuped'):
        if d.cluster and d.cluster!=d.entity:raise DesignError('本版A/B只支持独立单位推断，不支持另一个层级的聚类随机实验。')
        groups=data.groupby(d.treatment)[d.outcome]
        if len(groups)!=2 or (groups.count()<2).any() or not np.isfinite(groups.var().sum()) or groups.var().sum()<=0:raise DesignError('两组需要足够样本和可估计的组内变异。')
    if d.method=='did':
        for col in [d.time,d.treatment_time]:
            before=data[col].notna();parsed=pd.to_datetime(data[col],errors='coerce')
            if (before & parsed.isna()).any():raise DesignError('日期存在无法解析的非空值。')
            if not parsed.dropna().eq(parsed.dropna().dt.normalize()).all():raise DesignError('首版DID仅支持日级日期，请先明确聚合规则，不自动丢弃时分秒。')
            data[col]=parsed
        if data.duplicated([d.entity,d.time]).any():raise DesignError('DID每个实体每天必须只有一行。')
        if data.groupby(d.entity)[d.treatment_time].nunique(dropna=False).max()>1:raise DesignError('同一实体的首次处理日期不一致。')
        dates=data[d.treatment_time].dropna().unique()
        if len(dates)!=1:raise DesignError('首版仅开放共同处理时点DID；交错处理或没有处理时点不能套用此估计器。')
        if data.loc[data[d.treatment_time].isna(),d.entity].nunique()<2 or data.loc[data[d.treatment_time].notna(),d.entity].nunique()<2:raise DesignError('DID至少需要两个处理实体和两个从未处理实体。')
        expected=(data[d.treatment_time].notna() & (data[d.time]>=data[d.treatment_time])).astype(int)
        if not data[d.treatment].eq(expected).all():raise DesignError('DID处理字段必须表示“当日是否已经处理”，而不是固定的处理组标识。')
        event=next(iter(dates));expected_days=pd.date_range(pd.Timestamp(event)-pd.Timedelta(days=d.pre_days),periods=d.pre_days+d.post_days)
        if any(not set(expected_days).issubset(set(g[d.time])) for _,g in data.groupby(d.entity)):raise DesignError('当前前后窗口有实体缺日；请先确认缺失机制与聚合规则，本版不自动补零。')
    assumptions=[]
    if d.exchangeability_declared:assumptions.append('conditional exchangeability declared by reviewer; not empirically verified')
    if d.no_anticipation_declared:assumptions.append('no_anticipation declared by reviewer; not verified')
    spec=CausalSpec(question=d.question,domain='generic',analysis_unit=d.analysis_unit,treatment=d.treatment,outcome=d.outcome,
       entity_id_column=d.entity,cluster_column=(d.cluster or d.entity),covariates=d.covariates,candidate_methods=[d.method],
       assignment_mechanism=d.assignment,data_structure='panel' if d.method=='did' else 'cross_section',
       time_column=d.time if d.method=='did' else None,treatment_time_column=d.treatment_time if d.method=='did' else None,
       pre_period_days=d.pre_days if d.method=='did' else None,post_period_days=d.post_days if d.method=='did' else None,
       has_pre_treatment_outcome=d.method=='cuped' and d.covariates_reviewed,
       positivity_plausible=True if d.overlap_declared else None,parallel_trends_plausible=True if d.parallel_declared else None,
       identification_assumptions=assumptions)
    return data,spec,{'input_rows':len(frame),'analysis_rows':len(data),'explicit_complete_case_exclusions':dropped,
       'encoding':{'field':d.treatment,'zero':d.control_value,'one':d.treated_value},'metric_definition':d.metric.model_dump()}

class GeneralWorkspace:
    def __init__(self,root:Path|None=None):
        self.root=(root or workspace_root()).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.repo=ResearchRepository(self.root/'research.sqlite3')
        with self.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS general_uploads (upload_id TEXT PRIMARY KEY, name TEXT NOT NULL, relative_path TEXT NOT NULL, parquet_sha TEXT NOT NULL, frame_sha TEXT NOT NULL, reader_json TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS general_studies (session_id TEXT PRIMARY KEY, upload_id TEXT NOT NULL)')
    @contextmanager
    def connection(self):
        c=sqlite3.connect(self.root/'research.sqlite3')
        try:
            with c:yield c
        finally:c.close()
    def ingest(self,payload:bytes,name:str,**reader):
        frame=read_table(payload,name,**reader);uid=hashlib.sha256(payload+json.dumps(reader,sort_keys=True).encode()).hexdigest()
        with self.connection() as c:row=c.execute('SELECT upload_id FROM general_uploads WHERE upload_id=?',(uid,)).fetchone()
        if row:self.load_upload(uid);return uid
        path=self.root/'uploads'/f'{uid}.parquet';path.parent.mkdir(exist_ok=True);frame.to_parquet(path,index=False)
        with self.connection() as c:c.execute('INSERT INTO general_uploads VALUES (?,?,?,?,?,?)',(uid,Path(name).name,str(path.relative_to(self.root)),hashlib.sha256(path.read_bytes()).hexdigest(),_data_fingerprint(frame),json.dumps(reader)))
        return uid
    def uploads(self):
        with self.connection() as c:return [{'upload_id':r[0],'name':r[1]} for r in c.execute('SELECT upload_id,name FROM general_uploads ORDER BY rowid DESC')]
    def load_upload(self,uid):
        with self.connection() as c:r=c.execute('SELECT relative_path,parquet_sha,frame_sha FROM general_uploads WHERE upload_id=?',(uid,)).fetchone()
        if not r:raise DesignError('上传记录不存在。')
        p=(self.root/r[0]).resolve()
        if not p.is_relative_to(self.root/'uploads') or hashlib.sha256(p.read_bytes()).hexdigest()!=r[1]:raise DesignError('本地数据副本的路径或哈希不一致，停止分析。')
        f=pd.read_parquet(p)
        if _data_fingerprint(f)!=r[2]:raise DesignError('表内容指纹不一致。')
        return f
    def studies(self):
        with self.connection() as c:ids={r[0] for r in c.execute('SELECT session_id FROM general_studies')}
        return [s for s in self.repo.list_sessions() if s.session_id in ids]
    def upload_for(self,sid):
        with self.connection() as c:r=c.execute('SELECT upload_id FROM general_studies WHERE session_id=?',(sid,)).fetchone()
        if not r:raise DesignError('研究不属于此通用工作区。')
        return r[0]
    def save(self,uid,d:GeneralDesign,sid=None):
        frame,spec,quality=prepare(self.load_upload(uid),d);fingerprint=_data_fingerprint(frame)
        if sid:
            if self.upload_for(sid)!=uid:raise DesignError('研究与上传文件不匹配，请新建研究。')
            old=self.repo.get_session(sid)
            if old.current_draft_revision_id:
                rev=self.repo.get_revision(old.current_draft_revision_id)
                if rev.spec==spec and rev.research_notes.get('general_design')==d.model_dump(mode='json'):return sid,rev
            self.repo.register_dataset_version(sid,fingerprint=fingerprint,row_count=len(frame),column_schema={c:str(t) for c,t in frame.dtypes.items()})
        else:
            session=self.repo.create_session(title=d.question,dataset_fingerprint=fingerprint,row_count=len(frame),column_schema={c:str(t) for c,t in frame.dtypes.items()});sid=session.session_id
            with self.connection() as c:c.execute('INSERT INTO general_studies VALUES (?,?)',(sid,uid))
        rev=self.repo.create_revision(sid,spec,source=RevisionSource.USER_EDIT,change_reason='使用者保存字段映射、指标口径与研究设计；尚未批准',activate=True,status=DraftStatus.PENDING_REVIEW,
            research_notes={'general_design':d.model_dump(mode='json'),'input_quality':quality,'upload_id':uid,'external_model_authorized':False})
        return sid,rev
    def current(self,sid):
        s=self.repo.get_session(sid);return self.repo.get_revision(s.current_draft_revision_id)
    def execute(self,sid,revision_id,*,reviewed:bool,actor='user_explicit_review'):
        if not reviewed:raise DesignError('须明确确认当前保存的设计和执行边界。')
        rev=self.current(sid)
        if rev.revision_id!=revision_id:raise DesignError('草案已变化，请重新核对当前版本。')
        d=GeneralDesign.model_validate(rev.research_notes['general_design']);frame,spec,quality=prepare(self.load_upload(self.upload_for(sid)),d)
        ds=self.repo.get_dataset_version(rev.dataset_version_id)
        if spec!=rev.spec or _data_fingerprint(frame)!=ds.fingerprint_sha256:raise DesignError('重新准备的数据或设定与已保存版本不一致。')
        decision=route_identification(spec);association=d.method=='regression_adjustment'
        if decision.selected_method.value!=d.method or (decision.status.value!='pass' and not association):raise DesignError('识别条件尚未具备，请补充研究依据或改用明确的关联分析。')
        if d.method=='did' and not d.no_anticipation_declared:raise DesignError('尚未说明无预期效应；不能以默认勾选代替判断。')
        context={'metric_definition':d.metric.model_dump(),'input_quality':quality,'sample_note':d.metric.window,'source_note':'uploaded_local_table; no rows or schema sent to a model'}
        output=self.root/'runs'/sid
        if association:
            self.repo.authorize_association_analysis(revision_id,authorized_by=actor,authorization_note='明确授权仅条件关联分析，不确认无混杂或因果识别。')
            return run_versioned_association_workflow(frame,self.repo,session_id=sid,revision_id=revision_id,output_dir=output,source_description='user_uploaded_table_with_explicit_mapping',study_context=context)
        if rev.status!=DraftStatus.APPROVED:self.repo.approve_revision(revision_id,approved_by=actor,checklist={'mapping_and_unit':True,'design_and_assumptions':True,'execution_boundary':True})
        return run_versioned_workflow(frame,self.repo,session_id=sid,revision_id=revision_id,output_dir=output,source_description='user_uploaded_table_with_explicit_mapping',data_kind='user_provided',study_context=context)
    def runs(self,sid):
        self.upload_for(sid)
        with self.connection() as c:ids=[r[0] for r in c.execute("SELECT run_id FROM analysis_runs WHERE session_id=? AND status='completed' ORDER BY created_at DESC,run_id DESC",(sid,))]
        return [self.repo.get_analysis_run(x) for x in ids]
    def bundle(self,run_id):
        r=self.repo.get_analysis_run(run_id);self.upload_for(r.session_id);p=Path(r.result_bundle_path).resolve()
        if not p.is_relative_to(self.root/'runs'):raise DesignError('运行证据不属于当前工作区。')
        b=ResultBundle.model_validate_json(p.read_text(encoding='utf-8'));rev=self.repo.get_revision(r.revision_id);ds=self.repo.get_dataset_version(r.dataset_version_id)
        if b.run_id!=r.run_id or b.spec!=rev.spec or b.evidence['data']['fingerprint_sha256']!=ds.fingerprint_sha256:raise DesignError('运行、草案和数据证据不一致。')
        return b,r