from __future__ import annotations

from causalops.schemas import AssignmentMechanism, DataStructure


_ASSIGNMENT_LABELS = {
    AssignmentMechanism.UNKNOWN: "未知／待确认",
    AssignmentMechanism.RANDOMIZED: "随机分配",
    AssignmentMechanism.AS_IF_RANDOM: "近似随机分配",
    AssignmentMechanism.OBSERVATIONAL: "观察性分配",
}

_DATA_STRUCTURE_LABELS = {
    DataStructure.UNKNOWN: "未知／待确认",
    DataStructure.CROSS_SECTION: "横截面",
    DataStructure.PANEL: "面板数据",
    DataStructure.REPEATED_CROSS_SECTION: "重复横截面",
}

_RISK_MESSAGES = {
    "instruction_override": "研究问题包含疑似覆盖系统指令的内容，已在调用模型前阻断。",
    "secret_exfiltration": "研究问题包含疑似索取密钥或系统信息的内容，已在调用模型前阻断。",
    "code_execution": "研究问题包含疑似执行系统命令的内容，已在调用模型前阻断。",
    "role_override": "研究问题包含疑似改变模型权限或角色的内容，已在调用模型前阻断。",
    "provider_error": "模型服务调用失败；草案未进入执行链路。",
    "provider_ignored_json_mode": "模型返回内容混入了说明文字；系统仅提取唯一 JSON 并完成本地严格校验。",
    "schema_violation": "模型输出不符合研究设计结构，当前草案不可执行。",
    "unverified_assumption_removed": "模型声称的随机化或识别假设已被清空，必须由人工事实或确定性诊断确认。",
    "method_intent_guard_applied": "系统已按用户明确的方法意图调整候选顺序；这不代表方法条件已经满足。",
    "sensitive_treatment": "处理变量被标记为敏感字段，需要单独进行伦理与合规审核。",
    "hallucinated_reference": "草案引用了数据集中不存在或不允许使用的字段。",
}

_SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


def assignment_label_zh(value: AssignmentMechanism) -> str:
    return _ASSIGNMENT_LABELS[value]


def data_structure_label_zh(value: DataStructure) -> str:
    return _DATA_STRUCTURE_LABELS[value]


def proposal_risk_message_zh(code: str, fallback: str) -> str:
    return _RISK_MESSAGES.get(code, f"研究设计存在需审核风险：{fallback}")


def proposal_risk_severity_zh(severity: str) -> str:
    return _SEVERITY_LABELS.get(severity.lower(), severity)

