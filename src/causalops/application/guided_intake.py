"""Progressive human input; metadata registration grants neither consent nor execution."""
from __future__ import annotations
import copy,json
from causalops.application.data_contracts import DataContract
from causalops.assistant.service import now,profile
from causalops.general.service import DesignError

INTENTS={'describe':'了解目标指标的分布','association':'分析指标之间的关系','effect':'了解措施或策略的效果','unsure':'尚未确定分析问题'}

class GuidedIntake:
    def __init__(self,service):
        self.s=service
        with service.ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS workflow_guided_intake(session_id TEXT PRIMARY KEY,data_sha TEXT NOT NULL,step INTEGER NOT NULL,intention TEXT NOT NULL,updated TEXT NOT NULL)')
    def state(self,sid):
        binding=self.s.data_binding(sid)
        with self.s.ws.connection() as c:row=c.execute('SELECT data_sha,step,intention FROM workflow_guided_intake WHERE session_id=?',(sid,)).fetchone()
        if row and row[0]!=binding['frame_sha']:raise DesignError('引导引用的数据已变化，请重新建立任务。')
        return {'step':row[1] if row else 1,'intention':row[2] if row else 'describe'}
    def _step(self,sid,step,intention='describe'):
        if intention not in INTENTS or step not in (1,2,3,4):raise DesignError('引导状态不受支持。')
        with self.s.ws.connection() as c:
            c.execute('INSERT OR REPLACE INTO workflow_guided_intake VALUES(?,?,?,?,?)',(sid,self.s.data_binding(sid)['frame_sha'],step,intention,now()))
    def reset(self,sid,*,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('调整引导须由使用者发起。')
        self._step(sid,1)
    def _body(self,sid,expected_sha):
        row=self.s.contracts.latest(sid)
        if (row['sha'] if row else None)!=expected_sha:raise DesignError('分析设置已有更新，请重新查看后确认。')
        return copy.deepcopy(row['body']) if row else DataContract().model_dump()
    def save_unit(self,sid,unit,*,expected_sha=None,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('分析单位须由使用者确认；不确定可留空。')
        body=self._body(sid,expected_sha)
        if body['analysis_unit']!=unit:body['method_facts']={}
        body['analysis_unit']=unit
        self.s.contracts.save(sid,body,expected_sha=expected_sha,human_confirmed=True)
        self._step(sid,2)
    def save_target(self,sid,field,label='',unit='',*,expected_sha=None,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('目标指标须由使用者确认。')
        body=self._body(sid,expected_sha);frame=self.s.ws.load_upload(self.s.a.session(sid)['upload_id'])
        safe={f['field'] for f in profile(frame)['fields'] if not f['likely_identifier']}
        if field is not None and field not in safe:raise DesignError('请选择当前表中可用于分析且非疑似标识的字段。')
        if field and field in body['predictors']+body['covariates']+[body['treatment']]:raise DesignError('该字段已有其他分析角色，请先在高级设置核对角色；引导不会自动改写。')
        if body['outcome']!=field:
            body['method_facts']={};body['metric_kind']='unknown';body['metric_window']=''
        old=body['outcome'];body.update(outcome=field,metric_label=label.strip() if field else '',metric_unit=unit.strip() if field else '')
        for value in body['fields']:
            if value['field']==old and old!=field and value['role']=='outcome':value['role']='unspecified'
            if value['field']==field:value.update(role='outcome',unit=unit.strip())
        self.s.contracts.save(sid,body,expected_sha=expected_sha,human_confirmed=True)
        self._step(sid,3)
    def finish(self,sid,intention,*,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('分析目标须由使用者选择。')
        self._step(sid,4,intention)
        return self.question(sid,intention)
    def question(self,sid,intention):
        row=self.s.contracts.latest(sid);target=(row['body'].get('outcome') if row else None)
        name=('目标指标 '+target) if target else '当前表的可用字段'
        if intention=='describe':return {'question':'请分析'+name+'的缺失、分布与频数，生成基础图表和报告；保留原始记录，只做描述统计。','mode':'plan'}
        if intention=='association':return {'question':'围绕'+name+'推荐可回答的关联问题，说明还需确认的自变量和观测口径；不要推断因果。','mode':'explore'}
        if intention=='effect':return {'question':'我希望评估某项措施对'+name+'的效果。请先说明需要的处理、分配和时间信息；现有信息不足时明确缺项，暂不执行分析。','mode':'method'}
        return {'question':'请根据当前表和已确认指标推荐可回答的问题，区分已有字段和需要补充的信息。','mode':'explore'}
