"""Prepare a fresh, byte-identical attempt. No imports from the private grader."""
import argparse,sqlite3,shutil
from pathlib import Path
from common import CASES,ROOT,bounded,inventory,read,save,sha
from packets import PACKETS

def prepare(case,mode,attempt):
    case=case.upper()
    if case not in CASES or mode not in ('local','deepseek','fixed','adaptive') or not 1<=attempt<=3:raise ValueError('任务或尝试编号不受支持')
    strategy='fixed' if mode in ('local','fixed') else 'adaptive'
    if strategy=='fixed' and attempt!=1:raise ValueError('固定脚本每题一次')
    mode=strategy
    seal=read(ROOT/'frozen.json')
    base=ROOT/'fixtures'/case
    if sha(base/'initial.json')!=seal['fixtures'][case]['initial'] or sha(base/'files.json')!=seal['fixtures'][case]['files']:
        raise ValueError('冻结初始元数据的摘要不一致')
    expected=read(base/'files.json')
    if inventory(base/'workspace')!=expected:raise ValueError('初始库已变化')
    folder=bounded(ROOT/'attempts'/mode/case/f'attempt-{attempt}')
    folder.mkdir(parents=True,exist_ok=False)
    work=folder/'workspace'
    shutil.copytree(base/'workspace',work,ignore=shutil.ignore_patterns('*-wal','*-shm'))
    if inventory(work)!=expected:raise ValueError('初始副本内容与冻结版本不一致')
    # ResearchRepository stores two artifact paths as absolute names. Remap only
    # these paths on the verified copy, and verify each immutable artifact again.
    with sqlite3.connect(work/'research.sqlite3') as con:
        for rid,bundle,report in con.execute('select run_id,result_bundle_path,report_path from analysis_runs').fetchall():
            paths=[]
            for source in (bundle,report):
                rel=Path(source).resolve().relative_to((base/'workspace').resolve())
                local=(work/rel).resolve()
                if not local.is_relative_to(work.resolve()) or sha(local)!=expected[rel.as_posix()]:
                    raise ValueError('迁移产物路径校验失败')
                paths.append(str(local))
            con.execute('update analysis_runs set result_bundle_path=?, report_path=? where run_id=?',(*paths,rid))
    meta=read(base/'initial.json')
    question,followups=PACKETS[case]
    sequence=[question,*followups]
    if case=='B04':sequence.insert(0,{'action':'select_report','terms':['订单']})
    if case in ('B05','B06'):sequence.insert(-1,{'action':'review_if_matching'})
    launch=dict(case_id=case,mode=mode,strategy=strategy,attempt=attempt,workspace=str(work),session_id=meta['session_id'],
        question=question,initial_metadata_sha256=sha(base/'initial.json'),freeze_sha256=sha(ROOT/'frozen.json'),
        fixed_turns=sequence if strategy=='fixed' else [],product_mode='deepseek',product_commit=seal['product_commit'])
    save(folder/'launch.json',launch);print(folder/'launch.json',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True);q=s.add_parser('prepare')
    q.add_argument('--case',required=True,choices=CASES);q.add_argument('--mode',required=True,choices=['local','deepseek','fixed','adaptive'])
    q.add_argument('--attempt',required=True,type=int)
    a=p.parse_args();prepare(a.case,a.mode,a.attempt)
