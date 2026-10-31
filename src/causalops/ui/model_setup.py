"""Homepage connection settings. Non-widget memory survives Streamlit widget cleanup."""
from __future__ import annotations
import hashlib
import streamlit as st
from causalops.llm.providers import PRESETS,ProviderConfig,StructuredModelClient

def memory():
    return st.session_state.setdefault('_connection_memory',{'provider':'deepseek','profiles':{},'keys':{}})

def scope(provider,base):
    return hashlib.sha256((provider+'|'+base.rstrip('/')).encode()).hexdigest()[:16]

def current_connection():
    m=memory();p=m['provider'];values={**PRESETS[p],**m['profiles'].get(p,{})}
    try:
        cfg=ProviderConfig(**{k:values[k] for k in ProviderConfig.model_fields if k in values},provider=p)
    except ValueError:return None,''
    return cfg,st.session_state.get('_credential_memory_'+scope(p,cfg.base_url),m['keys'].get(scope(p,cfg.base_url),''))

def render_model_setup():
    m=memory()
    st.subheader('1. 连接分析助手')
    st.write('选择模型服务，填写该服务的 API 密钥。也可以先用本地模式体验基础分析。')
    key='_connect_provider'
    if key not in st.session_state:st.session_state[key]=m['provider']
    def choose():memory()['provider']=st.session_state[key]
    p=st.selectbox('模型服务商',list(PRESETS),format_func=lambda x:PRESETS[x]['label'],key=key,on_change=choose)
    m['provider']=p;defaults=PRESETS[p];saved=m['profiles'].setdefault(p,{})
    def text(label,field,default,**kw):
        k='_connect_'+p+'_'+field
        if k not in st.session_state:st.session_state[k]=saved.get(field,default)
        def persist():memory()['profiles'].setdefault(p,{})[field]=st.session_state[k]
        v=st.text_input(label,key=k,on_change=persist,**kw);saved[field]=v;return v
    name=text('模型名称（API 模型 ID）','model',defaults['model'],placeholder='填写服务账户中可调用的模型 ID')
    with st.expander('服务地址与高级连接设置',expanded=p=='custom'):
        base=text('API 服务基础地址','base_url',defaults['base_url'])
        modes=['anthropic_messages'] if p=='anthropic' else ['responses','chat_completions']
        mk='_connect_'+p+'_api_mode'
        if mk not in st.session_state:st.session_state[mk]=saved.get('api_mode',defaults['api_mode'])
        def mode_change():memory()['profiles'].setdefault(p,{})['api_mode']=st.session_state[mk]
        saved['api_mode']=st.selectbox('接口协议',modes,format_func=lambda x:{'responses':'Responses API','chat_completions':'Chat Completions','anthropic_messages':'Anthropic Messages'}[x],key=mk,on_change=mode_change)
        fs=['prompt_json'] if p=='anthropic' else ['json_object','json_schema','prompt_json'];fk='_connect_'+p+'_json_mode'
        if fk not in st.session_state:st.session_state[fk]=saved.get('json_mode',defaults['json_mode'])
        def fmt_change():memory()['profiles'].setdefault(p,{})['json_mode']=st.session_state[fk]
        saved['json_mode']=st.selectbox('结构化输出',fs,key=fk,on_change=fmt_change)
        if p=='anthropic':text('API 版本','anthropic_version','2026-10-21')
    sk=scope(p,base);wk='_connect_key_'+sk
    if wk not in st.session_state:st.session_state[wk]=st.session_state.get('_credential_memory_'+sk,m['keys'].get(sk,''))
    def keep_key():st.session_state['_credential_memory_'+sk]=st.session_state[wk]
    visible=st.checkbox('显示密钥',key='_connect_visible')
    credential=st.text_input('API 密钥',type='default' if visible else 'password',key=wk,on_change=keep_key,help='输入后按回车，或点击下方保存连接设置。')
    st.session_state['_credential_memory_'+sk]=credential
    cfg,_=current_connection()
    if name and not cfg:st.warning('连接配置不完整或地址与服务商不匹配，请核对高级设置。')
    if defaults['docs']:st.link_button('服务商官方接入文档',defaults['docs'])
    if st.button('保存连接设置（仅本次会话）',key='connection_save'):
        st.session_state['_credential_memory_'+sk]=st.session_state[wk]
        if cfg:st.success('连接设置已保存在内存中。可测试连接，或继续上传数据。')
        else:st.warning('请先完善服务地址和模型名称。')
    if st.button('测试模型连接',disabled=not(cfg and credential),key='connection_probe'):
        try:
            client=StructuredModelClient(cfg,credential)
            try:
                with st.spinner('正在核验认证、接口与结构化输出'):result=client.probe()
            finally:client.close()
            st.session_state['_connection_test']=(cfg.fingerprint,hashlib.sha256(credential.encode()).hexdigest())
            st.success('连接测试通过。可继续上传数据。')
        except (ValueError,RuntimeError):st.error('连接未通过。请核对服务地址、模型名称、密钥和账户额度；没有发送研究数据。')
    st.caption('密钥只保存在当前浏览器连接的服务端内存中，刷新重连或关闭服务后可能需重填。不会写入数据库、报告或代码。连接测试只发送固定测试内容。')

def task_model(a,sid):
    cfg,key=current_connection();model=None
    with st.container(border=True):
        st.markdown('**模型连接与本任务授权**')
        st.write((PRESETS[cfg.provider]['label']+' · '+cfg.model) if cfg and key else '本地模式：基础报告与统计工具可用。需要智能推荐时，请先到首页连接模型。')
        def open_settings():
            st.session_state['showcase_route']='home';st.query_params['route']='home'
        st.button('到首页设置或更换模型',key='task_model_settings',on_click=open_settings)
        if cfg and key:
            ck='task_send_'+sid+'_'+cfg.fingerprint
            if ck not in st.session_state:st.session_state[ck]=a.consent_enabled(sid,cfg)
            def consent():a.consent(sid,st.session_state[ck],cfg)
            enabled=st.checkbox('允许本任务向以上模型发送字段摘要、研究问题及运行汇总',key=ck,on_change=consent)
            st.caption('不发送原始数据行、用户或帖子 ID 值、完整论文。更换服务、模型或协议后需重新授权。')
            if st.button('查看本任务的发送内容示例',key='task_payload'):
                st.json({'target':cfg.binding(),'payload':a.external_payload(sid,'请根据字段摘要推荐可回答的问题')})
            if enabled and a.consent_enabled(sid,cfg):
                old=st.session_state.get('_assistant_provider_client')
                if old and (old.provider_config!=cfg or old._api_key!=key):old.close();old=None
                if old is None:old=StructuredModelClient(cfg,key);st.session_state['_assistant_provider_client']=old
                model=old
    return model
