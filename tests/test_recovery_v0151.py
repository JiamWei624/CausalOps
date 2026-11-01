import hashlib
import pytest
from streamlit.testing.v1 import AppTest
from causalops.ui import model_setup

SETUP="""
import streamlit as st
from causalops.ui import model_setup as m
if '_connection_memory' not in st.session_state:
 st.session_state['_connection_memory']={'provider':'deepseek','profiles':{},'keys':{}}
 st.session_state['_credential_memory_'+m.scope('deepseek','https://api.deepseek.com')]='demo'
m.render_model_setup()
st.write('LOCAL='+str(m.memory().get('local_only',False)))
st.write('KEY='+str(bool(m.current_connection()[1])))
"""

def test_failed_probe_removes_stale_success_and_exposes_safe_local_action(monkeypatch):
 class Failed:
  def __init__(self,*a,**k):pass
  def probe(self):raise RuntimeError('do-not-show-raw-provider-response')
  def close(self):pass
 monkeypatch.setattr(model_setup,'StructuredModelClient',Failed)
 at=AppTest.from_string(SETUP).run()
 cfg=model_setup.ProviderConfig();at.session_state['_connection_test']=(cfg.fingerprint,hashlib.sha256(b'demo').hexdigest())
 at.button(key='connection_probe').click().run()
 assert not at.exception and at.session_state['_connection_probe_failed'] is True
 assert '_connection_test' not in at.session_state and at.button(key='connection_use_local')
 assert 'do-not-show' not in ' '.join(x.value for x in at.error)


def test_local_mode_preserves_credentials_and_requires_explicit_restore():
 at=AppTest.from_string(SETUP).run();at.button(key='connection_use_local').click().run()
 assert at.session_state['_connection_memory']['local_only'] is True and any(x.value=='KEY=True' for x in at.markdown)
 assert at.button(key='connection_enable_model') and not at.exception
 at.button(key='connection_enable_model').click().run()
 assert at.session_state['_connection_memory']['local_only'] is False


def test_local_task_does_not_construct_model_or_rewrite_consent(monkeypatch):
 class Forbidden:
  def __init__(self,*a,**k):raise AssertionError('No network client in explicit local mode')
 monkeypatch.setattr(model_setup,'StructuredModelClient',Forbidden)
 script=SETUP.replace('m.render_model_setup()',"""
m.use_local_mode()
class A:
 def consent_enabled(self,*args):return True
 def consent(self,*args):raise AssertionError('Consent cannot be changed by local-mode selection')
a=A()
result=m.task_model(a,'test-task')
st.write('MODEL_NONE='+str(result is None))
""")
 at=AppTest.from_string(script).run()
 assert not at.exception and any(x.value=='MODEL_NONE=True' for x in at.markdown)

RECOVERY="""
import streamlit as st
from types import SimpleNamespace
from causalops.ui.recovery import render_recovery
class J:
 def submit_start(self,*args,**kwargs):
  st.session_state['submitted']={'args':args,'kwargs':kwargs}
  return {'flow_id':'new-draft'}
s=SimpleNamespace(a=SimpleNamespace(completed_runs=lambda sid:[{'run_id':'one'}]))
f={'id':'old-failed','status':'failed','request':{'question':'Please describe the quality distribution'}}
render_recovery(s,J(),'task',f,False)
"""

def test_recovery_opens_context_without_submitting_or_changing_records():
 at=AppTest.from_string(RECOVERY).run();at.button(key='recover_task_old-failed_context').click().run()
 assert at.session_state['_open_contract_task'] is True and 'submitted' not in at.session_state and not at.exception


def test_recovery_replans_instead_of_resuming_or_approving_old_flow():
 at=AppTest.from_string(RECOVERY).run();at.button(key='recover_task_old-failed_plan').click().run()
 v=at.session_state['submitted'];assert v['kwargs']=={'mode':'plan','parent_flow_id':'old-failed'}
 assert at.session_state['_graph_pending_task']=='new-draft' and not at.exception


def test_manual_resource_is_standalone_and_contains_real_scope():
 from importlib.resources import files
 import re
 value=files('causalops.help').joinpath('manual.html').read_text(encoding='utf-8')
 assert len(re.findall(r'<section id="chapter-',value))==25
 assert 'data:image/png;base64,' in value and 'data:image/svg+xml;base64,' in value
 assert '独立用户验收' in value and '尚未' in value and '本地单用户' in value
 assert 'window.print()' in value and 'id="toc-search"' in value
