# 真人试用主持手册

目前尚无真人独立使用的正式验收数据。先按[安装说明](../../../current/INSTALLATION.md)安装此快照，取得已核对的公开示例CSV。在源码根目录准备材料并为每人使用独立目录：

```powershell
python scripts/usability_study.py prepare --root ./usability-runs/study01 --public-csv ./public-example.csv
python -m causalops.launch --workspace ./usability-runs/P01/workspace --port 8513
```

P01只是目录示例，不是已经招募的用户。本机链接不是永久公开服务。默认不接入模型、不录屏或录音；必须先按[同意模板](CONSENT.md)确认，不能收集私人资料或密钥。每人独立浏览器与工作区，B/C同人关联；不让多名用户并发共用此单用户平台。

仅给[任务说明](PARTICIPANT.md)和数据资料，不提前教授按钮路径、数值或答案。计时/帮助按[协议](PROTOCOL.md)与[记录规则](RECORDING.md)，B实际完成后才可建立C起点；提供受控起点须另记介入。分级帮助：复述目标、解释术语/信息区、具体字段/按钮指导、代操作。不得替用户批准、改设计事实或隐藏失败。

先让用户自由说明结论、证据和限制，再中立追问。提示后回答不能算原始理解。参考仅供主持：A女性标记14/24、男性21/24，差29.1667个百分点，原近似区间[4.9045,53.4288]个百分点；合成B完成6/12与9/12，C留存4/12与6/12。后两者无因果区间，最终按真实Run核对，不以参考数字替代计算。

准备脚本生成空表，不自动生成参与者。local_user里程碑不证明真人，也不等于点击数/耗时。实际记录留本地，不提交Git。只读脱敏导出：

```powershell
python scripts/usability_study.py export-events --workspace ./usability-runs/P01/workspace --out ./usability-runs/P01/metadata.json
```

不导出原始行、目标/备注、模型原文或凭据；不同既有文件拒绝覆盖。模型对照为另行授权的选做项，目前没有真人对照结论。
