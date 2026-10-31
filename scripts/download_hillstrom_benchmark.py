"""Prepare the preregistered Hillstrom two-arm table; never redistribute source rows."""
from pathlib import Path
import argparse,urllib.request,hashlib,gzip,io,json
import pandas as pd,duckdb
URL='https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz'
UPSTREAM='https://github.com/maks-sh/scikit-uplift/blob/master/sklift/datasets/datasets.py'
MD5='a68a81291f53a14f4e29002629803ba3'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.expanduser().resolve();repo=Path(__file__).resolve().parents[1]
 if out.drive.lower()=='c:' or out==repo or out.is_relative_to(repo):raise SystemExit('Choose a data-drive directory outside the source checkout.')
 raw=out/'sources';prepared=out/'prepared';raw.mkdir(parents=True,exist_ok=True);prepared.mkdir(exist_ok=True);archive=raw/'hillstrom.csv.gz'
 if archive.exists():payload=archive.read_bytes()
 else:
  with urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'CausalOps-validation'}),timeout=60) as response:payload=response.read(5*1024*1024+1)
 if len(payload)>5*1024*1024 or hashlib.md5(payload).hexdigest()!=MD5:raise SystemExit('Upstream loader MD5/size check failed; source not adopted.')
 with gzip.GzipFile(fileobj=io.BytesIO(payload)) as g:csv=g.read(8*1024*1024+1)
 if len(csv)>8*1024*1024:raise SystemExit('Expanded source exceeds bound.')
 frame=pd.read_csv(io.BytesIO(csv));assert frame.shape==(64000,12)
 with duckdb.connect() as db:
  db.register('hillstrom_raw',frame);arm='Mens E-Mail';part=db.execute("SELECT *,CASE WHEN segment=? THEN 1 ELSE 0 END AS assigned FROM hillstrom_raw WHERE segment IN (?, 'No E-Mail')",[arm,arm]).df().reset_index(drop=True)
 part['entity_id']=['local_'+str(i) for i in range(len(part))];assert len(part)==42613
 target=prepared/'hillstrom_men_visit.parquet';buffer=io.BytesIO();part.to_parquet(buffer,index=False);data=buffer.getvalue()
 if target.exists() and target.read_bytes()!=data:raise SystemExit('A different prepared file exists; choose a new output instead of overwriting it.')
 archive.write_bytes(payload);target.write_bytes(data)
 record={'source':URL,'upstream_loader':UPSTREAM,'original_documentation':'https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html','loader_md5_verified':True,'archive_sha256':hashlib.sha256(payload).hexdigest(),'prepared_sha256':hashlib.sha256(data).hexdigest(),'rows':len(part),'transformation':'Predefined Mens E-Mail vs No E-Mail; assigned=1 for Mens; local sequential entity labels; no outcome-based filtering.','license_boundary':'No explicit original data redistribution license verified. Downloader only; data must not enter Git.'}
 (out/'hillstrom-manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(json.dumps(record))
if __name__=='__main__':main()