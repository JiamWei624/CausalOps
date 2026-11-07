# 安装、启动与故障恢复 · 0.19.0b1

> 本候选新增受限Hillstrom五步工作台，见[自动化教程](AUTOMATION_GUIDE.md)。旧版单次流程继续保留；新增[显式诊断与需求草案教程](DIAGNOSTICS_GUIDE.md)。安装后请核对软件包0.19.0b1与启动地址构建指纹。

新增[研究决策记忆教程](DECISION_MEMORY_GUIDE.md)。本次发布准备记录时0.19.0b1尚未推送，0.18.0b1为此前公开版本。公开状态以GitHub对应分支及精确提交核对为准；不要假定PyPI或Release存在本版本。

本文面向第一次运行 CausalOps 的使用者。先完成本地示例，再选择是否接入模型。仓库公开只代表源码可获取，不代表把本机工作区公开或提供在线多人服务。

## 1. 需要准备什么

- 已验证平台：Windows 64 位、Python 3.11。先执行 `python --version` 与 `python -c "import platform; print(platform.architecture()[0])"`。其他 Python 主版本或操作系统未在本次发行复现中验证。
- 磁盘：建议在数据盘预留 6 GB，并使用较短的工作区路径（例如 `E:/cops-work`），避免 Windows 深层文件名限制；完整依赖约数 GB，CSV/Parquet 与结果另计。内置示例仅约 84 KB。实际新环境占用以验收记录为准。
- 浏览器：可访问本机 `127.0.0.1` 的现代浏览器。无需安装 MySQL、Java、Hive、Docker、Power BI 或下载本地大模型。
- 模型 API 是可选项；本地示例和基础统计不需要账号、密钥或外网。

## 2. 在线安装（从源码目录执行）

在 GitHub 的 Code 菜单下载 ZIP 并解压，或使用 Git 克隆仓库。把项目放在数据盘。以下 E 盘只是可替换的路径示例，不要求与作者机器目录一致。

```powershell
New-Item -ItemType Directory -Force -Path "E:/causalops-temp", "E:/causalops-cache/pip", "E:/causalops-cache/matplotlib"
$env:TEMP = "E:/causalops-temp"
$env:TMP = "E:/causalops-temp"
$env:PIP_CACHE_DIR = "E:/causalops-cache/pip"
$env:MPLCONFIGDIR = "E:/causalops-cache/matplotlib"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m venv "E:/causalops-env"
& "E:/causalops-env/Scripts/python.exe" -m pip install -r requirements-runtime-win-py311.txt
& "E:/causalops-env/Scripts/python.exe" -m pip install --no-deps .
& "E:/causalops-env/Scripts/python.exe" -m pip check
```

不使用系统 Python 的 site-packages，不需要管理员方式运行。不确定解释器位置时，用 `where.exe python` 检查；带引号的完整解释器路径前使用 PowerShell 调用符 `&`。

如已有 0.16.0 安装，更新代码后请在新源码根目录用同一虚拟环境再次执行上面的安装命令，再重启服务。第二轮首页应显示营销邮件预览与三张案例卡；本候选应显示0.19.0b1，并同时核对构建指纹。葡萄酒样本随包提供；营销案例需另取[指定公开压缩包](PHASE2_ACCEPTANCE.md)。

## 3. 离线安装

本轮发布对象是 GitHub 源码；此前同版本号的离线包对应其自身构建。如使用单独制作的完整离线包，其中包含 wheelhouse、依赖哈希锁、应用 wheel 哈希、许可证资料与安装器。仅源码 ZIP 没有依赖包，不能冒充离线安装包。解压后在该目录执行：

```powershell
python install_offline.py --destination "E:/causalops-env-new"
```

离线包已固定换行规则，UCI 原始 CSV 按二进制原样保存，避免 Windows Git 自动换行改变校验值。

目标环境必须不存在；安装器不会删除旧环境。安装器核对 Python 3.11、逐项依赖 SHA-256 和应用 wheel SHA-256，执行 pip check，并用隔离模式确认导入的是新环境中的应用。数据与旧工作区不会被迁移或删除。

## 4. 统一启动

```powershell
& "E:/causalops-env/Scripts/python.exe" -m causalops.launch --workspace "E:/causalops-work" --port 8513
```

保留启动进程。使用终端本次显示的完整地址，形如 `http://127.0.0.1:8513/?route=home&release=0.19.0b1&build=...`；省略 `--port` 时同样使用 8513。首页与其他主页面顶部显示实际版本及构建号。源码快捷启动脚本和安装版均进入同一个工作台。若使用源码目录的双击脚本，请先为该次启动指定已经安装依赖的解释器，或把虚拟环境放在源码目录 `.venv` 中。脚本不再回退到作者机器的其他目录或旧版作品集。

```powershell
$env:CAUSALOPS_PYTHON = "E:/causalops-env/Scripts/python.exe"
& ".\启动作品集.cmd" --workspace "E:/causalops-work" --port 8513
```

工作区保存上传文件、SQLite 研究记录、检查点、图表、报告与临时文件。应用自动把自身缓存和临时目录放在工作区内。不要把工作区加入 Git。浏览器会话中的 API 密钥不会写入工作区；服务停止后可能需重新输入。

## 5. 更新与旧页面

先等待后台任务完成或在界面请求停止，然后停止旧服务、更新应用。保留原工作区后重新启动。只对本项目登记的进程允许：

```powershell
& "E:/causalops-env/Scripts/python.exe" -m causalops.launch --workspace "E:/causalops-work" --port 8513 --restart
```

启动器核对进程创建时间、命令与服务归属；后台任务未结束时拒绝重启。其他程序占用端口时不关闭它，改用其他端口。更新代码后，旧批准不会自动迁移到新计算；程序会核对绑定版本。不要删除数据库解决界面问题。

旧书签未必包含构建号，旧标签页也可能仍显示先前渲染内容；先用本次输出的完整地址重新打开，再核对顶部实际版本。本教程不把任何旧页面问题未经检查就归因于浏览器缓存。

## 6. 常见问题

| 现象 | 核查与处理 | 保留内容 |
|---|---|---|
| localhost 拒绝连接 | 确认启动命令仍运行、地址和端口一致；执行 `--diagnose` 查看状态 | 不删除工作区 |
| 看见旧标题或旧版本 | 对照本次启动 URL 的 release/build 与页面顶部；停止旧服务再启动 | 保留历史运行 |
| 模型已配置但未验证 | 在首页展开连接配置并测试；不能把填入密钥当作成功 | 密钥仅会话内存 |
| HTTP 400/401/429 | 核对官方地址、API 模型 ID、协议、额度；不要反复重发相同错误请求 | 本地统计仍可使用 |
| 上传文件乱码或只有一列 | 核对 UTF-8/GB18030、逗号/分号/制表符 | 不自动改原文件 |
| 上传过大 | 上限 50 MB、10 万行、200 列，解码后 256 MB；先在外部生成合适的分析表 | 不能声称已处理完整超限文件 |
| 批准按钮不可用 | 阅读具体缺项；确认必要事实、字段与版本。未知事实留空 | 不用随意勾选绕过 |
| 结果追问要求先选运行 | 先完成基础报告或已批准分析，并在当前任务选择对应运行 | 方法咨询不等于结果 |
| 刷新后密钥丢失 | 重新在首页输入；任务历史通过工作区恢复 | 研究记录与密钥独立 |
| 组件导入失败 | 使用同一版本完整安装；不要手动复制单个旧模块覆盖 | 新环境可验证 |

## 7. 部署边界

代码开放与 Web 服务开放是两件事。当前服务只监听本机，面向单用户；没有公网鉴权、多租户隔离、恶意文件沙箱或分布式任务队列。不要直接改监听为公网地址。独立用户验收仍待进行，自动浏览器复现不是人类用户效率对照实验。

## Beta 的本地资源

首页葡萄酒示例随包提供。营销实验可在页面上传教程指定的公开压缩包，也可通过 CAUSALOPS_HILLSTROM_ARCHIVE 指定同一文件。本地模式和这两个示例均不要求模型密钥。

旧版评测的已准备数据目录可用 CAUSALOPS_PUBLIC_CATALOG 指向 catalog.json，默认从启动目录下的 data/public/prepared 读取。清单内的 Parquet 须位于清单所在目录内并通过摘要校验。浏览器评测输出由 CAUSALOPS_V20_WORKSPACE 指定。历史私有示例仅在显式登记数据和 CAUSALOPS_PRIVATE_DATA_ROOT 后可用，公开快照不分发相应数据。旧实验记录中的 artifacts 标识对应本地归档，不作为公共下载链接。

## 诊断Beta升级边界

0.19.0b1增加只读诊断表和工作台，保留原统计服务。先保留原工作区副本，再安装到新环境；不要删除历史数据库。批准绑定数据、计划及源码身份，升级后旧执行许可可能不再有效，须经原服务核查，不能通过诊断或草案绕过。已完成历史按只读接口查看；本轮独立验收使用新工作区，不代表所有用户数据库升级组合都已验证。
