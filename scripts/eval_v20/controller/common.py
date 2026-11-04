"""Allow writes only beneath the dedicated V2 pilot workspace."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(os.environ.get('CAUSALOPS_V20_WORKSPACE', Path(__file__).resolve().parents[3]/'artifacts'/'v20-pilot')).resolve()
CASES=tuple('B%02d'%i for i in range(1,7))

def bounded(path):
    p=Path(path).resolve()
    if not p.is_relative_to(ROOT) or p==ROOT:raise ValueError('请使用专用评测子目录。')
    return p

def load(path):
    return Path(path).read_text(encoding='utf-8-sig')

def read(path):
    return json.loads(load(path))

def save(path,obj):
    p=bounded(path)
    with p.open('x',encoding='utf8') as writer:
        json.dump(obj,writer,ensure_ascii=False,indent=2,allow_nan=False,default=str)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def inventory(path):
    files={}
    for p in sorted(path.rglob('*')):
        if not p.is_file():continue
        if p.name.endswith(('-wal','-shm')):
            wal=p if p.name.endswith('-wal') else p.with_name(p.name[:-4]+'-wal')
            if wal.exists() and wal.stat().st_size:raise ValueError('尚有未归并事务的 WAL 内容，请先关闭工作区')
            continue
        files[p.relative_to(path).as_posix()]=sha(p)
    return files
