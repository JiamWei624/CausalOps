"""Download primary source snapshots locally; never execute remote code or redistribute article text."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from datetime import datetime,timezone
import hashlib,json,argparse
from causalops.knowledge.retrieval import MethodLibrary

def main(out):
    out.mkdir(parents=True,exist_ok=True);sources=MethodLibrary().catalog['sources']
    def fetch(item):
        sid,s=item
        try:
            req=Request(s['url'],headers={'User-Agent':'CausalOps-source-audit/0.4.0'})
            with urlopen(req,timeout=25) as response:
                data=response.read(8*1024*1024+1);final=response.url;mime=response.headers.get('content-type','')
            if len(data)>8*1024*1024:raise ValueError('source_exceeds_snapshot_limit')
            suffix='.pdf' if data.startswith(b'%PDF') else '.html';path=out/(sid+suffix);path.write_bytes(data)
            return dict(source_id=sid,url=s['url'],final_url=final,mime=mime,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),status='downloaded_for_local_audit_only',at=datetime.now(timezone.utc).isoformat())
        except Exception as e:return dict(source_id=sid,url=s['url'],status='download_failed_web_review_not_fulltext',exception_type=type(e).__name__)
    with ThreadPoolExecutor(max_workers=5) as pool:records=list(pool.map(fetch,sources.items()))
    (out/'source-snapshot-manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'downloaded':sum(x['status']=='downloaded_for_local_audit_only' for x in records),'total':len(records),'failed':[x['source_id'] for x in records if x['status'].startswith('download_failed')]}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.out)
