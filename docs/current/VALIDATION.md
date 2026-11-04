# 验收记录与使用限制 · 0.16.0 第二轮

[2026-11-05 阶段冻结与最新验收](../stage/验收与整合.md)


本页对应已发布的第二轮功能提交 [3f22318](https://github.com/JiamWei624/CausalOps/commit/3f223187d966c5a71263d54df7ba63ced4fec60c)。

| 核验对象 | 验收结果 | 范围 |
|---|---|---|
| 本地源码 | 配置指定原始数据文件后，633 项测试通过 | Windows、Python 3.11、本地模式；含真实营销样本测试 |
| GitHub 持续集成 | [该功能提交的 Windows 工作流](https://github.com/JiamWei624/CausalOps/actions/runs/41621014073) 已通过 | 未配置原始压缩包时，依赖真实文件的测试明确跳过 |
| 浏览器操作 | 已分别通过上传压缩包和指定本机文件建立任务；实际完成审核、计算、下载 HTML 和结果追问 | 错包被拒绝；未确认时不能批准；答复绑定已保存的运行 |
| 数值与单位 | 男装邮件与对照组共 42,613 人；核对两组分母、访问计数、绝对差与标准误 | 差值 7.659 个百分点，95% 区间 6.995 至 8.323 个百分点。相对增幅另用对照组作分母 |
| 其他入口 | 葡萄酒报告、两种合成政策情形均经浏览器操作；检查 390 像素宽首页 | 不代表所有设备和所有数据均已验收 |

**复现。** 按[安装指南](INSTALLATION.md)配置环境，按[案例验收](PHASE2_ACCEPTANCE.md)准备真实文件，执行 `python -m pytest tests/test_hillstrom_case.py -q`。全量检查执行 `python -m pytest -q`。

**仍需验证。** 第二轮没有复测所有外部模型服务，也没有完成独立用户试用。既有 90 次模拟中的 PSM 区间覆盖为 4/6，应保留小样本模拟的不确定性。[统计核查与限制](STATISTICAL_AUDIT.md)

[上一轮安装包、统计模拟与界面记录](https://github.com/JiamWei624/CausalOps/blob/3f223187d966c5a71263d54df7ba63ced4fec60c/docs/current/VALIDATION.md) · [五类真实数据的测试范围](REAL_DATA_EXPERIENCE.md)
