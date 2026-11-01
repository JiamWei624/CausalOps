"""Compatibility entry: all launches now use the main workbench."""
from pathlib import Path
import runpy
if __name__=='__main__':
    print('历史作品集启动入口已迁移至统一 CausalOps 工作台。')
    runpy.run_path(str(Path(__file__).with_name('start_workflow.py')),run_name='__main__')
