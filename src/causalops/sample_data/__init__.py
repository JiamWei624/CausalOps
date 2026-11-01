"""Attributable public examples; no private research data."""
from importlib.resources import files
import hashlib,json

def wine_example():
    folder=files(__package__)
    info=json.loads(folder.joinpath('wine-quality.json').read_text(encoding='utf-8'))
    payload=folder.joinpath(info['filename']).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=info['sha256']:
        raise ValueError('公共示例校验失败；请重新安装同一发行包，不要修改样本文件。')
    return payload,info

def create_wine_task(workspace):
    from causalops.application.research_service import ResearchService
    data,info=wine_example()
    return ResearchService(workspace).create_task(payload=data,name=info['filename'],title=info['title'],encoding='utf-8-sig',separator=info['separator'])


from functools import lru_cache
@lru_cache(maxsize=1)
def _wine_identity():
    import io,pandas as pd
    from causalops.execution import _data_fingerprint
    payload,info=wine_example()
    return _data_fingerprint(pd.read_csv(io.BytesIO(payload),sep=info['separator']))

def example_context(workspace,sid):
    # Content identity, never a filename or a user-provided claim of provenance.
    from causalops.application.research_service import ResearchService
    binding=ResearchService(workspace).data_binding(sid)
    if binding['frame_sha']!=_wine_identity():return None
    import copy
    _,info=wine_example()
    return copy.deepcopy(info)
