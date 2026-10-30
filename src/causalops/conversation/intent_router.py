from __future__ import annotations

import re

from causalops.research import ConversationIntent


_COMPARE = re.compile(r"比较|区别|差异|哪个更|哪种更|还是.{0,20}(合适|可靠|好)|versus|\bvs\b", re.I)
_DIAGNOSE = re.compile(r"诊断|检查|有哪些问题|什么问题|风险|缺少什么|是否满足|能否执行|可行性", re.I)
_EXPLAIN = re.compile(r"为什么|为何|是什么|解释|如何理解|什么意思|能不能直接|是否意味着", re.I)
_CANDIDATE_REVISION = re.compile(
    r"(?:生成|创建|提出|起草|形成|完善).{0,24}(?:候选)?(?:修订|草案|版本|方案)|"
    r"(?:候选修订|候选草案|候选版本)",
    re.I,
)
_MODIFY = re.compile(
    r"改成|改为|改用|换成|使用.{0,16}(方法|模型)|加入|新增|添加|移除|删除|去掉|"
    r"把.{0,40}(作为|设为)|将.{0,40}(作为|设为)|请修改|帮我修改",
    re.I,
)


def route_conversation_intent(message: str) -> ConversationIntent:
    """Conservatively distinguish discussion from a request to change the draft."""

    text = message.strip()
    # An explicit request to create a candidate revision is a state-preserving MODIFY
    # intent even when the same sentence mentions diagnostics, risks, or assumptions.
    # The model may only propose an inactive candidate; acceptance remains human-only.
    if _CANDIDATE_REVISION.search(text):
        return ConversationIntent.MODIFY
    if _COMPARE.search(text):
        return ConversationIntent.COMPARE
    if _DIAGNOSE.search(text):
        return ConversationIntent.DIAGNOSE
    if _EXPLAIN.search(text) and not re.search(r"请|帮我|现在", text[:12]):
        return ConversationIntent.EXPLAIN
    if _MODIFY.search(text):
        return ConversationIntent.MODIFY
    return ConversationIntent.EXPLAIN

