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
    def save_target(self,sid,field,label='',unit='',*,expected_sha=None,human_confirmed=False,time_field=None):
        if human_confirmed is not True:raise DesignError('目标指标须由使用者确认。')
        body=self._body(sid,expected_sha);frame=self.s.ws.load_upload(self.s.a.session(sid)['upload_id'])
        safe={f['field'] for f in profile(frame)['fields'] if not f['likely_identifier']}
        if field is not None and field not in safe:raise DesignError('请选择当前表中可用于分析且非疑似标识的字段。')
        if field and field in body['predictors']+body['covariates']+[body['treatment']]:raise DesignError('该字段已有其他分析角色，请先在高级设置核对角色；引导不会自动改写。')
        if body['outcome']!=field:
            body['method_facts']={};body['metric_kind']='unknown';body['metric_window']=''
        if time_field is not None:
            if time_field:
                import pandas as pd
                if time_field not in frame or pd.api.types.is_numeric_dtype(frame[time_field]):raise DesignError('请选择实际日期字段；年号、序号或数值编码不能直接当作日期。')
                if not pd.to_datetime(frame[time_field],errors='coerce').notna().any():raise DesignError('所选字段没有可解析日期，请先核对时间格式。')
            if body.get('time')!=(time_field or None):body['method_facts']={}
            body['time']=time_field or None
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
    def use_example(self,sid,*,expected_sha=None,human_confirmed=False):
        if human_confirmed is not True:raise DesignError('使用示例说明需要使用者明确确认。')
        from causalops.sample_data import example_context
        context=example_context(self.s.a,sid)
        if context is None:raise DesignError('当前数据不是内容校验通过的内置示例，不能套用示例含义。')
        body=self._body(sid,expected_sha);v=context['onboarding']
        if body.get('method_facts') or body.get('predictors') or body.get('covariates') or body.get('treatment') or (body.get('outcome') and body['outcome']!=v['target']):raise DesignError('当前已有自定义研究设置，请保留并逐步核对，不覆盖已有研究事实。')
        body.update(analysis_unit=v['analysis_unit'],outcome=v['target'],metric_label=v['metric_label'],metric_unit=v['metric_unit'],fields=[{'field':f['field'],'meaning':f['meaning'],'unit':f['unit'],'role':'outcome' if f['field']==v['target'] else 'measure','timing':'unknown'} for f in v['fields']])
        # Content-verified public sample metadata only; retain any human-entered scope.
        scope=body.setdefault('research',{})
        defaults={'population':'当前 UCI 红葡萄酒子集中的检测样本；不代表全部葡萄酒或消费者。','inclusion':'保留全部原始记录，不自动删除重复值或极端值。','provenance':context['attribution']+' '+context['landing_url']+'；许可：'+context['license'],'limitations':'观察性数据；质量评分与理化指标的关联不能直接解释为调整成分后的因果效果。'}
        for name,value in defaults.items():
            if not scope.get(name):scope[name]=value
        for field in body['fields']:field['source']=context['doi']
        self.s.contracts.save(sid,body,expected_sha=expected_sha,human_confirmed=True)
        return self.finish(sid,'describe',human_confirmed=True)

    def question(self,sid,intention):
        row=self.s.contracts.latest(sid);target=(row['body'].get('outcome') if row else None)
        name=('目标指标 '+target) if target else '当前表的可用字段'
        if intention=='describe':return {'question':'请分析'+name+'的缺失、分布与频数，生成基础图表和报告；保留原始记录，只做描述统计。','mode':'plan'}
        if intention=='association':return {'question':'围绕'+name+'推荐可回答的关联问题，说明还需确认的自变量和观测口径；不要推断因果。','mode':'explore'}
        if intention=='effect':return {'question':'我希望评估某项措施对'+name+'的效果。请先说明需要的处理、分配和时间信息；现有信息不足时明确缺项，暂不执行分析。','mode':'method'}
        return {'question':'请根据当前表和已确认指标推荐可回答的问题，区分已有字段和需要补充的信息。','mode':'explore'}
