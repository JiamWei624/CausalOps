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

def use_local_mode():
    # Only affects future requests; no consent, key, plan or approval is rewritten.
    memory()['local_only']=True

def enable_model_mode():
    memory()['local_only']=False

def render_model_setup():
    cfg,key=current_connection();configured=bool(cfg and key)
    st.subheader('模型连接')
    if configured:
        verified=st.session_state.get('_connection_test')==(cfg.fingerprint,hashlib.sha256(key.encode()).hexdigest())
        st.caption(PRESETS[cfg.provider]['label']+' · '+cfg.model+' · '+('连接已验证' if verified else '已配置，尚未验证连接'))
    else:st.caption('模型连接为可选配置；数据任务的发送许可需单独确认。')
    if memory().get('local_only'):st.info('当前使用本地模式。连接配置和已保存任务仍保留，后续请求不调用外部模型。')
    with st.expander('连接配置',expanded=bool(st.session_state.get('_connection_open'))):
        _render_connection_editor()
    if st.session_state.get('_connection_probe_failed'):
        st.warning('模型连接测试未完成；没有发送研究数据。连接配置与已有任务仍保留。可修改配置后重新测试，也可继续本地分析。')
    left,right=st.columns(2)
    if memory().get('local_only'):
        left.button('恢复模型辅助',key='connection_enable_model',on_click=enable_model_mode,disabled=not configured)
    else:left.button('使用本地模式继续',key='connection_use_local',on_click=use_local_mode)
    def begin_import():st.session_state['showcase_route']='assistant';st.query_params['route']='assistant'
    right.button('前往数据导入与已有任务',key='connection_to_data',on_click=begin_import)
    st.caption('模式切换只影响后续请求；已启动任务应通过停止按钮单独处理。新的分析仍须审核，原模型流程不会被静默改为本地执行。')

def _render_connection_editor():
    m=memory()
    st.write('配置模型服务与访问凭据。未配置模型时，可使用本地统计分析。')
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
    if st.button('保存连接配置',key='connection_save'):
        st.session_state['_credential_memory_'+sk]=st.session_state[wk]
        if cfg:st.success('连接配置已保存于本次会话内存。')
        else:st.warning('请先完善服务地址和模型名称。')
    if st.button('测试模型连接',disabled=not(cfg and credential),key='connection_probe'):
        try:
            client=StructuredModelClient(cfg,credential)
            try:
                with st.spinner('正在核验认证、接口与结构化输出'):result=client.probe()
            finally:client.close()
            st.session_state['_connection_probe_failed']=False
            st.session_state['_connection_test']=(cfg.fingerprint,hashlib.sha256(credential.encode()).hexdigest())
            st.success('连接测试通过。可继续上传数据。')
        except (ValueError,RuntimeError):
            st.session_state.pop('_connection_test',None)
            st.session_state['_connection_probe_failed']=True
            st.error('连接未通过。请核对服务地址、模型名称、密钥和账户额度；没有发送研究数据。')
    st.caption('密钥只保存在当前浏览器连接的服务端内存中，刷新重连或关闭服务后可能需重填。不会写入数据库、报告或代码。连接测试只发送固定测试内容。')

def task_model(a,sid):
    cfg,key=current_connection();local=bool(memory().get('local_only'));authorized=bool(not local and cfg and key and a.consent_enabled(sid,cfg))
    if local:st.caption('运行模式：本地统计分析；当前任务的模型许可仍保留，但后续请求不发送给模型。')
    else:st.caption('模型：'+PRESETS[cfg.provider]['label']+' / '+cfg.model+' · '+('本任务已授权' if authorized else '本任务尚未授权') if cfg and key else '运行模式：本地统计分析')
    def open_settings():
        st.session_state['showcase_route']='home';st.query_params['route']='home'
    with st.expander('模型连接与数据发送许可',expanded=bool(cfg and key and not authorized)):
        st.button('管理模型连接',key='task_model_settings',on_click=open_settings)
        if cfg and key:
            ck='task_send_'+sid+'_'+cfg.fingerprint
            if ck not in st.session_state:st.session_state[ck]=a.consent_enabled(sid,cfg)
            def consent():a.consent(sid,st.session_state[ck],cfg)
            enabled=st.checkbox('允许本任务向以上模型发送字段摘要、研究问题及运行汇总',key=ck,on_change=consent)
            st.caption('不发送原始数据行、用户或帖子 ID 值、完整论文。更换服务、模型或协议后需重新授权。')
            if st.button('查看本任务的发送内容示例',key='task_payload'):st.json({'target':cfg.binding(),'payload':a.external_payload(sid,'请根据字段摘要推荐可回答的问题')})
        else:st.caption('配置模型后可获取模型辅助建议；本地统计分析不受影响。')
    if authorized:
        old=st.session_state.get('_assistant_provider_client')
        if old and (old.provider_config!=cfg or old._api_key!=key):old.close();old=None
        if old is None:old=StructuredModelClient(cfg,key);st.session_state['_assistant_provider_client']=old
        return old
    return None
