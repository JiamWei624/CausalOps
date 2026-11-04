"""Guarded, one-time seal of case libraries, independent numerical truths and three-layer protocol."""
from pathlib import Path
import subprocess
from common import CASES,ROOT,inventory,read,save,sha
from fixture_data import materials

APP=Path(__file__).resolve().parent
REPO=APP.parents[2]
def main():
    if (ROOT/'attempts').exists() or (ROOT/'frozen.json').exists():raise SystemExit('已有正式尝试或冻结版本，不得覆盖')
    hidden=ROOT/'sealed';hidden.mkdir(exist_ok=True)
    keys={}
    for case in CASES:
        df,body=materials(case)
        meta=read(ROOT/'fixtures'/case/'initial.json')
        if inventory(ROOT/'fixtures'/case/'workspace')!=read(ROOT/'fixtures'/case/'files.json'):raise SystemExit('初始库摘要不符')
        runs=meta['runs']
        key=dict(records=len(df),old_ids=[r['id'] for r in runs])
        if case=='B01':
            groups=df.groupby('assigned').visit.agg(['sum','count','mean'])
            key.update(control_percent=100*groups.loc[0,'mean'],treated_percent=100*groups.loc[1,'mean'],
                pp=100*(groups.loc[1,'mean']-groups.loc[0,'mean']),method='ab_test',source_run=runs[0]['id'])
        if case=='B02':
            key.update(r=df.satisfaction.corr(df.spend),n=len(df),method='correlation',source_run=runs[0]['id'])
        if case=='B03':
            key.update(ratio=df.orders.sum()/df.visitors.sum(),orders=int(df.orders.sum()),visits=int(df.visitors.sum()),zero_days=int(df.orders.eq(0).sum()))
        if case=='B04':
            key.update(mean=df.orders.mean(),threshold=9,source_run=min(runs,key=lambda r:r['version'])['id'],method='descriptive')
        if case=='B05':
            key.update(mean=df.visitors.mean(),outcome='visitors',method='descriptive',old_run=runs[0]['id'])
        if case=='B06':
            window=df.sort_values('day').tail(7)
            key.update(mean=window.orders.mean(),window_start=window.day.min(),window_end=window.day.max(),n=7,old_run=runs[0]['id'])
        keys[case]=key
    save(hidden/'gold.json',keys)
    filenames=['fixture_data.py','packets.py','control.py','seed.py','common.py','freeze.py','grade.py','PROTOCOL.md']
    git='git'
    rev=subprocess.check_output([git,'-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    save(ROOT/'frozen.json',dict(product_commit=rev,strategy_slots={'fixed':1,'adaptive':3},
        fixtures={c:{'files':sha(ROOT/'fixtures'/c/'files.json'),'initial':sha(ROOT/'fixtures'/c/'initial.json')} for c in CASES},
        code={p:sha(APP/p) for p in filenames},gold_sha256=sha(hidden/'gold.json')))
    print('冻结 SHA-256',sha(ROOT/'frozen.json'))
if __name__=='__main__':main()
