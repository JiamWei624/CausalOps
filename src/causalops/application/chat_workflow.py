"""Reference-only bridge to existing formal workflows. No approval/execution interface."""
from __future__ import annotations
import io
import json
from causalops.assistant.service import digest
from causalops.general.service import DesignError


class ChatWorkflow:
    def __init__(self,chats):
        self.c=chats
        self.co=chats.s.automation_v2()

    def begin(self,chat_id,*,request_key,public=False):
        source=self.c.view(chat_id);meta=source['metadata']
        if meta and meta['domain']=='automation_v2':
            origin=dict(domain='automation_v2',subject_id=meta['subject_id'],data=meta['data'])
        elif meta:
            origin=dict(domain='assistant',subject_id=meta['subject_id'],data=meta['data'])
        elif public:
            origin=dict(domain='public',subject_id=None,data=None)
        else:raise DesignError('请先明确发送数据附件，或选择公开研究。')
        goal=next((m['reference'].question for m in self.c.messages(chat_id) if m['reference'].question!='导入附件并核对研究口径'),'核对研究条件并报告两组比例与证据限制')
        row,new=self.c._reserve(chat_id,'进入正式研究工作流',request_key,dict(operation='workflow_handoff',origin=origin,goal=goal))
        if not new:return self.c._turn(row)
        return self.c._finish(row,'completed',dict(kind='workflow_handoff',source='正式研究工作流',text='已打开正式研究工作区。合同确认、候选采纳和统计批准分别操作；完成后可返回本会话。',origin=origin,goal=goal))

    def get(self,chat_id,handoff):
        row=self.c._row(chat_id,handoff)
        ref=json.loads(row['reply'] or '{}')
        if row['status']!='completed' or ref.get('kind')!='workflow_handoff' or digest(ref)!=row['reply_sha']:
            raise DesignError('正式研究返回来源无效，未关联其他研究。')
        return ref

    def latest(self,chat_id,handoff):
        self.get(chat_id,handoff)
        with self.c.ws.connection() as db:
            rows=db.execute("SELECT reply,reply_sha FROM chat_turns WHERE chat_id=? AND status='completed' ORDER BY ordinal DESC",(chat_id,)).fetchall()
        for raw,sha in rows:
            ref=json.loads(raw or '{}')
            if ref.get('kind')=='workflow_link' and ref.get('handoff')==handoff:
                if digest(ref)!=sha:raise DesignError('正式研究关联指纹已变化。')
                return ref
        return None

    def active(self,chat_id):
        binding=self.c.binding(chat_id)
        if not binding:return None
        with self.c.ws.connection() as db:
            rows=db.execute("SELECT id,reply FROM chat_turns WHERE chat_id=? AND status='completed' ORDER BY ordinal DESC",(chat_id,)).fetchall()
        for identifier,raw in rows:
            ref=json.loads(raw or '{}')
            if ref.get('kind')!='workflow_handoff':continue
            root=self.get(chat_id,identifier);link=self.latest(chat_id,identifier)
            subject=link['task_id'] if link else root['origin']['subject_id']
            if subject==binding.subject_id:return identifier
        return None

    def input_file(self,chat_id,handoff):
        ref=self.get(chat_id,handoff);origin=ref['origin']
        if origin['domain']!='assistant':raise DesignError('此入口没有可配置的已登记数据。')
        if self.c.s.data_binding(origin['subject_id'])!=origin['data']:raise DesignError('已登记数据版本发生变化。')
        frame=self.c.ws.load_upload(origin['data']['upload_id']);buffer=io.BytesIO();frame.to_parquet(buffer,index=False)
        return buffer.getvalue(),'chat_registered_data.parquet'

    def publish(self,chat_id,handoff,task_id):
        root=self.get(chat_id,handoff);prior=self.latest(chat_id,handoff)
        source=self.c._resolve('automation_v2',task_id);t=source['view']['task'];origin=root['origin']
        if prior and prior['task_id']==task_id:
            if prior['plan_sha']!=t['plan_sha']:raise DesignError('已关联计划发生变化。')
            return prior
        expected=prior['task_id'] if prior else origin['subject_id'] if origin['domain']=='automation_v2' else None
        if expected:
            if t['source'].get('predecessor_task')!=expected:raise DesignError('新方案不属于本会话显式进入的研究修订链。')
        elif origin['domain']=='assistant':
            self.input_file(chat_id,handoff)
            if t['source'].get('raw_frame_sha')!=origin['data']['frame_sha']:raise DesignError('候选数据不属于本会话登记的分析表。')
        elif t['source'].get('adapter')!='hillstrom_public_v1':
            # Verify the public adapter explicitly rather than accepting any local task.
            from causalops.application.automation_contracts import scope
            if t['plan']['scope']!=scope():raise DesignError('不是本入口允许的公开营销研究。')
        payload=dict(kind='workflow_link',handoff=handoff,task_id=task_id,plan_sha=t['plan_sha'])
        row,new=self.c._reserve(chat_id,'正式研究已关联','link:'+handoff+':'+task_id,dict(operation='workflow_link',reference=payload))
        if new:self.c._finish(row,'completed',dict(**payload,source='正式研究工作流',text='正式候选已保存，可查看完整计划并审核。候选与聊天均不授予执行权限。'))
        self.c.bind(chat_id,'automation_v2',task_id)
        return self.latest(chat_id,handoff)

    def refresh(self,chat_id,handoff):
        root=self.get(chat_id,handoff);link=self.latest(chat_id,handoff)
        if not link:
            if root['origin']['domain']!='automation_v2':return self.c.view(chat_id)
            task=self.co.task(root['origin']['subject_id'])
            source=self.c._resolve('automation_v2',task['id'])
            self.c.bind(chat_id,'automation_v2',task['id'])
            return source
        task=self.co.task(link['task_id'])
        if task['plan_sha']!=link['plan_sha']:raise DesignError('计划身份变化，不能继承原会话关联。')
        # _resolve validates the actual current data/contract/report, not UI text.
        source=self.c._resolve('automation_v2',task['id'])
        active=self.c.binding(chat_id)
        if active and active.subject_id not in (root['origin']['subject_id'],task['id']):
            # A deliberate manual association supersedes this old workflow return.
            raise DesignError('当前会话已关联其他研究，请明确选择要恢复的研究。')
        self.c.bind(chat_id,'automation_v2',task['id'])
        return source

    def answer_goal(self,chat_id,handoff):
        try:source=self.refresh(chat_id,handoff)
        except (ValueError,RuntimeError,OSError):return None
        if not source['view'] or source['view']['task']['status']!='completed' or not source['view']['report']:return None
        root=self.get(chat_id,handoff);task=source['view']['task']
        # The original goal is shown with the plan. This automatic message is explicitly
        # read-only, so an action verb in that goal cannot be treated as a new command.
        return self.c.submit(chat_id,'本研究已保存的两组比例、样本量、差异、区间和研究限制是什么？',request_key='result:'+task['id'],mode='local')
