# CausalOps 0.21.0b2 · Windows安装与启动

本说明适用于Windows x64、Python 3.11和本地单用户。React是默认受限研究工作台；Streamlit完整兼容入口同时启动，使用同一个工作区。发行包包含前端，无需Node.js。开发人员修改前端时才需要Node与npm。

## 1. 安装发行包

先将wheel、`requirements-windows-py311.lock.txt`和SHA-256清单放在同一目录，核对下载来源与清单；本地候选不代表已发布下载地址。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows-py311.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\causalops_agent-0.21.0b2-py3-none-any.whl
.\.venv\Scripts\python.exe -m pip check
```

锁文件是本次实际验证的Windows/Python3.11依赖组合，包括pywin32。不要复用混合Anaconda/其他Python的site-packages或手工注入旧环境`.pth`。可选research等未验证扩展不属于此安装验收。网络受限时可提前下载锁文件中的公开依赖wheel，但不能把私有模型凭据作为安装参数。

## 2. 一个命令打开默认工作台

```powershell
.\.venv\Scripts\causalops-workbench.exe --workspace .\causalops-workspace
```

默认React地址：`http://127.0.0.1:8790`；完整Streamlit地址：`http://127.0.0.1:8791`。启动器在两个服务均通过健康、版本和工作区身份核验后才打开浏览器。终端保留前台监督，两个实际服务隐藏运行，不需要手工开第二个终端。

工作区路径应固定；命令参数优先于`CAUSALOPS_HOME`。未显式指定时，使用环境变量，再使用当前目录下的`causalops-workspace`。不要在不同目录运行默认命令后误以为研究历史被删除。

从React左侧底部“完整工作台与专业工具”进入兼容界面。也可用`causalops-streamlit --workspace .\causalops-workspace`打开同一服务组合的Streamlit界面；已有合法组合会复用，不新建不同数据目录。

## 3. 停止、重启与冲突

研究运行时先在页面请求暂停并等待安全边界。Ctrl+C或关闭启动窗口会停止两个本地服务，数据库与Run保留；重新运行同一命令后，通过原页面核查恢复，不能盲目重算。监督器检测任一服务退出会关闭另一服务；Windows进程组随监督器退出清理。

- 端口已占用：不会关闭其他程序，也不会把别的工作区当当前研究。明确关闭原启动窗口，或指定两个空闲端口。
- 服务提前退出/超时：不会打开“已就绪”页面；查看工作区`runtime`日志。
- 前端缺失、版本或内容校验失败：重新安装完整wheel；不从当前目录寻找未知dist。
- 缺少依赖：重新按锁文件安装并执行`pip check`，特别核对Python3.11与Windows依赖。

```powershell
causalops-workbench --workspace .\causalops-workspace --port 8890 --streamlit-port 8891
causalops-workbench --workspace .\causalops-workspace --diagnose
causalops-workbench --workspace .\causalops-workspace --no-browser
```

## 4. 从清洁源码包安装

解压`causalops-agent-0.21.0b2-source.zip`并进入项目目录。源码包也包含已构建资源，因此下面不需要Node：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows-py311.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\causalops-workbench.exe --workspace .\causalops-workspace
```

只有重新生成前端时执行`python scripts/build_frontend.py`，该命令需要Node并按`frontend/package-lock.json`执行npm ci、TypeScript/Vite构建和资源校验清单生成。然后重新构建wheel。普通安装用户不需要执行。

## 5. 升级与历史

升级前暂停/完成任务、停止原版本并备份工作区。不要让两个不同源码版本同时写入同一工作区。旧历史能通过合法引用只读查看，不代表旧批准在新源码下仍允许继续执行。遇到数据、合同、计划或执行源码失效，应按原门禁处理，不能手工改数据库或收据。

默认关闭模型与外部追踪。React当前只用本地确定性回复；Streamlit模型连接、授权与专业入口保留。无论默认UI如何变化，模型建议、研究诊断和用户决定都不产生统计执行权限。

下一步：[React完整使用教程](REACT_WORKSPACE_GUIDE.md)；[能力与兼容入口](../releases/react-workspace-beta/COVERAGE.md)。

## 6. 从0.21.0b1原地升级至0.21.0b2

1. 完成或暂停研究，停止b1启动器，备份整个工作区。不要让两个版本同时写入。
2. 在原Python环境执行 `python -m pip install --no-deps --upgrade .\causalops_agent-0.21.0b2-py3-none-any.whl`，然后执行 `python -m pip check`。
3. 以原来的 `--workspace` 路径启动，不移动数据库或重写Run路径。
4. 原报告、Run、旧诊断及研究决定/修订历史保留。旧批准不自动取得新源码执行权限。
5. 若面板明确提示“研究诊断需要重新核验，原有报告和历史记录已保留。”，点击“重新检查研究证据”进入诊断，再显式提交同名检查。此操作生成新诊断版本，不重新计算统计，也不覆盖旧报告和决定。

真正的数据、来源哈希或任务归属错误仍会拒绝读取，不能当作普通诊断过期绕过。React附件最多20MB、100000行、200列；读取器另保留50MB字节与256MB解码内存限制，不自动截断或抽样。
