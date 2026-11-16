"""Persistent conversation references over existing research facts; no execution API."""
from __future__ import annotations
import json,re,uuid,sqlite3,os
from typing import Literal
from pydantic import BaseModel,ConfigDict
from causalops.assistant.service import digest,now,check_question
from causalops.general.service import DesignError

class ChatSession(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    id:str
    title:str
    active_binding_id:str|None=None
    created:str
    updated:str

class ChatBinding(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    id:str
    chat_id:str
    version:int
    domain:Literal['automation_v2','assistant']
    subject_id:str
    assistant_session_id:str
    metadata:dict
    sha:str
    created:str

class MessageReference(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    id:str
    chat_id:str
    ordinal:int
    request_key:str
    question:str
    binding_id:str|None
    status:Literal['running','completed','blocked','failed','interrupted']
    created:str
    finished:str|None=None

class ChatService:
    """Single-local-user chat. Bound replies are original assistant event references."""
    def __init__(self,service):
        self.s=service;self.a=service.a;self.ws=service.ws
        with self.ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS chat_sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,create_key TEXT UNIQUE NOT NULL,active_binding_id TEXT,created TEXT NOT NULL,updated TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS chat_bindings(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL,version INTEGER NOT NULL,domain TEXT NOT NULL,subject_id TEXT NOT NULL,assistant_session_id TEXT NOT NULL,metadata TEXT NOT NULL,sha TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(chat_id,version))')
            c.execute('CREATE TABLE IF NOT EXISTS chat_turns(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL,ordinal INTEGER NOT NULL,request_key TEXT NOT NULL,request_sha TEXT NOT NULL,question TEXT NOT NULL,binding_id TEXT,status TEXT NOT NULL,reply TEXT,reply_sha TEXT,created TEXT NOT NULL,finished TEXT,owner_pid INTEGER,owner_birth TEXT,UNIQUE(chat_id,request_key),UNIQUE(chat_id,ordinal))')
    @staticmethod
    def _id(value):
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise DesignError('会话或消息身份不合法，未使用其他研究替代。')
        return value
    @staticmethod
    def _key(value):
        if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,128}',value):raise DesignError('提交标识不合法。')
        return value
    def session(self,chat_id):
        self._id(chat_id)
        with self.ws.connection() as c:r=c.execute('SELECT id,title,active_binding_id,created,updated FROM chat_sessions WHERE id=?',(chat_id,)).fetchone()
        if not r:raise DesignError('此研究会话不存在，未自动打开其他研究。')
        return ChatSession(**dict(zip(ChatSession.model_fields,r)))
    def sessions(self):
        with self.ws.connection() as c:ids=[r[0] for r in c.execute('SELECT id FROM chat_sessions ORDER BY updated DESC,rowid DESC')]
        return [self.session(x) for x in ids]
    def label(self,chat_id):
        cs=self.session(chat_id)
        if cs.title!='新研究':return cs.title
        with self.ws.connection() as c:r=c.execute('SELECT question FROM chat_turns WHERE chat_id=? ORDER BY ordinal LIMIT 1',(chat_id,)).fetchone()
        return (r[0][:24] if r else cs.title)
    def rename(self,chat_id,title):
        self.session(chat_id)
        title=check_question(title).strip()
        if not title or len(title)>64:raise DesignError('会话名称需为1至64字。')
        with self.ws.connection() as c:c.execute('UPDATE chat_sessions SET title=?,updated=? WHERE id=?',(title,now(),chat_id))
        return self.session(chat_id)
    def create(self,title='新研究',*,request_key=None):
        key=self._key(request_key or uuid.uuid4().hex);title=check_question(title)[:64]
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT id,title FROM chat_sessions WHERE create_key=?',(key,)).fetchone()
            if old:
                if old[1]!=title:raise DesignError('同一新建请求的内容已变化。')
                identifier=old[0]
            else:
                identifier=uuid.uuid4().hex;stamp=now();c.execute('INSERT INTO chat_sessions VALUES(?,?,?,?,?,?)',(identifier,title,key,None,stamp,stamp))
        return self.session(identifier)
    def binding(self,chat_id,binding_id=None):
        cs=self.session(chat_id);identifier=binding_id or cs.active_binding_id
        if not identifier:return None
        self._id(identifier)
        with self.ws.connection() as c:r=c.execute('SELECT id,chat_id,version,domain,subject_id,assistant_session_id,metadata,sha,created FROM chat_bindings WHERE id=? AND chat_id=?',(identifier,chat_id)).fetchone()
        if not r:raise DesignError('研究绑定不属于当前会话。')
        d=dict(zip(ChatBinding.model_fields,r));d['metadata']=json.loads(d['metadata'])
        if digest(d['metadata'])!=d['sha']:raise DesignError('会话研究来源指纹不一致。')
        return ChatBinding(**d)
    @staticmethod
    def validate_identity(value):
        """Stable boundary validator for non-UI adapters; no authorization grant."""
        return ChatService._id(value)
    @staticmethod
    def validate_request_key(value):
        return ChatService._key(value)
    def resolve_research(self,domain,subject_id,run_ids=None):
        """Verified read projection, shared by public transport adapters."""
        return self._resolve(domain,subject_id,run_ids)
    def _resolve(self,domain,subject_id,run_ids=None):
        """Read integrity is separate from permission to execute under new source code."""
        from causalops.application.report_identity import identity_error
        if domain not in ('automation_v2','assistant'):raise DesignError('研究类型不受支持。')
        self._id(subject_id)
        view=None;report=None;scope={};plans=[];warning=None
        if domain=='automation_v2':
            from causalops.application.automation_results import snapshot
            co=self.s.automation_v2();view=snapshot(co,subject_id);t=view['task'];p=t['plan'];sid=t['session_id']
            if view['errors'] or identity_error(view):raise DesignError('研究报告来源冲突或证据缺失，未展示其他任务的结果。')
            if digest(p)!=t['plan_sha'] or digest(t['source'])!=p['source_sha']:raise DesignError('研究计划或数据来源指纹不一致。')
            if self.s.data_binding(sid)!=p['data'] or self.s.contracts.ref(sid)!=p['contract_ref']:raise DesignError('研究数据或合同版本已变化，请重新核对研究范围。')
            scope=p['scope'];report=view['report'];plans=[dict(id=p['plan_id'],version=p['version'],sha=t['plan_sha'])]
            ids=list(report['source_runs']) if report else [view['evidence']['S02']['body']['run_id']] if 'S02' in view['evidence'] else []
            if run_ids is not None and ids!=run_ids:raise DesignError('研究运行清单已变化，请明确重新关联当前版本。')
            title=p['objective'];warning=view['binding_error']
        else:
            sid=subject_id;session=self.a.session(sid);title=session['title'];known=self.a.completed_runs(sid)
            ids=run_ids if run_ids is not None else ([self.a.selected_run(sid)] if self.a.selected_run(sid) else [known[0]['run_id']] if known else [])
            by={r['run_id']:r for r in known}
            if set(ids)-set(by):raise DesignError('所引运行不属于当前研究。')
            for rid in ids:
                plan=self.a.get_plan(by[rid]['plan_id']);plans.append(dict(id=plan['id'],version=plan['version'],sha=plan['sha']))
            if ids:
                from causalops.application.task_conclusions import source_dictionary
                dictionary,_=source_dictionary(self.a,sid,ids[-1]);scope={k:dictionary.get(k) for k in ('outcome','metric_label','metric_unit','metric_window','analysis_unit')}
        data=self.s.data_binding(sid);contract=self.s.contracts.ref(sid)
        if domain=='automation_v2':
            from .automation_answer import facts as report_facts
            facts=report_facts(view);runs=[dict(run_id=x) for x in ids]
        else:facts,runs=self.a.facts(sid,run_ids=ids)
        primary=ids[-1:] # S04 for complete effect, S02 for descriptive partial; never implicit cross-run arithmetic.
        metadata=dict(schema='chat-binding-v1',domain=domain,subject_id=subject_id,assistant_session_id=sid,title=title,
                      data=data,contract_ref=contract,plan_refs=plans,scope=scope,run_ids=ids,answer_run_ids=primary,
                      fact_catalog_sha=digest(facts),report_sha=digest(report) if report else None)
        return dict(metadata=metadata,view=view,runs=runs,execution_warning=warning)
    def bind(self,chat_id,domain,subject_id,*,run_ids=None):
        self.session(chat_id);source=self._resolve(domain,subject_id,run_ids);body=source['metadata'];sha=digest(body)
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE');active=c.execute('SELECT active_binding_id FROM chat_sessions WHERE id=?',(chat_id,)).fetchone()[0]
            if active:
                row=c.execute('SELECT id FROM chat_bindings WHERE id=? AND chat_id=? AND sha=?',(active,chat_id,sha)).fetchone()
                if row:return self.binding(chat_id,row[0])
            version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM chat_bindings WHERE chat_id=?',(chat_id,)).fetchone()[0]
            identifier=uuid.uuid4().hex;c.execute('INSERT INTO chat_bindings VALUES(?,?,?,?,?,?,?,?,?)',(identifier,chat_id,version,domain,subject_id,body['assistant_session_id'],json.dumps(body,ensure_ascii=False),sha,now()))
            c.execute('UPDATE chat_sessions SET active_binding_id=?,updated=? WHERE id=?',(identifier,now(),chat_id))
        return self.binding(chat_id,identifier)
    def view(self,chat_id,*,binding_id=None):
        b=self.binding(chat_id,binding_id)
        if not b:return dict(metadata=None,view=None,runs=[],execution_warning=None)
        source=self._resolve(b.domain,b.subject_id,b.metadata['run_ids'])
        if digest(source['metadata'])!=b.sha:raise DesignError('研究数据、合同、计划或运行版本已变化；旧消息引用保留，请显式重新关联。')
        return source
    def _row(self,chat_id,turn_id):
        self.session(chat_id)
        with self.ws.connection() as c:
            c.row_factory=sqlite3.Row;r=c.execute('SELECT * FROM chat_turns WHERE id=? AND chat_id=?',(turn_id,chat_id)).fetchone()
        if not r:raise DesignError('消息不属于此会话。')
        return dict(r)
    @staticmethod
    def _turn(row):return MessageReference(**{k:row[k] for k in MessageReference.model_fields})
    def _reserve(self,chat_id,question,request_key,payload):
        from causalops.assistant.runtime import process_birth
        cs=self.session(chat_id);key=self._key(request_key);sha=digest(dict(question=question,binding_id=None if payload.get('operation') in ('import','workflow_handoff','workflow_link') else cs.active_binding_id,**payload))
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT id,request_sha FROM chat_turns WHERE chat_id=? AND request_key=?',(chat_id,key)).fetchone()
            if r:
                if r[1]!=sha:raise DesignError('同一提交标识已用于不同内容，未重复处理。')
                identifier=r[0];new=False
            else:
                identifier=uuid.uuid4().hex;ordinal=c.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM chat_turns WHERE chat_id=?',(chat_id,)).fetchone()[0]
                c.execute('INSERT INTO chat_turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,chat_id,ordinal,key,sha,question,cs.active_binding_id,'running',None,None,now(),None,os.getpid(),process_birth(os.getpid())))
                c.execute('UPDATE chat_sessions SET updated=? WHERE id=?',(now(),chat_id));new=True
        return self._row(chat_id,identifier),new
    def _finish(self,row,status,reply):
        with self.ws.connection() as c:c.execute("UPDATE chat_turns SET status=?,reply=?,reply_sha=?,finished=? WHERE id=? AND status='running'",(status,json.dumps(reply,ensure_ascii=False),digest(reply),now(),row['id']))
        return self._turn(self._row(row['chat_id'],row['id']))
    @staticmethod
    def _policy(code,text):return dict(kind='local_policy',code=code,source='本地工作台能力说明',text=text,run_ids=[])
    def submit(self,chat_id,question,*,request_key,mode='local',model=None):
        q=check_question(question)
        if mode not in ('local','model'):raise DesignError('请求模式不受支持。')
        row,new=self._reserve(chat_id,q,request_key,dict(operation='question',mode=mode))
        if not new:return self._turn(row)
        try:
            source=self.view(chat_id,binding_id=row['binding_id']) if row['binding_id'] else dict(metadata=None)
            meta=source['metadata']
            if re.search('批准|执行|跑一下|开始计算|同意|修改研究|换成|更换指标|重新分析',q):
                return self._finish(row,'completed',self._policy('formal_action','聊天不创建批准或执行统计。请进入正式研究工作流核对候选、研究条件与人工审核；旧运行与历史消息保持原有来源。'))
            if not meta:return self._finish(row,'completed',self._policy('unbound','当前尚未绑定研究。可以上传 CSV / Parquet 核对数据口径，或关联已有研究后解释其真实结果。受限自动化只支持单表双组二元研究；其他统计方法保留专业入口，不能在聊天中执行任意研究目标。'))
            if re.search(r'(查看|打开|了解|检查).{0,12}(诊断|证据质量)|研究决定|决策历史',q):
                return self._finish(row,'completed',self._policy('evidence_navigation','请通过本条回复下方的入口查看当前研究的诊断或研究决定。诊断需要显式检查；研究决定需要用户明确保存，不会因聊天而自动产生，也没有统计执行权限。'))
            if not meta['answer_run_ids']:return self._finish(row,'completed',self._policy('no_run','数据或研究已关联，但当前没有可解释的已保存统计 Run。请通过原研究入口确认 DataContract、形成方案并正式审核；仅导入文件或选择字段不等于已经执行。'))
            if mode=='model':
                if model is None:return self._finish(row,'failed',self._policy('model_unavailable','模型尚未配置或未获本任务摘要发送许可，未发送本轮研究数据。可以选择本地确定性路径继续；已有统计运行没有重算。'))
                from causalops.llm.providers import model_binding
                if not self.a.consent_enabled(meta['assistant_session_id'],model_binding(model)):raise DesignError('当前研究未授权此模型接收摘要。')
            sid=meta['assistant_session_id'];before={e['id'] for e in self.a.events(sid)}
            if meta['domain']=='automation_v2':
                if mode=='model':return self._finish(row,'failed',self._policy('model_scope','自动化报告当前只接入已核验的确定性事实解释；本轮未向外部模型发送摘要。单次研究的模型解释仍可从原入口使用。'))
                from .automation_answer import answer as report_answer
                answer=report_answer(self.a,sid,source['view'],q)
            else:answer=self.a.ask(sid,q,model if mode=='model' else None,run_id=meta['answer_run_ids'][0])
            after=self.view(chat_id,binding_id=row['binding_id'])
            if after['metadata']!=meta:raise DesignError('答复期间研究来源发生变化。')
            matches=[e for e in self.a.events(sid) if e['id'] not in before and e['kind']=='answer' and digest(e['body'])==digest(answer)]
            if len(matches)!=1:raise DesignError('无法唯一核验本轮答复来源，未展示混合回答。')
            ref=dict(kind='assistant_event',assistant_session_id=sid,event_id=matches[0]['id'],event_sha=digest(answer),run_ids=answer['run_ids'])
            return self._finish(row,'completed',ref)
        except Exception:
            return self._finish(row,'blocked' if mode=='local' else 'failed',self._policy('source_or_provider_error','研究来源或模型响应未通过核验，未展示未经核实的统计解释。请核对当前研究和版本，或改用本地路径；不会使用其他任务的旧成功回答。'))
    def import_data(self,chat_id,payload,*,name,request_key):
        if not isinstance(payload,bytes):raise DesignError('附件内容不合法。')
        import hashlib
        row,new=self._reserve(chat_id,'导入附件并核对研究口径',request_key,dict(operation='import',name=name,sha256=hashlib.sha256(payload).hexdigest()))
        if not new:return self._turn(row)
        try:
            sid=self.s.create_task(payload=payload,name=name,title=name)
            b=self.bind(chat_id,'assistant',sid)
            return self._finish(row,'completed',dict(**self._policy('imported','附件已通过既有读取器导入，并关联为独立数据任务。DataContract 仍需在原研究入口明确确认；未生成计划、批准或统计 Run。'),imported_binding_id=b.id))
        except (ValueError,RuntimeError,OSError):return self._finish(row,'blocked',self._policy('import_rejected','附件未通过既有文件校验，未将其登记为新的研究绑定。请核对类型、编码、分隔符和必要字段后替换文件；当前历史研究不变。'))
    def messages(self,chat_id):
        self.session(chat_id)
        with self.ws.connection() as c:ids=[r[0] for r in c.execute('SELECT id FROM chat_turns WHERE chat_id=? ORDER BY ordinal',(chat_id,))]
        out=[];sources={};events={};catalogs={}
        for identifier in ids:
            row=self._row(chat_id,identifier);answer=None;available=True;error=None;b=None
            try:
                ref=json.loads(row['reply']) if row['reply'] else None
                if ref and digest(ref)!=row['reply_sha']:raise DesignError('消息回复引用指纹不一致。')
                if ref and ref['kind']=='assistant_event':
                    # Batch verification lives only for this read; the next call
                    # reloads sources and event hashes, including corruption.
                    bid=row['binding_id']
                    if bid not in sources:
                        bound=self.binding(chat_id,bid)
                        sources[bid]=(bound,self.view(chat_id,binding_id=bid))
                    b,source=sources[bid]
                    if b.assistant_session_id not in events:
                        events[b.assistant_session_id]={e['id']:e for e in self.a.events(b.assistant_session_id) if e['kind']=='answer'}
                    event=events[b.assistant_session_id].get(ref['event_id'])
                    if not event or digest(event['body'])!=ref['event_sha'] or event['body'].get('run_ids')!=ref['run_ids'] or set(ref['run_ids'])-set(b.metadata['run_ids']):raise DesignError('原始回答或运行引用已变化。')
                    key=(bid,tuple(ref['run_ids']))
                    if key not in catalogs:
                        if b.domain=='automation_v2':
                            from .automation_answer import facts as report_facts
                            catalogs[key]=report_facts(source['view'])
                        else:catalogs[key]=self.a.facts(b.assistant_session_id,run_ids=ref['run_ids'])[0]
                    facts=catalogs[key]
                    for fact in event['body'].get('facts',[]):
                        if fact['id'] not in facts or digest(fact['value'])!=digest(facts[fact['id']]['value']):raise DesignError('消息中的数值引用不符合保存运行。')
                    answer=event['body']
                elif ref:answer={k:v for k,v in ref.items() if k not in ('kind','code','imported_binding_id')}
                if row['binding_id'] and b is None:b=self.binding(chat_id,row['binding_id'])
            except (ValueError,RuntimeError,OSError,KeyError):available=False;error='这条历史回复的原来源无法核验，正文暂不展示；原引用保留，未加载其他任务代替。'
            out.append(dict(reference=self._turn(row),binding=b,answer=answer,available=available,error=error))
        return out
    def reconcile(self,chat_id):
        from causalops.assistant.runtime import alive
        self.session(chat_id)
        with self.ws.connection() as c:
            for identifier,pid,birth in c.execute("SELECT id,owner_pid,owner_birth FROM chat_turns WHERE chat_id=? AND status='running'",(chat_id,)).fetchall():
                if not alive(pid,birth):c.execute("UPDATE chat_turns SET status='interrupted',finished=? WHERE id=? AND status='running'",(now(),identifier))
        # No blind replay. Users may inspect and explicitly submit a separate read-only question.
