from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from causalops.capabilities import format_method_label, get_method_capability
from causalops.identification import route_identification
from causalops.llm import StructuredModelClient
from causalops.metadata import FieldCatalogEntry
from causalops.research import (
    ConversationIntent,
    DraftRevisionRecord,
    DraftStatus,
    ResearchRepository,
    RevisionSource,
)
from causalops.schemas import CausalMethod, CausalSpec, GateStatus

from .intent_router import route_conversation_intent
from .model_dialogue import (
    DialogueModelError,
    RestrictedResearchDialogueModel,
    UnsafeDialogueInput,
)


_METHOD_ALIASES: tuple[tuple[CausalMethod, tuple[str, ...]], ...] = (
    (CausalMethod.CUPED, ("cuped",)),
    (CausalMethod.EVENT_STUDY, ("事件研究", "event study", "event-study")),
    (CausalMethod.DID, ("双重差分", "difference-in-differences", "did")),
    (CausalMethod.FIXED_EFFECTS, ("固定效应", "fixed effects")),
    (CausalMethod.IPW, ("逆概率加权", "ipw")),
    (CausalMethod.DOUBLE_ML, ("双重机器学习", "doubleml", "double ml")),
    (CausalMethod.PSM, ("倾向得分匹配", "psm")),
    (CausalMethod.AB_TEST, ("a/b", "ab实验", "随机实验")),
    (CausalMethod.REGRESSION_ADJUSTMENT, ("回归调整",)),
    (CausalMethod.DESCRIPTIVE, ("描述性", "描述分析")),
)


@dataclass(frozen=True)
class ConversationTurnResult:
    intent: ConversationIntent
    answer_zh: str
    candidate_revision: DraftRevisionRecord | None = None
    used_model: bool = False
    provider_metadata: dict[str, Any] | None = None


def _mentioned_methods(message: str) -> list[CausalMethod]:
    lowered = message.lower()
    return [
        method
        for method, aliases in _METHOD_ALIASES
        if any(alias.lower() in lowered for alias in aliases)
    ]


def _mentioned_fields(
    message: str, catalog: dict[str, FieldCatalogEntry]
) -> list[str]:
    lowered = message.lower()
    matches: list[str] = []
    for name, entry in catalog.items():
        aliases = {name.lower(), entry.label_zh.lower()}
        if any(alias and alias in lowered for alias in aliases):
            matches.append(name)
    return matches


class DesignConversationService:
    """Versioned dialogue; model changes can only become inactive candidates."""

    def __init__(
        self,
        repository: ResearchRepository,
        *,
        model_client: StructuredModelClient | None = None,
    ) -> None:
        self.repository = repository
        self.model_dialogue = (
            RestrictedResearchDialogueModel(model_client) if model_client else None
        )

    def handle(
        self,
        *,
        session_id: str,
        message: str,
        catalog: dict[str, FieldCatalogEntry],
    ) -> ConversationTurnResult:
        session = self.repository.get_session(session_id)
        if not session.current_draft_revision_id:
            raise ValueError("当前研究会话还没有可讨论的草案。")
        current = self.repository.get_revision(session.current_draft_revision_id)
        intent = route_conversation_intent(message)
        history = self.repository.list_chat_messages(session_id)
        self.repository.add_chat_message(
            session_id,
            role="user",
            content=message,
            revision_id=current.revision_id,
            intent=intent,
        )
        try:
            if self.model_dialogue and intent == ConversationIntent.MODIFY:
                result = self._modify_with_model(
                    session_id, current, message, catalog, history
                )
            elif self.model_dialogue:
                result = self._discuss_with_model(
                    current, intent, message, catalog, history
                )
            elif intent == ConversationIntent.MODIFY:
                result = self._modify(session_id, current, message, catalog)
            elif intent == ConversationIntent.COMPARE:
                result = self._compare(current.spec, message)
            elif intent == ConversationIntent.DIAGNOSE:
                result = self._diagnose(current.spec)
            else:
                result = self._explain(current.spec)
        except UnsafeDialogueInput as exc:
            result = ConversationTurnResult(intent, str(exc))
        except DialogueModelError as exc:
            result = self._deterministic_fallback(
                session_id=session_id,
                current=current,
                intent=intent,
                message=message,
                catalog=catalog,
                reason=str(exc),
            )
        self.repository.add_chat_message(
            session_id,
            role="assistant",
            content=result.answer_zh,
            revision_id=(
                result.candidate_revision.revision_id
                if result.candidate_revision
                else current.revision_id
            ),
            intent=intent,
        )
        return result

    def _deterministic_fallback(
        self,
        *,
        session_id: str,
        current: DraftRevisionRecord,
        intent: ConversationIntent,
        message: str,
        catalog: dict[str, FieldCatalogEntry],
        reason: str,
    ) -> ConversationTurnResult:
        if intent == ConversationIntent.MODIFY:
            return ConversationTurnResult(
                intent=ConversationIntent.MODIFY,
                answer_zh=(
                    "⚠️ 本轮候选修订失败，未创建任何候选版本，当前草案保持不变。\n"
                    f"模型候选被本地安全或一致性门禁拒绝：{reason}\n"
                    "修改请求采用失败关闭（fail-closed）：系统不会在模型失败后"
                    "自动生成替代草案。请修正请求或重新生成候选修订。"
                ),
                candidate_revision=None,
                used_model=False,
            )
        elif intent == ConversationIntent.COMPARE:
            fallback = self._compare(current.spec, message)
        elif intent == ConversationIntent.DIAGNOSE:
            fallback = self._diagnose(current.spec)
        else:
            fallback = self._explain(current.spec)
        return ConversationTurnResult(
            intent=fallback.intent,
            answer_zh=(
                "⚠️ 本轮是本地确定性兜底，不是 DeepSeek 的回答。\n"
                f"模型调用失败原因：{reason}\n"
                "请展开页面顶部的“DeepSeek 连接诊断”并运行一次；"
                "在连接修复前，不要把下方模板当作模型生成的研究解释。\n\n"
                f"【本地草案摘要】\n{fallback.answer_zh}"
            ),
            candidate_revision=fallback.candidate_revision,
            used_model=False,
        )

    def _discuss_with_model(
        self,
        current: DraftRevisionRecord,
        intent: ConversationIntent,
        message: str,
        catalog: dict[str, FieldCatalogEntry],
        history: list,
    ) -> ConversationTurnResult:
        reply = self.model_dialogue.discuss(
            intent=intent,
            message=message,
            current=current,
            catalog=catalog,
            history=history,
        )
        return ConversationTurnResult(
            intent,
            reply.answer_zh,
            used_model=True,
            provider_metadata=reply.provider_metadata,
        )

    def _modify_with_model(
        self,
        session_id: str,
        current: DraftRevisionRecord,
        message: str,
        catalog: dict[str, FieldCatalogEntry],
        history: list,
    ) -> ConversationTurnResult:
        reply = self.model_dialogue.propose_candidate(
            message=message,
            current=current,
            catalog=catalog,
            history=history,
        )
        candidate_spec = reply.candidate_spec
        if candidate_spec is None:
            raise DialogueModelError("模型未返回候选草案。")
        before = current.spec.model_dump(mode="json")
        after = candidate_spec.model_dump(mode="json")
        changed_fields = [field for field in after if before.get(field) != after.get(field)]
        research_notes = reply.research_notes or {}
        decision = route_identification(candidate_spec)
        status = (
            DraftStatus.DRAFT
            if decision.status == GateStatus.PASS
            else DraftStatus.NEEDS_REVISION
        )
        candidate = self.repository.create_revision(
            session_id,
            candidate_spec,
            source=RevisionSource.AI_CONVERSATION,
            change_reason=(
                "DeepSeek 对话候选修订："
                + ("、".join(changed_fields) if changed_fields else "研究说明")
            ),
            parent_revision_id=current.revision_id,
            activate=False,
            status=status,
            research_notes=research_notes,
        )
        change_summary = "、".join(changed_fields) if changed_fields else "研究说明"
        answer = (
            f"DeepSeek 已生成候选修订 V{candidate.version_number}，涉及字段："
            f"{change_summary}。本地结构校验和识别门控结果为 "
            f"{decision.status.value}。该版本未激活、未接受、未批准、未执行；"
            "请在候选修订面板查看差异后，由你决定接受、放弃或继续讨论。"
        )
        return ConversationTurnResult(
            ConversationIntent.MODIFY,
            answer,
            candidate,
            used_model=True,
            provider_metadata=reply.provider_metadata,
        )

    def _explain(self, spec: CausalSpec) -> ConversationTurnResult:
        method = spec.candidate_methods[0] if spec.candidate_methods else CausalMethod.DESCRIPTIVE
        capability = get_method_capability(method)
        decision = route_identification(spec)
        unresolved = "；".join(decision.required_actions) or "当前基础门禁没有未解决事项"
        answer = (
            f"当前草案首选{format_method_label(method)}。处理变量为 {spec.treatment}，"
            f"结果变量为 {spec.outcome}，处理前协变量为"
            f"{'、'.join(spec.covariates) if spec.covariates else '尚未指定'}。"
            f"当前门禁状态为 {decision.status.value}，需要注意：{unresolved}。"
            + ("该方法已有受控执行器。" if capability.executable else "该方法当前只能用于研究设计讨论。")
            + "本次回答只解释当前草案，没有修改任何字段或版本。"
        )
        return ConversationTurnResult(ConversationIntent.EXPLAIN, answer)

    def _compare(self, spec: CausalSpec, message: str) -> ConversationTurnResult:
        methods = _mentioned_methods(message)
        if not methods:
            methods = list(spec.candidate_methods[:2])
        if len(methods) < 2:
            methods = [*methods, CausalMethod.DESCRIPTIVE][:2]
        parts = []
        for method in methods[:3]:
            capability = get_method_capability(method)
            parts.append(
                f"{format_method_label(method)}："
                f"{'可执行' if capability.executable else '仅支持设计'}；"
                f"需要审核的配置包括 {', '.join(sorted(capability.relevant_fields))}"
            )
        answer = "方法比较如下。" + "；".join(parts) + "。比较不会自动改变当前草案。"
        return ConversationTurnResult(ConversationIntent.COMPARE, answer)

    def _diagnose(self, spec: CausalSpec) -> ConversationTurnResult:
        decision = route_identification(spec)
        if decision.status == GateStatus.PASS:
            detail = "基础识别门禁已通过，但执行后的经验诊断仍可能降低结论等级。"
        else:
            detail = "；".join(decision.required_actions) or "存在尚未结构化的问题。"
        answer = (
            f"当前草案诊断状态为 {decision.status.value}，主张上限为 "
            f"{decision.claim_ceiling.value}。{detail}本次诊断没有修改草案。"
        )
        return ConversationTurnResult(ConversationIntent.DIAGNOSE, answer)

    def _modify(
        self,
        session_id: str,
        current: DraftRevisionRecord,
        message: str,
        catalog: dict[str, FieldCatalogEntry],
    ) -> ConversationTurnResult:
        payload = current.spec.model_dump(mode="json")
        methods = _mentioned_methods(message)
        fields = _mentioned_fields(message, catalog)
        changed: list[str] = []
        if methods:
            payload["candidate_methods"] = [methods[0].value]
            changed.append(f"候选方法改为 {format_method_label(methods[0])}")

        add_requested = bool(re.search(r"加入|新增|添加|作为协变量|控制", message, re.I))
        remove_requested = bool(re.search(r"移除|删除|去掉|不控制", message, re.I))
        current_covariates = list(payload.get("covariates", []))
        if add_requested:
            additions = [
                name
                for name in fields
                if catalog[name].can_be_covariate and name not in current_covariates
            ]
            current_covariates.extend(additions)
            if additions:
                changed.append("新增候选协变量：" + "、".join(additions))
        if remove_requested:
            removals = [name for name in fields if name in current_covariates]
            current_covariates = [name for name in current_covariates if name not in removals]
            if removals:
                changed.append("移除候选协变量：" + "、".join(removals))
        payload["covariates"] = current_covariates

        if not changed:
            return ConversationTurnResult(
                ConversationIntent.MODIFY,
                "我识别到修改意图，但没有找到可安全落入结构化草案的具体方法或字段。"
                "请明确写出方法名，或使用数据中的字段名/中文字段名。当前草案未改变。",
            )
        try:
            candidate_spec = CausalSpec.model_validate(payload)
        except ValidationError as exc:
            return ConversationTurnResult(
                ConversationIntent.MODIFY,
                "候选修改未通过结构校验，因此没有创建新版本。主要问题："
                + "；".join(error["msg"] for error in exc.errors()),
            )

        decision = route_identification(candidate_spec)
        status = (
            DraftStatus.DRAFT
            if decision.status == GateStatus.PASS
            else DraftStatus.NEEDS_REVISION
        )
        candidate = self.repository.create_revision(
            session_id,
            candidate_spec,
            source=RevisionSource.CONVERSATION_REVISION,
            change_reason="；".join(changed),
            parent_revision_id=current.revision_id,
            activate=False,
            status=status,
        )
        answer = (
            "已生成候选修订，但尚未覆盖当前草案。修改内容："
            + "；".join(changed)
            + f"。候选版本为 V{candidate.version_number}，状态为 {candidate.status.value}。"
            "你可以接受修改、放弃修改或继续讨论。"
        )
        return ConversationTurnResult(ConversationIntent.MODIFY, answer, candidate)

