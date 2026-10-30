from pathlib import Path
import os,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
os.environ.setdefault('CAUSALOPS_HOME',str(root/'artifacts/general-workspace'))
from causalops.launch import main
if __name__=='__main__':
    try:raise SystemExit(main(["--port","8510",*sys.argv[1:]],project_root=root))
    except (OSError,RuntimeError) as e:raise SystemExit('启动未完成：'+str(e)) from None
