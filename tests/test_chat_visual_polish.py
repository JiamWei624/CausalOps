"""Visual presentation contracts; research evidence and bindings remain immutable."""
from streamlit.testing.v1 import AppTest
from test_configurable_research import co,config,data
from causalops.application.chat_sessions import ChatService
from pathlib import Path

APP=Path(__file__).parents[1]/'src/causalops/ui/workbench.py'

def app_for(co,monkeypatch,chat):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    app=AppTest.from_file(str(APP),default_timeout=30)
    app.query_params.update(route='home',chat=chat.id);app.run()
    assert not app.exception
    return app

def test_latest_message_is_native_control_not_page_anchor(co,monkeypatch):
    chats=ChatService(co.s);chat=chats.create()
    app=app_for(co,monkeypatch,chat)
    assert app.button(key='chat_latest_'+chat.id).label=='最新消息'
    assert not any('href="#chat-latest-' in m.value for m in app.markdown)
    app.button(key='chat_latest_'+chat.id).click().run()
    assert not app.exception and app.query_params['chat']==chat.id and len(app.chat_input)==1

def test_unbound_reply_is_labeled_as_its_original_context(co,monkeypatch):
    chats=ChatService(co.s);chat=chats.create();chats.submit(chat.id,'请说明当前研究范围',request_key='before-bind')
    t=co.create_configurable(data().to_csv(index=False).encode(),name='controlled.csv',configuration=config(),request_id='polish-context',human_confirmed=True)
    chats.bind(chat.id,'automation_v2',t['id']);original=chats.messages(chat.id)[0]['reference']
    app=app_for(co,monkeypatch,chat)
    assert any('发送时尚未关联研究' in x.value for x in app.caption)
    assert chats.messages(chat.id)[0]['reference']==original
    assert not any(x.label=='研究上下文' for x in app.expander)

def test_demo_filter_preserves_history_and_keeps_selected_chat_visible(co,monkeypatch):
    chats=ChatService(co.s);a=chats.create('实际研究');b=chats.create('隔离验收')
    monkeypatch.setenv('CAUSALOPS_DEMO_HIDDEN_CHATS',b.id)
    app=app_for(co,monkeypatch,a)
    assert 'chat_session_'+b.id not in [x.key for x in app.button]
    assert chats.session(b.id).title=='隔离验收'
    app.checkbox(key='chat_include_demo').check().run()
    assert 'chat_session_'+b.id in [x.key for x in app.button]
    app.query_params.update(chat=b.id);app.run()
    assert 'chat_session_'+b.id in [x.key for x in app.button]

def test_panel_hides_repeated_main_report_action_and_keeps_evidence_links(co,monkeypatch):
    chats=ChatService(co.s);chat=chats.create()
    t=co.create_configurable(data().to_csv(index=False).encode(),name='controlled.csv',configuration=config(),request_id='polish-panel',human_confirmed=True)
    co.approve(t['id'],expected_plan_sha=t['plan_sha'],human_confirmed=True);co.run(t['id']);chats.bind(chat.id,'automation_v2',t['id'])
    app=app_for(co,monkeypatch,chat)
    assert 'chat_result_link' in [x.key for x in app.button]
    app.button(key='chat_panel_toggle').click().run()
    keys=[x.key for x in app.button]
    assert 'chat_result_link' not in keys and 'chat_full_report' in keys
    assert 'chat_product_evidence' in keys and 'chat_product_decisions' in keys
