"""UI state checks complement real browser acceptance."""
from streamlit.testing.v1 import AppTest
from test_configurable_research import co
from causalops.application.chat_sessions import ChatService
from pathlib import Path

APP=Path(__file__).parents[1]/'src/causalops/ui/workbench.py'

def test_empty_workspace_chat_and_restored_identity(co,monkeypatch):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    c=ChatService(co.s).create()
    app=AppTest.from_file(str(APP),default_timeout=25)
    app.query_params.update(route='home',chat=c.id);app.run()
    assert not app.exception
    assert len(app.chat_input)==1
    assert not any('统计结果'==x.value for x in app.metric)
    assert '展开研究面板' in [b.label for b in app.button]
    assert app.query_params['chat']==c.id

def test_unknown_chat_does_not_fallback_to_previous_success(co,monkeypatch):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    ChatService(co.s).create()
    app=AppTest.from_file(str(APP),default_timeout=25)
    app.query_params.update(route='home',chat='a'*32);app.run()
    assert not app.exception and app.error
    assert not app.chat_input
    assert not app.info  # Rejected identities must not retain a loading message.

def test_native_chat_switch_drops_previous_transcript(co,monkeypatch):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    service=ChatService(co.s);a=service.create('研究甲会话');b=service.create('研究乙会话')
    service.submit(a.id,'只属于研究甲的提问',request_key='a')
    service.submit(b.id,'只属于研究乙的提问',request_key='b')
    app=AppTest.from_file(str(APP),default_timeout=25)
    app.query_params.update(route='home',chat=a.id);app.run()
    assert not app.exception
    app.button(key='chat_session_'+b.id).click().run()
    assert not app.exception and app.query_params['chat']==b.id
    text=' '.join(m.value for m in app.markdown)
    assert '只属于研究乙的提问' in text and '只属于研究甲的提问' not in text


def test_registered_chat_data_enters_actual_contract_editor_and_returns_same_chat(co,monkeypatch):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    service=ChatService(co.s);chat=service.create()
    service.import_data(chat.id,b'arm,completed\na,0\nb,1\n',name='table.csv',request_key='data')
    app=AppTest.from_file(str(APP),default_timeout=25)
    app.query_params.update(route='home',chat=chat.id);app.run()
    app.button(key='chat_start_config').click().run()
    assert not app.exception and app.query_params['route']=='configure'
    assert app.query_params['chat']==chat.id and app.query_params['chat_flow']
    assert any(x.label=='研究目标' for x in app.text_input)
    assert not app.get('file_uploader')  # Registered input is re-used, not selected again.
    assert not any(x.value for x in app.checkbox)
    app.button(key='back_to_chat').click().run()
    assert not app.exception and app.query_params['chat']==chat.id
    assert app.query_params['route']=='home' and app.chat_input
