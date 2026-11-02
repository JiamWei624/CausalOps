"""Chinese display labels; citation identity and original titles remain in the catalog."""
import streamlit as st

LABELS = {
    "pandas": "数据表的描述性统计", "pearson": "皮尔逊相关系数与检验",
    "ols": "普通最小二乘回归", "glm": "广义线性模型", "logit": "二元逻辑回归",
    "welch": "独立样本均值比较", "cuped": "利用实验前数据提高在线对照实验的灵敏度",
    "doubleml": "双重机器学习模型", "crossfit": "样本切分与交叉拟合",
    "did": "面板数据模型示例", "design": "在线对照实验的实验前设计",
    "airbnb": "市场平台实验中的干扰与集群随机化", "chat": "在线客服中人工智能与顾客互动的随机现场实验",
    "human": "以人为中心的人工智能现场实验", "utd": "得克萨斯大学达拉斯分校期刊目录",
    "mcp": "模型上下文协议开发工具", "deepseek": "结构化输出接口",
    "did-modern": "多时期双重差分入门", "iv_official": "工具变量与第一阶段诊断",
    "rd_official": "断点回归工具与实现", "staggered_official": "交错处理下的分组分期效应",
    "jfe_baker_full": "交错双重差分设计的可靠性", "isr_caps_full": "平台监管实证研究",
    "csr_rd_full": "企业社会责任与财务表现", "statsmodels_wald": "线性约束的联合检验",
    "statsmodels_cov": "稳健协方差估计", "robust_ar_theory": "多工具变量与弱识别",
    "doubleml_resampling": "样本分割与交叉拟合", "matchit_estimand": "匹配后效应与适用人群",
}

def show_source(source):
    key = source["source_id"]
    label = LABELS.get(key, "查看登记来源")
    scope = source.get("access_scope", "")
    if scope == "abstract_only":
        prefix = "实证案例（摘要）"
    elif scope.startswith("full_text_selected"):
        prefix = "文献选读"
    else:
        prefix = "方法参考"
    st.link_button(f"{prefix}｜{label}", source["url"], help=source["title"])
