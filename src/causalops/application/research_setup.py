"""Human configuration -> deterministic proposal -> explicit adoption, never execution.

Uses existing contract repository, append-only assistant event journal, compiler
and adoption service. No statistical fact table, estimator or approval is added.
"""
from __future__ import annotations
import io,json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .chat_sessions import ChatService
from .configurable_research import BinaryResearchConfig,prepared
from .constrained_planning import CandidatePlanning
from .locking import flow_lock

class SetupError(DesignError):
    """Safe, actionable setup message; never contains the submitted raw object."""

class SetupRecord(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    schema_version:Literal['research-setup-v1']='research-setup-v1'
    kind:Literal['contract','candidate','adoption']
    chat_id:str
    session_id:str
    request_key:str
    request_sha:str
    values:dict
    checksum:str

class ResearchSetup:
    KINDS=('research_setup_contract','research_setup_candidate','research_setup_adoption')
    def __init__(self,chats:ChatService):
        self.c=chats;self.s=chats.s;self.a=chats.a;self.co=self.s.automation_v2();self.planning=CandidatePlanning(self.co)

    def _records(self,cid,kind=None):
        self.c.session(cid)
        with self.s.ws.connection() as db:
            rows=db.execute("SELECT id,session_id,kind,body,created FROM assistant_events WHERE kind IN (?,?,?) AND json_extract(body,'$.chat_id')=? ORDER BY rowid",(*self.KINDS,cid)).fetchall()
        out=[]
        for identifier,sid,event_kind,raw,created in rows:
            try:
                record=SetupRecord.model_validate_json(raw);body=record.model_dump(mode='json')
                if (record.session_id!=sid or record.chat_id!=cid or event_kind!='research_setup_'+record.kind
                    or digest({k:v for k,v in body.items() if k!='checksum'})!=record.checksum):raise ValueError()
            except (ValueError,TypeError):raise SetupError('配置回执来源或哈希不一致，未使用其他研究补齐。')
            if kind is None or record.kind==kind:out.append(dict(id=identifier,created=created,**record.values))
        return out

    def _get(self,cid,identifier,kind):
        self.c.validate_identity(identifier)
        found=next((x for x in self._records(cid,kind) if x['id']==identifier),None)
        if not found:raise SetupError('这份配置或候选不属于当前会话，未建立跨研究关联。')
        return found

    def _old(self,cid,kind,key,request):
        self.c.validate_request_key(key)
        with self.s.ws.connection() as db:
            rows=db.execute("SELECT body FROM assistant_events WHERE kind=? AND json_extract(body,'$.chat_id')=? AND json_extract(body,'$.request_key')=?",('research_setup_'+kind,cid,key)).fetchall()
        if len(rows)>1:raise SetupError('提交记录无法唯一核对，请保留现场并重新确认来源。')
        if not rows:return None
        try:r=SetupRecord.model_validate_json(rows[0][0])
        except ValueError:raise SetupError('配置提交回执损坏，未覆盖原记录或重新生成。')
        if r.request_sha!=digest(request):raise SetupError('相同提交标识已经用于其他内容；没有覆盖原配置。')
        # Reload through checksum and ownership validation.
        matches=[x for x in self._records(cid,kind) if x.get('request_key')==key]
        if len(matches)!=1:raise SetupError('配置提交回执无法唯一核验。')
        return matches[0]

    def _save(self,cid,sid,kind,key,request,values):
        body=dict(schema_version='research-setup-v1',kind=kind,chat_id=cid,session_id=sid,request_key=key,request_sha=digest(request),values=dict(values,request_key=key))
        record=SetupRecord(**body,checksum=digest(body))
        self.a.event(sid,'research_setup_'+kind,record.model_dump(mode='json'))
        return self._old(cid,kind,key,request)

    def _source(self,cid,bid=None,*,check_expected=False):
        current=self.c.session(cid)
        if check_expected and current.active_binding_id!=bid:raise SetupError('当前研究关联已经变化，请重新载入数据后确认。')
        source=self.c.view(cid);m=source['metadata']
        if not m:raise SetupError('请先明确提交CSV或Parquet附件，不能把未发送的文件当作已登记数据。')
        return source

    def _configuration_current(self,cid,r):
        if self.s.data_binding(r['session_id'])!=r['data'] or self.s.contracts.ref(r['session_id'])!=r['contract_ref']:
            raise SetupError('数据或合同版本已变化，旧候选不能继续采纳。请重新确认当前口径。')
        BinaryResearchConfig.model_validate(r['configuration'])

    def preview(self,cid):
        source=self._source(cid);m=source['metadata'];sid=m['assistant_session_id'];frame=self.c.ws.load_upload(m['data']['upload_id'])
        fields=[]
        for col in frame:
            values=frame[col].dropna().astype(str);counts=values.value_counts()
            fields.append(dict(name=col,dtype=str(frame[col].dtype),missing=int(frame[col].isna().sum()),distinct=int(values.nunique()),values=[dict(value=str(k),count=int(v)) for k,v in counts.iloc[:20].items()]))
        rows=json.loads(frame.head(8).to_json(orient='records',force_ascii=False,date_format='iso'))
        configs=self._records(cid,'contract');proposals=self._records(cid,'candidate');adoptions=self._records(cid,'adoption')
        editable=m['domain']=='assistant' and not m['run_ids']
        adoption=next((r for r in reversed(adoptions) if m['domain']=='automation_v2' and r['task_id']==m['subject_id']),None)
        config=next((r for r in reversed(configs) if r['session_id']==sid),None) if editable else (self._get(cid,adoption['configuration_ref'],'contract') if adoption else None)
        proposal=next((r for r in reversed(proposals) if config and r['configuration_ref']==config['id']),None)
        current_config=False
        if config:
            try:self._configuration_current(cid,config);current_config=True
            except (ValueError,RuntimeError,OSError):pass
        return dict(schema_version='research-setup-view-v1',chat_id=cid,binding_id=self.c.binding(cid).id,
            session_id=sid,data=m['data'],contract=self.s.contracts.latest(sid),editable=editable,
            phase='adopted' if adoption else 'candidate' if proposal and current_config else 'confirmed' if current_config else 'data_registered' if editable else 'existing_research',
            rows=len(frame),fields=fields,sample=rows,configuration=config if current_config else None,
            candidate=self.candidate(cid,proposal['id']) if proposal and current_config else None,adoption=adoption,
            scope_notice='这里是字段与编码预览，不是正式统计运行；不会自动删样本、填补或推断随机分配。')

    def confirm(self,cid,*,configuration,expected_binding_id,expected_data_sha,expected_contract_sha,human_confirmed,request_key):
        if human_confirmed is not True:raise SetupError('请显式核对并确认数据合同；确认不等于批准统计执行。')
        request=dict(configuration=configuration,expected_binding_id=expected_binding_id,expected_data_sha=expected_data_sha,expected_contract_sha=expected_contract_sha,human_confirmed=True)
        self.c.session(cid)
        with flow_lock(self.c.ws.root,'research-setup-'+cid):
            old=self._old(cid,'contract',request_key,request)
            if old:return old
            source=self._source(cid,expected_binding_id,check_expected=True);m=source['metadata']
            if m['domain']!='assistant' or m['run_ids']:raise SetupError('当前正式研究保留原合同和运行。修改口径请先登记新的数据任务，不原地改写已执行研究。')
            if m['data']['frame_sha']!=expected_data_sha:raise SetupError('数据指纹已变化，请重新预览。')
            c=BinaryResearchConfig.model_validate(configuration);frame=self.c.ws.load_upload(m['data']['upload_id']);prepared(frame,c)
            body=c.contract();body['entity']=c.entity
            # The original compiler adds its technical row key only in the
            # derived analysis table. Raw data is not silently rewritten here.
            row=self.s.contracts.save(m['assistant_session_id'],body,expected_sha=expected_contract_sha,human_confirmed=True)
            b=self.c.bind(cid,'assistant',m['subject_id'])
            return self._save(cid,m['assistant_session_id'],'contract',request_key,request,dict(session_id=m['assistant_session_id'],data=m['data'],contract_ref=self.s.contracts.ref(m['assistant_session_id']),configuration=c.model_dump(mode='json'),output_binding_id=b.id,human_confirmed=True))

    def compile(self,cid,configuration_ref,*,expected_binding_id,request_key):
        request=dict(configuration_ref=configuration_ref,expected_binding_id=expected_binding_id)
        self.c.session(cid)
        with flow_lock(self.c.ws.root,'research-setup-'+cid):
            old=self._old(cid,'candidate',request_key,request)
            if old:return self.candidate(cid,old['id'])
            source=self._source(cid,expected_binding_id,check_expected=True);r=self._get(cid,configuration_ref,'contract');self._configuration_current(cid,r)
            if source['metadata']['domain']!='assistant' or source['metadata']['subject_id']!=r['session_id']:raise SetupError('候选输入不是当前会话已确认的数据任务。')
            buf=io.BytesIO();self.c.ws.load_upload(r['data']['upload_id']).to_parquet(buf,index=False)
            previous=None
            for proposal in reversed(self._records(cid,'candidate')):
                prior=self._get(cid,proposal['configuration_ref'],'contract')
                if prior['session_id']==r['session_id'] and prior['id']!=r['id']:
                    previous=proposal;break
            request_id=digest(dict(chat=cid,key=request_key))
            if previous:
                # Preserve original revision/version, supersession and window
                # guards. Do not turn a changed scope into an unrelated seed.
                task=self.co.revise_configurable(previous['task_id'],configuration=r['configuration'],request_id=request_id,human_confirmed=True,stage2=True,require_unapproved=True)
            else:
                task=self.co.create_configurable(buf.getvalue(),name='confirmed_research.parquet',configuration=r['configuration'],request_id=request_id,human_confirmed=True,stage2=True)
            candidate=self.planning.template(task['id'])
            record=self._save(cid,r['session_id'],'candidate',request_key,request,dict(configuration_ref=r['id'],task_id=task['id'],plan_sha=task['plan_sha'],candidate_id=candidate['id'],execution_authorized=False))
            return self.candidate(cid,record['id'])

    def candidate(self,cid,identifier):
        r=self._get(cid,identifier,'candidate');cfg=self._get(cid,r['configuration_ref'],'contract');candidate=self.planning.get(r['task_id'],r['candidate_id']);task=self.co.task(r['task_id'])
        current=True;reason=None
        try:
            self._configuration_current(cid,cfg);payload=self.planning.payload(r['task_id'])
            if task['plan_sha']!=r['plan_sha'] or candidate['binding']!=payload['input_versions']:raise SetupError('候选计划或输入范围已经变化。')
        except (ValueError,RuntimeError,OSError):current=False;reason='候选来源、数据或合同版本已变化；保留历史但不能采纳。'
        return dict(**r,candidate=candidate,source_current=current,source_error=reason,contract_ref=cfg['contract_ref'],data=cfg['data'])

    def adopt(self,cid,candidate_ref,*,expected_binding_id,human_confirmed,request_key):
        if human_confirmed is not True:raise SetupError('请显式采纳候选；采纳后仍需要正式人工审批。')
        request=dict(candidate_ref=candidate_ref,expected_binding_id=expected_binding_id,human_confirmed=True)
        self.c.session(cid)
        with flow_lock(self.c.ws.root,'research-setup-'+cid):
            old=self._old(cid,'adoption',request_key,request)
            if old:return old
            r=self.candidate(cid,candidate_ref);cfg=self._get(cid,r['configuration_ref'],'contract')
            if not r['source_current']:raise SetupError(r['source_error'])
            current=self._source(cid);m=current['metadata']
            recovering=(m['domain']=='automation_v2' and (current['view']['task']['plan'].get('candidate_ref') or {}).get('id')==r['candidate_id'])
            if not recovering:
                self._source(cid,expected_binding_id,check_expected=True)
                if m['domain']!='assistant' or m['subject_id']!=cfg['session_id']:raise SetupError('候选不属于当前明确关联的数据任务。')
            task=self.planning.adopt(r['task_id'],r['candidate_id'],human_confirmed=True)
            if task['status']!='candidate' or task['plan']['configuration']!=cfg['configuration']:raise SetupError('采纳未产生匹配的待审方案；未授予执行权限。')
            b=self.c.bind(cid,'automation_v2',task['id'])
            return self._save(cid,cfg['session_id'],'adoption',request_key,request,dict(configuration_ref=cfg['id'],candidate_ref=r['id'],task_id=task['id'],plan_sha=task['plan_sha'],output_binding_id=b.id,status=task['status'],execution_authorized=False))
