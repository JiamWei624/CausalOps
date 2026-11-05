"""Public case entry. No automatic downloads or approval."""
import os
from pathlib import Path

import streamlit as st

from causalops.sample_data.hillstrom import COUNTS, DOWNLOAD, QUESTION, SOURCE, cohort, contract


def preview():
    with st.container(key="panel_marketing_preview"):
        st.caption('公开研究案例　/　随机营销实验')
        st.subheader('营销邮件与两周访问率')
        for label, (visits, total) in COUNTS.items():
            rate = visits / total
            st.markdown(f'**{label}**　{rate:.2%}')
            color = '#16756d' if label=='男装邮件' else '#56798a'
            st.html(f'<div aria-hidden="true" style="height:10px;background:#e6eeec;border-radius:3px"><div style="height:100%;border-radius:3px;width:{rate/.20*100:.4f}%;background:{color}"></div></div>')
        control, treated = COUNTS['未发邮件'], COUNTS['男装邮件']
        delta = 100 * (treated[0] / treated[1] - control[0] / control[1])
        st.caption(f'同一尺度 0–20%　｜　绝对差 {delta:.2f} 个百分点')
        st.caption('基于公开数据的已核对摘要。当前任务的区间与诊断在审核并运行后生成。')


def render():
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace

    st.title('营销邮件实验', anchor=False)
    if st.button('进入五步自动化研究'):
        st.query_params['route']='automation'
        st.rerun()
    left, right = st.columns([1.15, 1])
    with right:
        preview()
    with left:
        st.subheader('研究对象与指标')
        st.write('原实验将 64,000 名客户随机分配到三组。本例预先选取男装邮件与未发邮件两组，比较分配后两周内至少访问一次的客户比例。女装邮件组不进入这次比较。')
        st.markdown(f'[实验发布者说明]({SOURCE}) · [同期挑战报告](https://stochasticsolutions.com/pdf/HillstromChallenge.pdf) · [下载公开数据文件]({DOWNLOAD})')
        st.write('分析单位为客户。行号用于标识记录；随机分配依据实验说明。收入、成本与次年表现不属于本次指标。')
    st.subheader('用公开原始数据建立研究任务')
    location = os.environ.get('CAUSALOPS_HILLSTROM_ARCHIVE')
    configured = Path(location) if location else None
    if configured and configured.is_file():
        st.caption('已找到本机配置的公开实验文件，建任务前将核对文件指纹。')
        upload = None
    else:
        upload = st.file_uploader('上传上方下载的原始 .csv.gz 文件', type=['gz'])
    ready = bool(upload or (configured and configured.is_file()))
    confirmed = st.checkbox('已核对来源、随机分配、两组定义与两周访问指标')
    if st.button('创建研究任务并生成待审方案', type='primary', disabled=not (confirmed and ready)):
        try:
            if configured and configured.is_file():
                if configured.stat().st_size > 5_000_000:
                    raise ValueError('文件超过本例固定压缩包的大小上限。')
                payload = configured.read_bytes()
            else:
                if upload.size > 5_000_000:
                    raise ValueError('文件超过本例固定压缩包的大小上限。')
                payload = upload.getvalue()
            data = cohort(payload)
        except (OSError, ValueError) as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else '无法读取公开实验文件。')
            return
        service = ResearchService(AssistantWorkspace())
        sid = service.create_task(payload=data, name='hillstrom_men_visit.csv', title='营销邮件与两周访问率')
        service.contracts.save(sid, contract(), expected_sha=None, human_confirmed=True)
        flow = service.start(sid, QUESTION, mode='plan')
        st.query_params.update(route='assistant', assistant=sid, flow=flow['id'])
        st.rerun()
