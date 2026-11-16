"""Developer-only reproducible UI build. End users install the prebuilt wheel."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tomllib
root=Path(__file__).resolve().parents[1];front=root/'frontend';dest=root/'src/causalops/web_assets'
if not shutil.which('npm'):raise SystemExit('源码构建需要Node.js与npm；发行包用户不需要Node。')
for args in [['npm','ci'],['npm','run','build']]:
    if sys.platform=='win32':args[0]='npm.cmd'
    subprocess.run(args,cwd=front,check=True)
# Only delete the explicitly resolved, dedicated generated UI directory.
resolved=dest.resolve();assert resolved.parent==(root/'src/causalops').resolve()and resolved.name=='web_assets'
if resolved.exists():shutil.rmtree(resolved)
shutil.copytree(front/'dist',resolved)
rows=[{'path':p.relative_to(resolved).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}for p in sorted(resolved.rglob('*'))if p.is_file()]
version=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf8'))['project']['version'];lock=hashlib.sha256((front/'package-lock.json').read_bytes()).hexdigest()
(resolved/'build-manifest.json').write_text(json.dumps({'version':version,'frontend_lock_sha256':lock,'files':rows},indent=2)+'\n',encoding='utf8',newline='\n')
print('Packaged React assets:',len(rows),version)
