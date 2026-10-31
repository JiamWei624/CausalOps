"""Download three UCI validation tables; keep data outside the Git checkout."""
from pathlib import Path
import argparse,hashlib,io,json,urllib.request,zipfile
import pandas as pd
DATASETS=[('wine_quality','186','wine+quality','10.24432/C56S3T'),('bank_marketing','222','bank+marketing','10.24432/C5K306'),('online_shoppers','468','online+shoppers+purchasing+intention+dataset','10.24432/C5F88Q')]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.drive.lower()=='c:':raise SystemExit('请选择C盘以外的数据目录。')
 repository=Path(__file__).resolve().parents[1]
 if out==repository or out.is_relative_to(repository):raise SystemExit('数据目录应位于Git源码目录之外。')
 raw=out/'sources';prepared=out/'prepared';raw.mkdir(parents=True,exist_ok=True);prepared.mkdir(exist_ok=True);records=[]
 for name,num,slug,doi in DATASETS:
  source=f'https://archive.ics.uci.edu/dataset/{num}/{slug}';url=f'https://archive.ics.uci.edu/static/public/{num}/{slug.replace("+","%2B")}.zip';archive=raw/(name+'.zip')
  if not archive.exists():
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CausalOps-public-validation'}),timeout=60) as response:payload=response.read(16*1024*1024+1)
   if len(payload)>16*1024*1024:raise RuntimeError('Archive exceeds this downloader size bound')
   archive.write_bytes(payload)
  z=zipfile.ZipFile(archive);names=z.namelist()
  if name=='bank_marketing':
   nested=next(n for n in names if n.endswith('bank.zip'));inner=zipfile.ZipFile(io.BytesIO(z.read(nested)));member=next(n for n in inner.namelist() if n.endswith('bank-full.csv'));payload=inner.read(member);frame=pd.read_csv(io.BytesIO(payload),sep=';');frame['subscribed']=(frame['y']=='yes').astype(int);transform='Derived subscribed from y=yes; retained y; no row removal.'
  else:
   member=next(n for n in names if n.endswith('winequality-red.csv' if name=='wine_quality' else 'online_shoppers_intention.csv'));payload=z.read(member);frame=pd.read_csv(io.BytesIO(payload),sep=';' if name=='wine_quality' else ',');transform='Selected red-wine subset; no row removal.'
   if name=='online_shoppers':frame['Revenue']=frame.Revenue.astype(int);transform='Converted Revenue bool to integer; no row removal.'
  target=prepared/(name+'.parquet');frame.to_parquet(target,index=False)
  records.append({'id':name,'source':source,'download':url,'doi':doi,'license':'CC BY 4.0 (see source page)','archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'member':member,'csv_sha256':hashlib.sha256(payload).hexdigest(),'prepared_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'rows':len(frame),'columns':list(frame),'transformation':transform,'checksum_scope':'Local download identity, not a publisher signature.'})
 (out/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps([{'id':r['id'],'rows':r['rows']} for r in records]))
if __name__=='__main__':main()
