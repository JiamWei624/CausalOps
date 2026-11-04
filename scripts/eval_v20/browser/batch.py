"""Launch isolated fixed or adaptive browser runs. A key is read once from hidden input."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
OUT=Path(os.environ.get('CAUSALOPS_V20_WORKSPACE',REPO/'artifacts'/'v20-pilot')).resolve()
PY=Path(sys.executable)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage",choices=["fixed","adaptive"],required=True)
    p.add_argument("--jobs",type=int,choices=[1,2,3],default=2)
    args=p.parse_args()
    if not (OUT/"frozen.json").is_file():raise SystemExit("初始库尚未冻结")
    if args.stage=="adaptive" and not (OUT/"fixed-browser-batch.json").is_file():
        raise SystemExit("先完成固定脚本批次")
    jobs=[(f"B{i:02d}",n) for n in range(1,(2 if args.stage=="fixed" else 4)) for i in range(1,7)]
    if any((OUT/"attempts"/args.stage/c/f"attempt-{n}").exists() for c,n in jobs):
        raise SystemExit("预定目录已存在；禁止重放或覆盖已开始的正式槽")
    key=os.environ.get("DEEPSEEK_API_KEY") or getpass("Official model credential (hidden): ")
    if not key:raise SystemExit("未提供模型凭据")
    env=dict(os.environ,DEEPSEEK_API_KEY=key,PYTHONPATH=str(REPO/"src"),PYTHONIOENCODING="utf-8",PYTHONDONTWRITEBYTECODE="1")
    clean={k:v for k,v in env.items() if k!="DEEPSEEK_API_KEY"}
    def execute(job):
        c,n=job
        folder=OUT/"attempts"/args.stage/c/f"attempt-{n}"
        prepared=subprocess.run([str(PY),str(HERE.parent/"controller/control.py"),"prepare","--case",c,
                                 "--mode",args.stage,"--attempt",str(n)],env=clean,cwd=REPO,capture_output=True)
        if prepared.returncode:
            return {"case":c,"attempt":n,"status":"prepare_error","exit":prepared.returncode}
        launch=folder/"launch.json"
        try:
            result=subprocess.run([str(PY),str(HERE/"drive.py"),str(launch),"--strategy",args.stage],
                                  env=env,cwd=REPO,capture_output=True,timeout=900)
            row=json.loads((folder/"interaction.json").read_text("utf-8"))
            status=row["status"]
        except (OSError,ValueError,subprocess.TimeoutExpired):
            status="worker_interrupted"
        print(c,n,status,flush=True)
        return {"case":c,"attempt":n,"status":status,"interaction":str(folder/"interaction.json")}
    def now():return datetime.now(timezone.utc).isoformat()
    files=[HERE/"drive.py",HERE/"observe.js",HERE/"batch.py",HERE.parent/"controller/control.py",HERE.parent/"controller/packets.py"]
    if args.stage=="adaptive":files.extend((HERE.parent/"actor/policy.py",HERE.parent/"actor/tasks.json"))
    meta={"stage":args.stage,"started":now(),"jobs":args.jobs,"files_sha256":{str(f.relative_to(REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},"planned":jobs}
    with (OUT/(args.stage+"-browser-start.json")).open("x",encoding="utf-8") as f:json.dump(meta,f,indent=2)
    with ThreadPoolExecutor(args.jobs) as pool:rows=list(pool.map(execute,jobs))
    with (OUT/(args.stage+"-browser-batch.json")).open("x",encoding="utf-8") as f:
        json.dump({**meta,"ended":now(),"results":rows},f,ensure_ascii=False,indent=2)

if __name__=="__main__":
    main()
