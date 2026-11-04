"""Build a batch index from saved task evidence; never rerun an analysis."""
import json


def event_index(root, cases):
    destination=root/'events.jsonl'
    with destination.open('w',encoding='utf8') as target:
        for case in cases:
            folder=root/case/'attempt-1'
            snapshot=folder/'observations.json'
            observations=json.loads(snapshot.read_text('utf8')) if snapshot.is_file() else {}
            flows={f['id']:f for f in observations.get('flows',[])}
            for line in (folder/'events.jsonl').read_text('utf8').splitlines():
                event=json.loads(line)
                if event['事件']=='结果解释生成完成' and not event['运行']:
                    flow=flows.get(event['流程'],{})
                    event['运行']=flow.get('answer',{}).get('run_ids') or None
                target.write(json.dumps(event,ensure_ascii=False)+'\n')
    return destination
