"""Real user trials only. Script tests are never inserted as human observations."""
from __future__ import annotations
import json,uuid,hashlib,math
from datetime import datetime,timezone
from causalops.general.service import DesignError

def timestamp():return datetime.now(timezone.utc).isoformat()
class UserTrials:
    def __init__(self,ws):
        self.ws=ws
        with ws.connection() as c:c.execute('CREATE TABLE IF NOT EXISTS user_value_trials(id TEXT PRIMARY KEY,participant TEXT NOT NULL,pair_id TEXT NOT NULL,mode TEXT NOT NULL,task TEXT NOT NULL,started TEXT NOT NULL,finished TEXT,result TEXT)')
    def start(self,participant,pair_id,mode,task):
        if mode not in ('manual','assistant') or not participant or len(participant)>40:raise DesignError('请使用匿名编号与人工/助手模式。')
        if not pair_id.strip() or not task.strip():raise DesignError('请填写配对任务编号与同一验收目标。')
        tid=uuid.uuid4().hex
        with self.ws.connection() as c:c.execute('INSERT INTO user_value_trials VALUES(?,?,?,?,?,?,?,?)',(tid,participant,pair_id,mode,task,timestamp(),None,None))
        return tid
    def finish(self,tid,*,reviewed_correct,error_count,rework_count,report_exported,run_id=None,note=''):
        if not isinstance(reviewed_correct,bool) or error_count<0 or rework_count<0:raise DesignError('结果质量须由评审核对；错误/返工不能负数。')
        with self.ws.connection() as c:
            r=c.execute('SELECT * FROM user_value_trials WHERE id=?',(tid,)).fetchone()
            if not r or r[6]:raise DesignError('计时不存在或已结束。')
            finish=timestamp();seconds=(datetime.fromisoformat(finish)-datetime.fromisoformat(r[5])).total_seconds()
            if seconds<=0:raise DesignError('计时异常；不能报告负耗时。')
            result=dict(seconds=seconds,reviewed_correct=reviewed_correct,error_count=error_count,rework_count=rework_count,report_exported=bool(report_exported),run_id=run_id,note=note[:2000],provenance='human_ui_submission_requires_independent_review')
            c.execute('UPDATE user_value_trials SET finished=?,result=? WHERE id=?',(finish,json.dumps(result,ensure_ascii=False),tid))
        return result
    def records(self):
        with self.ws.connection() as c:rows=c.execute('SELECT * FROM user_value_trials ORDER BY started').fetchall()
        return [dict(id=r[0],participant=r[1],pair_id=r[2],mode=r[3],task=r[4],started=r[5],finished=r[6],result=json.loads(r[7]) if r[7] else None) for r in rows]
    def report(self):
        records=self.records();complete=[r for r in records if r['result']];pairs={}
        for r in complete:pairs.setdefault((r['participant'],r['pair_id']),{}).setdefault(r['mode'],[]).append(r)
        valid=[]
        for key,modes in pairs.items():
            if set(modes)!= {'manual','assistant'} or any(len(v)!=1 for v in modes.values()):continue
            a,b=modes['manual'][0],modes['assistant'][0]
            if a['task']!=b['task'] or not all(x['result']['reviewed_correct'] and x['result']['report_exported'] for x in (a,b)):continue
            valid.append(dict(participant=key[0],pair_id=key[1],manual_seconds=a['result']['seconds'],assistant_seconds=b['result']['seconds'],saved_seconds=a['result']['seconds']-b['result']['seconds'],relative_time_reduction=1-b['result']['seconds']/a['result']['seconds']))
        return {'status':'pending_real_participants' if not complete else 'observational_usability_records_not_randomized_causal_evidence','completed_tasks':len(complete),'valid_correct_exported_pairs':valid,'records':records,'limitations':['参与者必须是真实未参与开发者；本模块不生成假参与者。','评审核对正确性、同一任务难度与报告；顺序/学习效应需在研究设计中平衡。','记录含阅读、思考和操作时间；不能用脚本速度替代人类效率。','少量配对结果是可用性线索，不自动作为总体效率的因果证明。']}
