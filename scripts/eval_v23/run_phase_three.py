"""Third-phase development rerun. Reuse frozen worker/data; no scoring/holdout imports."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import getpass
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
from run_pilot import worker,write,ROOT,DATA

TASKS=tuple(f"{c}{i:02}" for c in "ABCDE" for i in range(1,7))
REPO=Path(__file__).resolve().parents[2]
BASELINE="a23b54d"
FROZEN=("docs/evaluation/v23/development_tasks.json","docs/evaluation/v23/development_rubrics.json",
        "docs/evaluation/v23/data","scripts/eval_v23/run_pilot.py","scripts/eval_v23/datasets.py",
        "scripts/eval_v23/calibrate.py")
def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO,text=True).strip()
def validate(product):
    if git("diff",BASELINE,"--",*FROZEN):
        raise RuntimeError("冻结题目、数据、原工作进程或评分规则变化")
    if git("diff",product,"--","src") or git("diff","--","src"):
        raise RuntimeError("产品偏离冻结提交")
    return {"repository_commit":git("rev-parse","HEAD"),"product_commit":git("rev-parse",product),
            "product_tree":git("rev-parse",product+":src"),"scorer":"v23.2.1",
            "input_sha256":hashlib.sha256((ROOT/"development_tasks.json").read_bytes()).hexdigest(),
            "data_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file()}}
def launch(root,case,mode,key):
    folder=root/case
    folder.mkdir()
    env=dict(os.environ,CAUSALOPS_HOME=str(folder/"workspace"))
    env.pop("DEEPSEEK_API_KEY",None)
    if mode=="deepseek":env["DEEPSEEK_API_KEY"]=key
    start=time.perf_counter()
    try:
        with (folder/"worker.log").open("xb") as log:
            res=subprocess.run([sys.executable,__file__,str(folder),mode,"--worker",case],
                               env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420)
        status="完成" if res.returncode==0 and (folder/"observation.json").exists() else "运行器失败"
    except subprocess.TimeoutExpired:status="超时"
    write(folder/"status.json",{"case":case,"mode":mode,"status":status,"wall_s":round(time.perf_counter()-start,3)})
    print(case,status,flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("mode",choices=["local","deepseek"])
    parser.add_argument("--worker",choices=TASKS)
    parser.add_argument("--product")
    args=parser.parse_args()
    if args.worker:worker(args.folder,args.worker,args.mode)
    else:
        if not args.product:parser.error("须指定冻结产品提交")
        snapshot=validate(args.product)
        if args.folder.exists() or args.folder.resolve().is_relative_to(REPO):
            parser.error("使用仓库外全新证据目录，不覆盖历史")
        key=(os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("Official key (hidden): ")) if args.mode=="deepseek" else ""
        args.folder.mkdir(parents=True)
        write(args.folder/"batch.json",{**snapshot,"tasks":TASKS,"mode":args.mode,"max_workers":2,
                    "timeout_per_task_s":420,"worker":"unchanged run_pilot.worker",
                    "model":"deepseek-flash" if args.mode=="deepseek" else None})
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda case:launch(args.folder,case,args.mode,key),TASKS))
