"""Download exact public test tables; no silent source changes or execution."""
from pathlib import Path
import argparse,json,urllib.request,hashlib
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
rows=json.loads((Path(__file__).parent/'public-data-manifest.json').read_text(encoding='utf-8'))
for r in rows:
 with urllib.request.urlopen(r['url'],timeout=60) as response:data=response.read()
 if hashlib.sha256(data).hexdigest()!=r['sha256']:raise SystemExit('Downloaded source hash mismatch; no file saved')
 path=a.output/r['file'];path.write_bytes(data);print(r['file'],len(data),'bytes; SHA256 verified')
