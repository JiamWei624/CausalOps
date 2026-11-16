"""Start the LangGraph build with existing local research history."""
from pathlib import Path
import os,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
os.environ.setdefault('CAUSALOPS_HOME',str(root/'artifacts/general-workspace'))
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
from causalops.workspace_launch import main
if __name__=='__main__':
    try:raise SystemExit(main(['--port','8513',*sys.argv[1:]],project_root=root))
    except (OSError,RuntimeError,ValueError) as exc:raise SystemExit('启动未完成：'+str(exc)) from None
