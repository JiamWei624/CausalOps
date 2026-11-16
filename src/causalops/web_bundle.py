"""Verify the built, packaged UI; never fall back to an unrelated working directory."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

def workspace_identity(home):
    return hashlib.sha256(os.path.normcase(str(Path(home).resolve())).encode('utf8')).hexdigest()

def packaged_root():
    return Path(__file__).resolve().parent/'web_assets'

def verify_bundle(root=None):
    from causalops import __version__
    root=Path(root or packaged_root()).resolve()
    try:
        raw=(root/'build-manifest.json').read_bytes();m=json.loads(raw)
        if m['version']!=__version__ or not isinstance(m['files'],list) or not m['files']:raise ValueError('version')
        names=set()
        for row in m['files']:
            name=row['path'];p=(root/name).resolve()
            if not isinstance(name,str) or name in names or not p.is_relative_to(root) or name.startswith(('/', '\\')) or '..' in Path(name).parts or ':' in name:raise ValueError('path')
            names.add(name)
            if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('hash')
        actual={p.relative_to(root).as_posix()for p in root.rglob('*')if p.is_file() and p.name!='build-manifest.json'}
        if names!=actual or 'index.html' not in names or not any(n.endswith('.js')and n.startswith('assets/')for n in names):raise ValueError('incomplete')
        return dict(version=m['version'],sha=hashlib.sha256(raw).hexdigest(),files=len(names),root=root)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise RuntimeError('React静态资源缺失、版本不一致或校验失败。请重新安装完整发行包；源码开发请执行python scripts/build_frontend.py。') from exc
