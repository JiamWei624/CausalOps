import hashlib,json
from pathlib import Path
import pytest
from causalops import web_bundle as bundle
from causalops import workspace_launch as launch

def assets(tmp_path):
 root=tmp_path/'assets-package';(root/'assets').mkdir(parents=True)
 for name,text in [('index.html','<html>release</html>'),('assets/main.js','console.log(1)'),('assets/main.css','body{}')]:
  (root/name).write_text(text,encoding='utf8')
 rows=[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in root.rglob('*')if p.is_file()]
 (root/'build-manifest.json').write_text(json.dumps({'version':'0.21.0b1','files':rows}),encoding='utf8');return root

def test_missing_or_changed_bundle_fails_closed(tmp_path):
 with pytest.raises(RuntimeError):bundle.verify_bundle(tmp_path)
 root=assets(tmp_path);assert bundle.verify_bundle(root)['version']=='0.21.0b1'
 (root/'assets/main.js').write_text('changed')
 with pytest.raises(RuntimeError):bundle.verify_bundle(root)

def test_manifest_cannot_escape_package(tmp_path):
 root=assets(tmp_path);p=root/'build-manifest.json';m=json.loads(p.read_text());m['files'][0]['path']='../outside';p.write_text(json.dumps(m))
 with pytest.raises(RuntimeError):bundle.verify_bundle(root)

def test_shared_home_and_no_external_model_keys(tmp_path):
 env=launch.child_environment(tmp_path,{'DEEPSEEK_API_KEY':'not-real-test-value','LANGSMITH_API_KEY':'not-real-test-value'})
 assert env['CAUSALOPS_HOME']==str(tmp_path.resolve())
 assert not env.get('DEEPSEEK_API_KEY') and not env.get('LANGSMITH_API_KEY')
 assert env['LANGSMITH_TRACING']=='false' and env['LANGCHAIN_TRACING_V2']=='false'
 assert Path(env['TEMP']).is_relative_to(tmp_path)

def test_ports_are_distinct_and_home_is_explicit(tmp_path):
 c=launch.configuration(['--workspace',str(tmp_path),'--port','8840','--streamlit-port','8841','--no-browser'])
 assert c.workspace==tmp_path.resolve() and (c.port,c.streamlit_port)==(8840,8841)
 with pytest.raises(SystemExit):launch.configuration(['--port','8840','--streamlit-port','8840'])

def test_health_identity_requires_entire_pair(tmp_path):
 data={'instance':'a','workspace':bundle.workspace_identity(tmp_path),'version':'0.21.0b1','frontend_sha':'b','ready':True}
 assert launch.match_health(data,instance='a',home=tmp_path,version='0.21.0b1',frontend_sha='b')
 for key in ('instance','workspace','version','frontend_sha','ready'):
  changed={**data,key:'other'}
  assert not launch.match_health(changed,instance='a',home=tmp_path,version='0.21.0b1',frontend_sha='b')

def test_health_api_does_not_grant_authority(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from causalops.react_api import create_app
 from causalops.application.research_service import ResearchService
 from causalops.assistant.service import AssistantWorkspace
 from causalops.general.service import GeneralWorkspace
 monkeypatch.setenv('CAUSALOPS_LAUNCH_INSTANCE','release-test')
 s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/'workspace')))
 with TestClient(create_app(s,static_dir=assets(tmp_path)),base_url='http://127.0.0.1:8790') as c:
  x=c.get('/api/health');assert x.status_code==200 and x.json()['instance']=='release-test'
  assert 'csrf_token' not in x.json() and 'api_key' not in x.text.lower()
  assert c.post('/api/chats',json={'title':'cannot write','request_key':'no-authority'}).status_code==401
  c.get('/api/bootstrap')
  assert c.post('/api/chats',json={'title':'cannot write','request_key':'no-authority'}).status_code==403
