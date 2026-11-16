# CausalOps React工作台 0.21.0b1

真实服务前端；不是静态原型。普通用户安装发行wheel后，通过`causalops-workbench --workspace ./causalops-workspace`自动启动React和同源Python API，并保留同工作区Streamlit入口，不需要Node。

[完整安装](../docs/current/INSTALLATION.md) · [完整使用教程](../docs/current/REACT_WORKSPACE_GUIDE.md) · [能力和兼容入口](../docs/releases/react-workspace-beta/COVERAGE.md)

## 开发构建

在根目录运行`python scripts/build_frontend.py`，需要已安装Node及npm。脚本按本目录package-lock执行npm ci、TypeScript和Vite构建，并复制到`src/causalops/web_assets`，生成版本和SHA-256清单。

本目录私有版本为0.21.0-beta.1，与Python发行版本0.21.0b1对应，不表示独立发布的前端软件。构建产物随Python包提供，运行时不执行npm。

## 受限能力与权限

会话、CSV/Parquet、合同、确定性候选、采纳、正式审核、独立开始、真实步骤、暂停/取消/核查恢复、统计报告、显式诊断、决定及追加历史均调用原Python服务。React聊天当前仅本地确定性回复；模型候选/授权、原单次研究、专业方法和需求草案通过Streamlit使用。

API仅本地回环，同源Cookie、CSRF、Host/Origin、绑定、版本、哈希和幂等检查保持。新增health只返回版本、匿名工作区摘要及服务实例状态，不返回CSRF或执行权限。聊天、诊断和决定不授予统计执行权限。

前端组件测试：`npm test`；实际浏览器验收与单元测试单独记录。不存在真人独立使用验收数据，不宣称通用自主规划或公网多人安全。
