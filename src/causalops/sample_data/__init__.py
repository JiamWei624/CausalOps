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
