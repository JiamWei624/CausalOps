"""Explicit configuration UI. Preview, declaration, approval and execution stay separate."""
from __future__ import annotations
import hashlib
import uuid
import streamlit as st
from causalops.general.service import DesignError
from causalops.application.configurable_research import BinaryResearchConfig,SCHEMA


def editor(co,*,previous=None):
    prior=previous['plan']['configuration'] if previous else {}
    st.subheader('使用自己的数据开展研究' if not previous else '创建修订候选 · 重新审核')
    st.caption('受限单表、恰好两个组、一个二元指标。仅编译已注册五步链，不生成代码；默认不调用模型，可选候选规划须单独授权。预览不修改正式计划；新范围必须重新审核。')
    upload=st.file_uploader('上传单表 CSV 或 Parquet'+('（留空沿用原始数据）' if previous else ''),type=['csv','parquet'],key='cfg_upload_'+(previous['id'] if previous else 'new'))
    try:
        if upload:
            if upload.size>20_000_000:raise DesignError('文件超过20 MB，本地受限流程暂不接受。')
            payload=upload.getvalue();name=upload.name;uid=co.ws.ingest(payload,name);frame=co.ws.load_upload(uid)
            filekey=hashlib.sha256(payload).hexdigest()[:12]
            import_key='config_import_'+(previous['id'] if previous else 'new')+'_'+filekey
            if import_key not in st.session_state:st.session_state[import_key]=co.record_import(uid)
        elif previous:
            payload=None;name=None;uid=previous['source']['raw_upload_id'];frame=co.ws.load_upload(uid);filekey=uid[:12]
        else:
            st.info('先上传文件查看结构；上传不生成研究方案、批准或统计运行。');return
        cols=list(frame.columns)
        st.write(f'数据预览：{len(frame):,} 条记录，{len(cols)} 个字段。没有自动删除、填补或筛选。')
        st.dataframe(frame.head(12),hide_index=True,width='stretch')
        st.dataframe([{'字段':str(k),'类型':str(frame[k].dtype),'缺失数':int(frame[k].isna().sum())} for k in cols],hide_index=True,width='stretch')
        prefix='cfg_'+(previous['id'] if previous else 'new')+'_'+filekey+'_'
        def text(label,field,default=''):
            return st.text_input(label,value=prior.get(field,default),key=prefix+field)
        def select(label,field,choices,default=None):
            saved=prior.get(field,default)
            return st.selectbox(label,choices,index=choices.index(saved) if saved in choices else 0,key=prefix+field)
        question=text('研究目标','objective','比较两个方案在已确认观察窗口内的二元结果比例，并报告差异与证据限制。')
        unit=text('每行的分析单位','analysis_unit')
        entity=select('唯一标识字段（没有时必须明确记录粒度）','entity',[None]+cols)
        grain=text('记录粒度与纳入范围','record_grain')
        independent=st.checkbox('我确认每行是一个独立观察单位，不是同一实体重复抽检或纵向记录',key=prefix+'independent')
        group=select('比较组字段','treatment',cols)
        gvalues=sorted(frame[group].dropna().astype(str).unique().tolist())
        if len(gvalues)!=2:
            st.error('当前字段不恰好包含两个组。请选择正确分组字段；系统不会替你排除其他组。');return
        control=select('对照组编码','control_value',gvalues)
        treated=select('比较组编码','treated_value',gvalues,default=next(x for x in gvalues if x!=control))
        clabel=text('对照组业务含义','control_label');tlabel=text('比较组业务含义','treated_label')
        outcome=select('正式二元结果字段','outcome',cols,default=next((x for x in cols if x!=group),cols[0]))
        ovalues=sorted(frame[outcome].dropna().astype(str).unique().tolist())
        if not 1<=len(ovalues)<=2:
            st.error('当前结果字段不是二元编码；请选择正确字段。本阶段不把连续指标自动二分。');return
        negative=text('否定事件编码（映射为0）','negative_value',ovalues[0])
        positive=text('肯定事件编码（映射为1）','positive_value',ovalues[-1] if len(ovalues)>1 else '')
        metric=text('结果指标名称','metric');display=select('展示单位','unit',['概率','比例','百分比'])
        window=text('观察窗口（说明本表全部记录对应的窗口）','window')
        st.caption('本版本不按日期自动切片。若改变窗口，必须提供实际覆盖该窗口的数据，不能只改文字重复使用旧记录。')
        assignment=select('分配机制','assignment',['unknown','randomized'])
        st.caption('unknown：随机化依据未知，仅描述；randomized：需要核对明确设计来源。两个组不证明随机分配。')
        url=text('数据／设计公开来源网页（依据未知可留空）','source_url')
        evidence=text('设计依据与适用范围说明','design_evidence')
        source_confirmed=st.checkbox('我已核对来源明确支持本数据与观察单位的随机分配，不是仅根据组名判断',key=prefix+'source') if assignment=='randomized' else False
        if assignment=='unknown':st.warning('将生成描述性研究路径，只调用实际描述统计和证据核验，不调用A/B，不生成因果效应区间。')
        confirmed=st.checkbox('我已核对字段、组别含义、二元编码、分析单位与窗口，确认此数据合同',key=prefix+'contract')
        st.write('正式方案采用：'+outcome+' / '+metric+'；'+tlabel+' 对比 '+clabel+'；窗口 '+window+'。预览字段不会自动批准任何计算。')
        if st.button('确认合同并生成待审计划',disabled=not confirmed,key=prefix+'compile',type='primary'):
            cfg=dict(objective=question,analysis_unit=unit,entity=entity,record_grain=grain,independent_records_confirmed=independent,
                     treatment=group,control_value=control,treated_value=treated,control_label=clabel,treated_label=tlabel,outcome=outcome,
                     negative_value=negative,positive_value=positive,metric=metric,unit=display,window=window,assignment=assignment,
                     source_url=url,design_evidence=evidence,source_confirmed=source_confirmed)
            BinaryResearchConfig.model_validate(cfg)
            request=st.session_state.setdefault(prefix+'request',uuid.uuid4().hex)
            if previous:task=co.revise_configurable(previous['id'],configuration=cfg,request_id=request,human_confirmed=confirmed,payload=payload,name=name,stage2=True)
            else:task=co.create_configurable(payload,name=name,configuration=cfg,request_id=request,human_confirmed=confirmed,stage2=True,import_event_id=st.session_state[import_key])
            st.query_params['automation']=task['id'];st.query_params.pop('config_edit',None);st.rerun()
    except (ValueError,OSError) as exc:
        st.error(str(exc) if isinstance(exc,ValueError) else '文件读取失败，尚未创建可执行计划。请核对 CSV/Parquet 格式。')
        st.caption('原有研究与历史运行保留；合同确认不是执行批准。')
