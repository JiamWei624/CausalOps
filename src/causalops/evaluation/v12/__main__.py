"""Launch isolated attempts, retaining failed requests and all scheduled slots."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import getpass,json,os
from pathlib import Path
import subprocess,sys
from time import perf_counter
from uuid import uuid4

from .inputs import CASES
from .rubric import grade
from causalops.evaluation.v1.worker import save


def lines(path):
    return [json.loads(s) for s in path.read_text('utf8').splitlines() if s.strip()] if path.exists() else []


def one(root,case,number,mode,key,timeout,worker_module='causalops.evaluation.v12.attempt'):
    folder=root/case/f'attempt-{number}'
    env=dict(os.environ,CAUSALOPS_HOME=str(folder/'work'),PYTHONDONTWRITEBYTECODE='1')
    if key:env['DEEPSEEK_API_KEY']=key
    else:env.pop('DEEPSEEK_API_KEY',None)
    begin=perf_counter()
    error=None
    try:
        rc=subprocess.run([sys.executable,'-m',worker_module,str(folder),case,mode],
            env=env,timeout=timeout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
        if rc:error=f'尝试进程退出 {rc}'
    except subprocess.TimeoutExpired:error='尝试超时'
    path=folder/'observation.json'
    obs=json.loads(path.read_text('utf8')) if path.exists() else dict(errors=[error or '缺少观测'])
    score=grade(case,obs)
    if error:score.update(结果='失败',错误=[error])
    calls=lines(folder/'requests.jsonl');responses=lines(folder/'responses.jsonl')
    score.update(任务=case,尝试=number,耗时秒=perf_counter()-begin,发起请求=len(calls),完成响应=len(responses),
        模式=mode,结构化输出=[dict(种类=r['schema'],有效=r['valid']) for r in responses],
        输入令牌=sum((r['telemetry'].get('input_tokens') or 0) for r in responses),
        输出令牌=sum((r['telemetry'].get('output_tokens') or 0) for r in responses),
        有用量的响应=sum(r['telemetry'].get('total_tokens') is not None for r in responses))
    folder.mkdir(exist_ok=True,parents=True);save(folder/'score.json',score)
    print(mode,case,number,score['结果'],score['发起请求'],flush=True)
    return score


def stats(rows):
    def rate(values):
        values=[x for x in values if x is not None]
        return dict(通过=sum(map(bool,values)),有效数=len(values))
    calls=[v for r in rows for v in r['结构化输出']]
    adv=[r['模型建议'] for r in rows if r['模型建议'] is not None]
    return dict(尝试数=len(rows),任务正确处理率=rate(r['结果']!='失败' for r in rows),
                方法建议合理率=rate(a['method'] and a['action'] and a['fields'] for a in adv if a['method'] is not None),
                模型研究条件识别率=rate(a['conditions'] for a in adv),
                结构化方案有效率=rate(v['有效'] for v in calls if v['种类']=='Plan'),
                独立研究建议结构有效率=rate(v['有效'] for v in calls if v['种类']=='Advice'),
                关键条件识别率=rate(r['关键条件'] for r in rows),
                不合法执行阻断率=rate(r['非法执行阻断'] for r in rows),
                数值与引用判据=rate(r['数字及引用'] for r in rows),多轮版本正确率=rate(r['多轮版本'] for r in rows),
                严重失败=sum(r['严重失败'] for r in rows),
                耗时秒=sum(r['耗时秒'] for r in rows),模型请求=sum(r['发起请求'] for r in rows),
                有用量的响应=sum(r['有用量的响应'] for r in rows),输入令牌=sum(r['输入令牌'] for r in rows),
                输出令牌=sum(r['输出令牌'] for r in rows))


def main(*,worker_module='causalops.evaluation.v12.attempt'):
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['local','deepseek'],default='local')
    p.add_argument('--rounds',type=int,choices=[1,2,3],default=3);p.add_argument('--jobs',type=int,choices=range(1,5),default=3)
    p.add_argument('--cases',nargs='+',choices=list(CASES),default=list(CASES))
    p.add_argument('--official-consent',action='store_true');p.add_argument('--smoke-first',action='store_true')
    args=p.parse_args()
    if len(set(args.cases))!=len(args.cases):p.error('任务重复')
    root=args.output.resolve()/(args.mode+'-'+uuid4().hex[:12])
    if os.environ.get('CAUSALOPS_HOME') and root.is_relative_to(Path(os.environ['CAUSALOPS_HOME']).resolve()):p.error('请使用隔离目录')
    key=None
    if args.mode=='deepseek':
        if not args.official_consent:p.error('缺少官方接口发送许可')
        key=os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('Official key (hidden): ')
        if not key:p.error('未配置密钥')
    git=os.environ.get('CAUSALOPS_EVAL_GIT','git')
    rev=subprocess.check_output([git,'rev-parse','HEAD'],text=True,cwd=Path(__file__).parent).strip()
    root.mkdir(parents=True)
    jobs=[(case,n) for n in range(1,args.rounds+1) for case in args.cases]
    save(root/'manifest.json',dict(提交=rev,模式=args.mode,时间=datetime.now(timezone.utc).isoformat(),计划=jobs,并行=args.jobs))
    print(root,flush=True)
    if args.smoke_first and key:
        r=one(root/'smoke','C07',1,args.mode,key,150,worker_module)
        if not any(x['有效'] for x in r['结构化输出']) or not r['有用量的响应']:
            save(root/'unstarted.json',dict(原因='冒烟调用未得到有效结构与用量',未测试=jobs))
            raise SystemExit('真实模型冒烟失败；正式尝试未开始')
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows=list(pool.map(lambda x:one(root,*x,args.mode,key,180,worker_module),jobs))
    save(root/'results.json',rows);save(root/'summary.json',stats(rows))
    print('完成',root,flush=True)


if __name__=='__main__':main()
