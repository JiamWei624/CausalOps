"""Smoke the frozen mixed-intent product route. This is not a simulated user task."""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

import pandas as pd
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
from causalops.evaluation.v13.capture import Metered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    folder = parser.parse_args().output
    folder.mkdir(parents=True, exist_ok=False)
    model = Metered(os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('Official key (hidden): '), folder)
    assistant = AssistantWorkspace(GeneralWorkspace(folder/'workspace'))
    service = ResearchService(assistant, model=model)
    frame = pd.DataFrame({'quality': [5, 6, 7, 6]*10, 'acidity': [4., 5., 6., 5.]*10})
    sid = service.create_task(payload=frame.to_csv(index=False).encode(), name='synthetic.csv', title='混合研究请求冒烟')
    assistant.consent(sid, True, model.provider_config)
    question = '先看分布，再使用OLS分析quality与acidity的关联'
    flow = service.begin(sid, question)
    started = time.perf_counter()
    result = dict(question=question, session=sid, flow=flow['id'], frozen='5f257e8')
    try:
        route = service.decide_route(flow['id'])
        result.update(route=route.model_dump(), passed=route.route=='plan' and 'ols' in route.methods)
    except Exception as exc:
        result.update(error=type(exc).__name__, passed=False)
    result.update(seconds=time.perf_counter()-started, calls=model.index, runs=len(assistant.completed_runs(sid)))
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['passed'], result['calls'])


if __name__=='__main__':
    main()
