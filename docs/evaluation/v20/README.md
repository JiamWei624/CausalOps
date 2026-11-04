# 浏览器评测基线的复现

被测应用为 `5f257e8`，评测代码位于同一仓库 `scripts/eval_v20`。运行环境为 Windows、Python 3.11、项目统计与 Streamlit 依赖、Python Playwright 及 Chromium。操作浏览器的程序不读评分答案；初始化真实研究记录和结束后检查证据属于控制器。正式付费调用与 UI 操作分开计量。

## 重评分与查看证据

现有文件夹后缀 `review/frozen` 为原始评分。用本分支代码从仓库根目录运行以下命令会重读已经关闭的24个槽，输出必须使用新的空路径。

```powershell
$py = './.venv/Scripts/python.exe'
$env:PYTHONPATH = (Resolve-Path src).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = (New-Item -ItemType Directory -Force ./artifacts/project-temp).FullName
$env:TMP = $env:TEMP
& $py scripts/eval_v20/controller/grade.py --output ./artifacts/v20-pilot/review/recheck-01
```

从 `review/frozen/逐次三层证据.json` 定位槽位，打开同目录所指向的 `interaction.json` 与 `browser/*-after.png` 核对最后一轮。题面在 `actor/tasks.json`，参考值单独在证据根目录的 `sealed/gold.json`。初始运行编号随新工作区变化，重新造库时应重新生成封存答案。

## 从空环境重做

保留原始证据目录。推荐独立工作树和新输出根目录，用同一冻结产品源码及相同测试脚本。从项目根目录运行，设置 CAUSALOPS_V20_WORKSPACE 为新的评测目录，并用 CAUSALOPS_HILLSTROM_ARCHIVE 指向官方原始压缩包。Git 由 PATH 定位。测试环境须单独安装 Playwright 与 Chromium，可用 CAUSALOPS_BROWSER_EXECUTABLE 指定已有浏览器。旧批次的关闭槽和实际请求记录保存在本地档案。

```powershell
# $out 应与复现副本 ROOT/OUT 完全一致
$out = [IO.Path]::GetFullPath('./artifacts/v20-replay-new')
$env:CAUSALOPS_V20_WORKSPACE = $out
& $py scripts/eval_v20/smoke.py "$out/smoke"
foreach ($case in 'B01','B02','B03','B04','B05','B06') {
    & $py scripts/eval_v20/controller/seed.py $case "$out/fixtures/$case"
    if ($LASTEXITCODE -ne 0) { throw "初始记录未生成：$case" }
}
& $py scripts/eval_v20/controller/freeze.py
& $py scripts/eval_v20/browser/batch.py --stage fixed --jobs 2
# 先检查六槽终态、截图、授权与实际提交，再启动重复尝试
& $py scripts/eval_v20/browser/batch.py --stage adaptive --jobs 2
& $py scripts/eval_v20/controller/grade.py --output "$out/review/frozen"
& $py scripts/eval_v20/browser/reload_probe.py "$out/attempts/fixed/B04/attempt-1" "$out/supplemental-history-reload-01"
```

密钥通过隐藏提示输入或在单次进程中传入，浏览器不采集密钥输入界面。原始运行脚本拒绝覆盖已开始的槽位。若实际批次中止，应保留中止记录，另开复现目录。本轮全部24槽均有终态。单次回放可能取得不同的模型回复，核对的是流程、输入、运行绑定和评分规则。正式报告与任务策略、判据和限制见同目录 REPORT.md 以及 scripts/eval_v20/controller/PROTOCOL.md。