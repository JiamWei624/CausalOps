"""Nonblocking OS lease, released even when the owning process exits."""
from contextlib import contextmanager
from pathlib import Path
import os
from causalops.general.service import DesignError

@contextmanager
def flow_lock(root: Path, flow_id: str):
    directory=root/'workflow-locks';directory.mkdir(exist_ok=True)
    with (directory/(flow_id+'.lock')).open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise DesignError('该流程正在处理，请等待；不会并行重复执行。') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
