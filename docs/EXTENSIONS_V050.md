# CausalOps 0.5.0：方法、全文依据与互操作

## 使用路径

启动原工作台，打开“扩展研究设计”。选择方法，批量填写映射并生成候选。回“任务与对话”接受候选，登记具体研究设计依据和适用的人工事实，再执行。模型只提案/解释，不确认这些事实。报告在“结果与报告”，数字通过运行证据进入同页问答。

## 执行范围

| 方法 | 实现 | 本版限制 |
|---|---|---|
| IV 2SLS | linearmodels 7.1 IV2SLS，robust/clustered | 一个内生处理，数值控制，秩检查，重复实体需聚类，至少30簇；无AR/CLR弱工具稳健区间，不把第一阶段显著或robust chi²当强工具证明 |
| 清晰RDD | rdrobust 2.1.1，p=1、q=2、tri、mserd、Robust行 | 事先阈值；处理若给出须与阈值完全一致；每侧30行/15种取值、带宽内每侧20行；密度/协变量连续性与带宽敏感性尚需另做，不执行模糊RDD |
| 交错DID | differences 0.3.0 ATTgt、reg、universal基期g−1 | 平衡面板，连续整数期5–30期，最多一万实体，至少两批，每批与从未组至少20实体；从未组cohort为空；静态事前协变量；实体聚类，不支持上层政策聚类、处理反转 |

交错DID分别保存批次×时间ATT、事件期聚合、simple总体聚合及其权重含义。区间是逐点区间，不是同时置信带。不同事件期的批次构成可能改变。固定包的wald_pre_test属性存在results(sample_name)接口错误：本实现直接调用同版本官方helper及原生namedtuple影响函数，测试其路径；检验失败/奇异明确记录不可用，绝不默认通过。处理前显著时降低解释等级，未显著也不能证明平行趋势。

运行证据包含确切设计、人工依据、数据指纹、官方包版本、样本排除和结果哈希。上传数据不自动发送外部模型。官方真实示例仅作数值实现基准，不代表本项目验证了真实数据的识别条件。

## 全文来源与核对范围

- Baker, Larcker & Wang (2022), Journal of Financial Economics 144, 370–395。作者公开全文 https://andrew-charles-baker.github.io/research/articles/staggered_did/did.pdf 。核对PDF第14–15、24–25页；不同批次比较、CS/SA、窗口/基期与干净对照。
- Li & Wang (2024), Regulating Powerful Platforms: Evidence from Commission Fee Caps, Information Systems Research，DOI 10.1287/isre.2022.0191。大学全文 https://udspace.udel.edu/server/api/core/bitstreams/e77c77fc-33e7-4159-8575-9c72d390f8b0/content 。核对PDF第6–7、9、13页；平台直接/溢出作用、匹配、批次DID与稳健性；未核对在线附录。
- Flammer (2015), Does CSR Lead to Superior Financial Performance? A Regression Discontinuity Approach, Management Science 61, 2549–2568。作者全文 https://sites.bu.edu/cflammer/files/2018/09/Flammer_MgtSci2015-1.pdf 。视觉核对PDF第5–6、9页；投票阈值、通过vs实施、密度与事前特征。现代主执行器不照搬旧文的高次全局多项式。

以上仅原创简要方法提炼，不复制全文，不声称复现这些论文；历史3篇摘要仍是摘要卡。知识卡和运行证据分层引用。

## MCP宿主

安装包含mcp可选依赖后运行：

```powershell
python scripts/configure_readonly_hosts.py --project "E:/path/to/CausalOps" --workspace "E:/CausalOps-workspace"
```

只写项目内.codex/config.toml和.mcp.json，遇已有不同配置不覆盖。Codex需打开并信任该项目、重新加载工具；当前已开启聊天不会热加载。宿主仅开放search_methods/read_run_evidence。实际数据证据先在方法页显式导出，无任意SQL/文件/原始行/批准/执行工具。官方配置依据：https://developers.openai.com/codex/mcp/ 。本机已用真实宿主解析和官方SDK stdio验证，但不冒称当前聊天已加载。

## A2A

官方a2a-sdk==1.3.0，JSON-RPC 1.0，127.0.0.1:8512。在扩展页点击审阅会按需启动。请求只允许review_method或read_evidence；结果为任务artifact，主工作台记录审阅事件，不自动修改计划。方法审阅是独立确定性规则角色，不是另一个大模型。SDK参考：https://github.com/a2aproject/a2a-python 。TaskStore当前为进程内；主工作台保存返回事件，但重启远端TaskStore不支持恢复。没有公网认证/多租户，不宣称已具备生产级多Agent自治研究。

## 复现与许可

Python3.11/Windowsx64。离线包按wheel哈希安装，保留精确依赖版本。源码在线安装可用 `pip install ".[app,llm,mcp,extensions,a2a,dev]"`。GPLv3的differences/rdrobust源码随完整离线包附带，原项目MIT不改变依赖许可证。方法诊断和模拟真值验收不能替代陌生使用者提效评测；后者仍待真实参与者。
