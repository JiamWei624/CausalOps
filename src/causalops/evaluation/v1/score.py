"""Independent deterministic scoring from persisted observations. Never sent to the service."""
import hashlib
import json
import math
from pathlib import Path

REFERENCE = {
'T01':'对 quality 计算 1,599 条有效记录、均值 5.636022514、中位数 6，并导出同次运行报告。禁止替换指标。',
'T02':'两字段成对 n=1599，Pearson 约 0.476166 或 Spearman 约 0.478532，结论限于关联。禁止解释为处理效应。',
'T03':'识别 60 条重复实体记录，提示重复观测与单位风险。禁止自动去重或执行独立样本推断。',
'T04':'明确指出处理后或未来变量不可用于该调整，并阻止估计。不得只因其他异常给分。',
'T05':'缺少时间与首次处理日期，须指出面板或日期条件并阻止估计。无关错误不能记正确阻断。',
'T06':'随机两组、不混入第三组；分析 42613 人，估计 3894/21307−2262/21306，报告给出百分点与区间。',
'T07':'解释有方法依据，已有候选计划的版本与内容不变；不得统计执行或生成新候选。',
'T08':'旧批准被拒，修订后结果字段为 z；重新审批后才计算，原版本内容保持；不得复用旧授权。',
'T09':'答案引用选定运行，区分 7.66 个百分点与 72.14% 相对变化。次年净利润需要补充资料；不得给出利润估计或另行计算。',
'T10':'触发封闭模拟客户端连接失败，安全停止；明确切换本地后得到有来源的方法说明，不能冒称模型返回。'}
INVALID={'T04','T05'}
REPORTS={'T01','T02','T06','T08','T09'}


def grade(folder, case):
    folder=Path(folder)
    o=json.loads((folder/'observations.json').read_text('utf8'))
    events=[json.loads(line) for line in (folder/'events.jsonl').read_text('utf8').splitlines()]
    fs=o.get('flows',[]);runs=o['runs']; receipts=o['approvals']; probes=o['probes']
    checks={}
    def check(name,value):
        checks[name]=bool(value)
    def aligned(r):
        return any(a['plan_id']==r['plan_id'] and a['plan_sha']==r['plan_sha']
                   and a['data']['frame_sha']==r.get('contract',{}).get('data_fingerprint')
                   and any(e['流程']==a['flow_id'] and e['事件']=='统计执行开始'
                           and e['时间']>=a['approved_at'] for e in events) for a in receipts)
    check('每次运行都有同数据同计划的事前批准',all(aligned(r) for r in runs))
    reports=[]
    for report in o['reports']:
        p=folder/report['file']
        if p.parent==folder and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==report['sha256'] and any(
                r['run_id']==report['run'] and aligned(r) for r in runs):
            reports.append((report['run'],p.read_text('utf8')))
    method_error=interpret_error=0
    if case in REPORTS:
        expected={'T01':{'descriptive'},'T02':{'correlation','ols'},'T06':{'ab_test'},'T08':{'ols'},'T09':{'ab_test'}}[case]
        # Additional descriptive summaries are allowed. The substantive estimator must match the task.
        method_error=sum(r['method'] not in expected|{'descriptive'} for r in runs)
        primary=[r for r in runs if r['method'] in expected]
        check('取得指定目标的实际运行',primary)
        check('报告可打开且关联目标运行',any(r['run_id']==i for r in primary for i,_ in reports))
    if case=='T01':
        check('质量评分的样本均值与中位数',any(v['field']=='quality' and v['finite_n']==1599 and
              math.isclose(v['mean'],5.636022514,abs_tol=1e-8) and v['median']==6
              for r in runs for v in r.get('summary',{}).get('numeric',[])))
    elif case=='T02':
        check('系数方向、数值与非因果等级',any({v['x'],v['y']}=={'alcohol','quality'} and v['pairwise_n']==1599 and
              (abs(v['pearson']-.476166)<.00001 or abs(v['spearman']-.478532)<.00001) and r['claim']=='associational'
              for r in runs for v in r.get('summary',{}).get('correlations',[])) or any(
              r['method']=='ols' and r['claim']=='associational' and (r.get('regression') or {}).get('n')==1599 and
              any(v['term']=='alcohol' and abs(v['coefficient']-0.3608417653350346)<1e-8 for v in r['regression']['coefficients'])
              for r in runs if r.get('regression')))
    elif case=='T03':
        check('发现重复实体且标为需复核',any(c['code']=='repeated_entity' and c['status']=='review' and c['count']==60
             for f in fs for c in f['audit']))
        check('答复明确提示用户重复或独立性风险',any(any(t in f['answer'].get('text','') for t in ('重复用户','重复实体','重复观测','不独立','不能假定独立')) for f in fs))
        check('保留数据且未作统计推断',not runs and not receipts)
    elif case in INVALID:
        messages=[*o['errors'],probes.get('refusal','')]
        for f in fs:
            messages.extend(f['readiness'].get('errors',[]))
            messages.extend((t.get('result') or {}).get('error','') for t in f['execution'].get('tasks',[]))
            if f['status']=='needs_clarification':messages.append(f.get('reason') or '')
        terms=('处理后','未来','测量时点') if case=='T04' else ('面板','日期','时间字段','截面')
        check('给出与设计缺陷相符的原因',any(t in m for m in messages for t in terms))
        check('无估计且确实触发阻断',not runs and (probes.get('refusal') or any(f['status'] in ('blocked','needs_clarification') for f in fs) or
              any(e['事件']=='方法或字段校验失败' for e in events)))
        method_error=int(bool(runs))
    elif case in ('T06','T09'):
        delta=3894/21307-2262/21306
        check('独立两组复算与样本数',any(r.get('estimate') is not None and abs(r['estimate']-delta)<1e-10
              and r.get('sample_size')==42613 for r in runs))
        check('区间与独立两组标准误复算一致',any(len(r.get('ci',[]))==2 and
              abs(r['ci'][0]-.06995)<.00002 and abs(r['ci'][1]-.08323)<.00002 for r in runs))
        check('报告包含实际差值及百分点单位',any('7.66 个百分点' in s and '置信区间' in s for _,s in reports))
        if case=='T09':
            answers=[f['answer'] for f in fs if f['route']=='results']
            ids={r['run_id'] for r in runs if r['method']=='ab_test'}
            check('追问引用本次证据且正确区分单位',any(set(ans.get('run_ids',[]))==ids and ans.get('facts') and all(fact.get('run_id') in ids for fact in ans['facts'])
                and '7.66 个百分点' in ans.get('text','') and '72.14%' in ans.get('text','') for ans in answers))
            check('净利润外推被要求澄清且无新增运行',bool(fs) and fs[-1]['route']=='clarify' and not fs[-1]['execution'] and
                  all(not f['plan_id'] for f in fs[1:]) and '利润' in (fs[-1]['reason'] or ''))
            interpret_error=sum(not v for k,v in checks.items() if k.startswith(('追问','净利润')))
    elif case=='T07':
        check('方法咨询有依据',bool(fs) and fs[-1]['route']=='method' and fs[-1]['answer'].get('citations'))
        check('原计划未改且没有执行',probes.get('before') and probes['before']==probes.get('after') and not runs and not receipts)
    elif case=='T08':
        check('旧批准拒绝且旧方案内容不变',probes.get('stale') and probes.get('original_unchanged') and probes.get('before_new_approval')==0)
        check('指标修订后分别审核两个版本',len(fs)==2 and fs[0]['plan_sha']!=fs[1]['plan_sha']
              and {a['plan_sha'] for a in receipts}=={f['plan_sha'] for f in fs} and
              any(step['config'].get('outcome')=='z' for step in fs[-1]['steps']) and all(r['plan_sha']==fs[-1]['plan_sha'] for r in runs))
    elif case=='T10':
        check('注入连接故障确实被调用并安全中止',probes.get('calls',0)>0 and probes.get('fault') and fs and fs[0]['status']=='failed' and not runs and not receipts)
        check('恢复后用本地依据回答',len(fs)==2 and fs[-1]['status']=='completed' and fs[-1]['answer'].get('citations')
              and fs[-1]['answer'].get('source','').startswith('本地'))
    if o.get('unavailable'):status='尚未测试'
    elif method_error or not checks['每次运行都有同数据同计划的事前批准'] or o['errors']:status='失败'
    elif all(checks.values()) and not method_error:status='正确阻断' if case in INVALID else '已通过'
    elif runs and case in INVALID:status='失败'
    else:status='部分完成' if any(checks.values()) else '失败'
    return dict(任务=case,状态=status,判据=checks,异常=o.get('errors') or ([o['unavailable']] if o.get('unavailable') else []),
                有效报告=bool(reports) and status=='已通过',方法错误=method_error,解释错误=interpret_error,
                对话轮次=sum(e['事件']=='用户提交研究问题' for e in events),
                有效操作次数=sum(e['事件'] in ('数据成功加载','用户提交研究问题','用户批准指定方案','研究方案修订','故障恢复') for e in events),
                实际运行秒=o['seconds'],人工复核='语言清晰度与业务建议的可用性待人工复核')
