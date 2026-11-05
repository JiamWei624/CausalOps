"""Second-phase execution only. Import the frozen worker; never import scoring or references."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from run_pilot import worker, write, read, ROOT, DATA, PILOT

REMAINING = tuple(f"{c}{i:02}" for c in "ABCDE" for i in range(3,7))
BASELINE = "a3302c0"
REPO = Path(__file__).resolve().parents[2]

def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO,text=True).strip()

def validate_product():
    if git("diff",BASELINE,"--","src"):
        raise RuntimeError("被测产品源码偏离第一期基线，停止")
    if git("diff",BASELINE,"--","docs/evaluation/v23/development_tasks.json",
           "docs/evaluation/v23/development_rubrics.json","docs/evaluation/v23/data",
           "scripts/eval_v23/run_pilot.py","scripts/eval_v23/datasets.py"):
        raise RuntimeError("题目、数据或原工作进程变化，停止")
    return {"repository_commit":git("rev-parse","HEAD"),
            "product_tree":git("rev-parse","HEAD:src"),
            "baseline_product_tree":git("rev-parse",BASELINE+":src"),
            "input_sha256":hashlib.sha256((ROOT/"development_tasks.json").read_bytes()).hexdigest(),
            "data_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file()}}

def launch(root,case,mode,key):
    folder=root/case
    folder.mkdir()
    env=dict(os.environ,CAUSALOPS_HOME=str(folder/"workspace"))
    env.pop("DEEPSEEK_API_KEY",None)
    if mode=="deepseek":
        env["DEEPSEEK_API_KEY"]=key
    start=time.perf_counter()
    try:
        with (folder/"worker.log").open("xb") as log:
            res=subprocess.run([sys.executable,__file__,str(folder),mode,"--worker",case],
                               env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420)
        status="完成" if res.returncode==0 and (folder/"observation.json").exists() else "运行器失败"
    except subprocess.TimeoutExpired:
        status="超时"
    write(folder/"status.json",{"case":case,"mode":mode,"status":status,"wall_s":round(time.perf_counter()-start,3)})
    print(case,status,flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    parser.add_argument("mode",choices=["local","deepseek"])
    parser.add_argument("--worker",choices=REMAINING)
    args=parser.parse_args()
    if args.worker:
        if args.worker in PILOT:
            parser.error("第二期不重跑第一期题目")
        worker(args.folder,args.worker,args.mode)
    else:
        snapshot=validate_product()
        if args.folder.resolve().is_relative_to(REPO):
            parser.error("证据必须位于仓库外")
        if args.folder.exists():
            parser.error("不覆盖既有证据")
        key=(os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("Official key (hidden): ")) if args.mode=="deepseek" else ""
        args.folder.mkdir(parents=True)
        write(args.folder/"batch.json",{**snapshot,"tasks":REMAINING,"mode":args.mode,
              "max_workers":2,"timeout_per_task_s":420,"worker":"unchanged run_pilot.worker",
              "model":"deepseek-flash" if args.mode=="deepseek" else None})
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda case:launch(args.folder,case,args.mode,key),REMAINING))

