from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math,re,sqlite3,uuid

class TimingStateError(ValueError):pass

class HumanTimingStore:
    """Self-operated timing, not a fabricated or independently observed user study."""
    def __init__(self,path:Path,clock=None):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        with self._connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS trials(
              trial_id TEXT PRIMARY KEY,participant TEXT NOT NULL,task_id TEXT NOT NULL,condition TEXT NOT NULL,status TEXT NOT NULL,
              started TEXT NOT NULL,active_since TEXT,elapsed REAL NOT NULL,reference_json TEXT NOT NULL,answer_json TEXT,score_json TEXT,submitted TEXT);
              CREATE UNIQUE INDEX IF NOT EXISTS one_active_trial ON trials(participant) WHERE status IN ('running','paused');
              CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,trial_id TEXT NOT NULL,event TEXT NOT NULL,at_utc TEXT NOT NULL);''')
    def _connect(self):
        c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
    def _now(self):
        n=self.clock()
        if n.tzinfo is None:raise TimingStateError('Clock must be timezone-aware')
        return n.astimezone(timezone.utc)
    def _event(self,c,trial_id,event,at):c.execute('INSERT INTO events VALUES (?,?,?,?)',(uuid.uuid4().hex,trial_id,event,at))
    def start(self,participant,task_id,condition,reference):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',participant):raise TimingStateError('请使用不含姓名的英数字别名。')
        if condition not in {'script','agent'}:raise TimingStateError('Unknown condition')
        if not all(k in reference for k in ['estimate','lower','upper','claim','task_id','data_sha256']):raise TimingStateError('Reference is incomplete')
        if reference['task_id']!=task_id:raise TimingStateError('Reference task mismatch')
        now=self._now().isoformat();trial_id=uuid.uuid4().hex
        try:
            with self._connect() as c:
                c.execute('INSERT INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(trial_id,participant,task_id,condition,'running',now,now,0,json.dumps(reference),None,None,None))
                self._event(c,trial_id,'start',now)
        except sqlite3.IntegrityError as e:raise TimingStateError('该别名已有进行中或暂停的任务，请先完成或放弃。') from e
        return trial_id
    def get(self,trial_id):
        with self._connect() as c:r=c.execute('SELECT * FROM trials WHERE trial_id=?',(trial_id,)).fetchone()
        if r is None:raise TimingStateError('Unknown trial')
        d=dict(r);elapsed=float(d['elapsed'])
        if d['status']=='running':
            delta=(self._now()-datetime.fromisoformat(d['active_since'])).total_seconds()
            if delta<0:raise TimingStateError('系统时钟倒退，不能生成有效耗时。')
            elapsed+=delta
        d['active_elapsed_seconds']=elapsed
        return d
    def _change(self,trial_id,event,answer=None):
        now=self._now();stamp=now.isoformat()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM trials WHERE trial_id=?',(trial_id,)).fetchone()
            if r is None:raise TimingStateError('Unknown trial')
            old=r['status'];elapsed=float(r['elapsed'])
            allowed={'pause':{'running'},'resume':{'paused'},'submit':{'running','paused'},'abandon':{'running','paused'}}
            if old not in allowed[event]:raise TimingStateError('当前状态不允许该操作，重复提交不会计入。')
            if old=='running':
                delta=(now-datetime.fromisoformat(r['active_since'])).total_seconds()
                if delta<0:raise TimingStateError('系统时钟倒退。')
                elapsed+=delta
            status={'pause':'paused','resume':'running','submit':'submitted','abandon':'abandoned'}[event]
            score=None
            if event=='submit':score=self.score(answer,json.loads(r['reference_json']))
            c.execute('UPDATE trials SET status=?,active_since=?,elapsed=?,answer_json=?,score_json=?,submitted=? WHERE trial_id=?',
                (status,stamp if status=='running' else None,elapsed,json.dumps(answer,ensure_ascii=False) if answer is not None else None,
                 json.dumps(score,ensure_ascii=False) if score else None,stamp if event=='submit' else None,trial_id))
            self._event(c,trial_id,event,stamp)
        return self.get(trial_id)
    def pause(self,t):return self._change(t,'pause')
    def resume(self,t):return self._change(t,'resume')
    def abandon(self,t):return self._change(t,'abandon')
    def submit(self,t,a):return self._change(t,'submit',a)
    @staticmethod
    def score(answer,reference):
        if not answer or answer.get('unit') not in {'raw','percentage_points'}:raise TimingStateError('请填写单位与答案。')
        factor=100 if answer['unit']=='percentage_points' else 1
        if factor==100 and not reference.get('binary'):raise TimingStateError('连续指标不能填成百分点。')
        values={}
        for k in ['estimate','lower','upper']:
            try:v=float(answer[k])/factor
            except (KeyError,ValueError,TypeError) as e:raise TimingStateError('请填写估计值和区间。') from e
            if not math.isfinite(v):raise TimingStateError('不接受无穷大或空值。')
            values[k]=v
        if values['lower']>values['upper']:raise TimingStateError('区间上下界倒置。')
        if not isinstance(answer.get('explanation'),str) or len(answer['explanation'].strip())<10:raise TimingStateError('请写一句实际含义和后续建议。')
        if answer.get('claim') not in {'identified_causal','reduced_form','associational','descriptive'}:raise TimingStateError('请选择结论等级。')
        checks={k:abs(values[k]-reference[k])<=max(5e-4,abs(reference[k])*1e-4) for k in values}
        checks['claim']=answer['claim']==reference['claim']
        return {'objective_checks':checks,'objective_passed':all(checks.values()),'business_explanation_review':'pending_human_review',
                'independent_observer':False,'timing_source':'self_operated_server_utc_with_explicit_pauses'}
    def list_trials(self,participant=None):
        with self._connect() as c:
            q='SELECT trial_id FROM trials';params=()
            if participant:q+=' WHERE participant=?';params=(participant,)
            q+=' ORDER BY started';ids=[r['trial_id'] for r in c.execute(q,params)]
        return [self.get(t) for t in ids]
    def export(self):
        rows=self.list_trials()
        return {'trials':rows,'submitted_count':sum(r['status']=='submitted' for r in rows),
                'human_savings_claim_validated':False,'note':'无独立观察与业务解释复核时，仅为自助试用记录。未开始的试验不会自动生成耗时。'}