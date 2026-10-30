"""Install the hash-locked offline release into a chosen data-drive environment."""
from pathlib import Path
import argparse,os,subprocess,sys,json,hashlib

def main():
    p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parent;dest=a.destination.expanduser().resolve()
    if sys.version_info[:2]!=(3,11):raise SystemExit('Use Python 3.11 on Windows x64 for this verified release.')
    if not (root/'wheelhouse').is_dir():raise SystemExit('This source-only download has no wheels. Use the full offline release or install source dependencies online.')
    if dest.exists():raise SystemExit('Destination already exists. Choose a new environment path; no files were removed.')
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
    short=Path(dest.anchor)/'causalops-install-temp';cache=Path(dest.anchor)/'causalops-install-cache'
    for key,path in {'TEMP':short,'TMP':short,'PIP_CACHE_DIR':cache}.items():path.mkdir(exist_ok=True);env[key]=str(path)
    subprocess.run([sys.executable,'-m','venv',str(dest)],env=env,check=True)
    python=dest/'Scripts/python.exe';lock=root/'requirements-win-py311-offline.lock'
    subprocess.run([str(python),'-m','pip','install','--no-index','--find-links',str(root/'wheelhouse'),'--require-hashes','--no-deps','-r',str(lock)],env=env,check=True)
    record=json.loads((root/'application-wheel.json').read_text(encoding='utf-8'));app=root/'wheelhouse'/record['wheel']
    if not app.is_file() or hashlib.sha256(app.read_bytes()).hexdigest()!=record['sha256']:raise SystemExit('Application wheel hash mismatch; installation stopped.')
    subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(app)],env=env,check=True)
    subprocess.run([str(python),'-m','pip','check'],env=env,check=True)
    print('Installed. Start with: '+str(python)+' -m causalops.launch --workspace <data-drive-workspace> --port 8510')
if __name__=='__main__':main()
