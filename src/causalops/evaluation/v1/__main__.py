"""CLI for the local benchmark. Each attempt runs in its own process and fresh workspace."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

from .cases import TASKS
from .score import grade, INVALID, REPORTS
from .worker import save
from .evidence import event_index


def summary(rows):
    good={'已通过','正确阻断'}
    def rate(items, predicate):
        items=list(items)
        count=sum(bool(predicate(r)) for r in items)
        return dict(分子=count,分母=len(items),比例=count/len(items) if items else None)
    return {
        '任务正确处理率':rate(rows,lambda r:r['状态'] in good),
        '有效报告完成率':rate((r for r in rows if r['任务'] in REPORTS),lambda r:r['有效报告']),
        '首次尝试成功率':rate(rows,lambda r:r['状态'] in good),
        '不合法任务阻断率':rate((r for r in rows if r['任务'] in INVALID),lambda r:r['状态']=='正确阻断'),
        '故障恢复率':rate((r for r in rows if r['任务']=='T10'),lambda r:r['状态']=='已通过'),
        **{k:sum(r[k] for r in rows) for k in ('有效操作次数','对话轮次','方法错误','解释错误','任务总耗时秒')},
        '状态计数':dict(Counter(r['状态'] for r in rows))}


def run(args):
    git=shutil.which('git') or os.environ.get('CAUSALOPS_EVAL_GIT')
    if not git:raise SystemExit('请设置 CAUSALOPS_EVAL_GIT 或将 Git 加入 PATH。')
    source=Path(__file__).resolve().parent
    rev=subprocess.check_output([git,'-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output([git,'-C',str(source),'status','--porcelain'],text=True).strip():rev+='-dirty'
    official = os.environ.get('CAUSALOPS_HOME')
    if official and args.output.resolve().is_relative_to(Path(official).resolve()):
        raise SystemExit('请选择正式用户工作区以外的专用输出目录')
    root=args.output.resolve()/('eval-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    rows=[]
    for case in args.cases:
        folder=root/case/'attempt-1'
        env=dict(os.environ, CAUSALOPS_EVAL_CHILD='1',CAUSALOPS_HOME=str(folder/'work'),PYTHONDONTWRITEBYTECODE='1')
        cmd=[sys.executable,'-m','causalops.evaluation.v1.worker',case,str(folder),rev]
        if args.archive:cmd+=['--archive',str(args.archive.resolve())]
        start=perf_counter()
        error=None
        try:
            child=subprocess.run(cmd,env=env,timeout=args.timeout,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if child.returncode:error='评测子进程异常退出：'+str(child.returncode)
        except subprocess.TimeoutExpired:error='超过单题时限'
        elapsed=perf_counter()-start
        if not error:
            try:r=grade(folder,case)
            except Exception as exc:error='评分器无法复核：'+type(exc).__name__
        if error:
            path=folder/'events.jsonl'
            events=[json.loads(s) for s in path.read_text('utf8').splitlines() if s.strip()] if path.exists() else []
            r=dict(任务=case,状态='失败',判据={},异常=[error],有效报告=False,方法错误=0,解释错误=0,
                   对话轮次=sum(e['事件']=='用户提交研究问题' for e in events),
                   有效操作次数=sum(e['事件'] in ('数据成功加载','用户提交研究问题','用户批准指定方案','研究方案修订','故障恢复') for e in events))
        folder.mkdir(parents=True,exist_ok=True)
        log=folder/'events.jsonl'
        trail=[json.loads(s) for s in log.read_text('utf8').splitlines() if s.strip()] if log.exists() else []
        final=dict(任务=case,尝试=folder.name,会话=trail[-1]['会话'] if trail else None,提交=rev,模式='本地规则',
                   时间=datetime.now(timezone.utc).isoformat(),顺序=len(trail)+1,事件='评测任务结束',状态=r['状态'],
                   流程=None,方案版本=None,运行=None,耗时秒=elapsed,详情={})
        with log.open('a',encoding='utf8') as f:f.write(json.dumps(final,ensure_ascii=False)+'\n')
        r['任务总耗时秒']=elapsed
        save(folder/'score.json',r);rows.append(r)
        print(case,r['状态'],flush=True)
    event_index(root,args.cases)
    scores=summary(rows)
    save(root/'summary.json',dict(版本=rev,模式='本地规则；未进行真实模型评测',指标=scores))
    save(root/'results.json',rows)
    report=['# CausalOps Eval V1 · 自动化验收报告','',f'源码版本：`{rev}`。每题首次独立尝试；未进行真实模型评测。此处不涉及独立用户试用。','',
            '|任务|处理结果|用时（秒）|未通过判据或异常|','|---|---|---:|---|']
    for r in rows:
        reasons=[k for k,v in r['判据'].items() if not v]+r['异常']
        report.append(f"|{r['任务']} {TASKS[r['任务']]['title']}|{r['状态']}|{r['任务总耗时秒']:.2f}|"+('；'.join(reasons) or '—')+'|')
    report+=['','## 汇总','']
    for k,v in scores.items():
        if isinstance(v,dict) and '分母' in v:report.append(f"- {k}：{v['分子']}/{v['分母']}"+(f"（{v['比例']:.1%}）" if v['分母'] else '（不适用）'))
        elif not isinstance(v,dict):report.append(f'- {k}：{v:.2f}' if isinstance(v,float) else f'- {k}：{v}')
    report+=['','## 复核与后续','每题的 events.jsonl、observations.json、score.json、独立数据库及导出 HTML 均在任务子目录。先查未通过判据，再对照领域事件与批准回执。咨询类自然语言建议的可读性留给人工复核。下一阶段在同一输入及相同批准条件下接入已授权模型，对关键边界重复运行，并由独立评审盲读报告。']
    (root/'报告.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    print(root,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description='运行独立的本地研究任务评测')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cases',nargs='+',choices=list(TASKS),default=list(TASKS))
    p.add_argument('--archive',type=Path,default=os.environ.get('CAUSALOPS_HILLSTROM_ARCHIVE'))
    p.add_argument('--timeout',type=int,default=120)
    args=p.parse_args()
    if args.timeout<=0 or len(set(args.cases))!=len(args.cases):p.error('任务不能重复，时限必须为正数')
    run(args)
