import type { RefObject } from "react";
import type { Chat, SetupView, ResearchView, Report } from "../api";
import { ResearchCompletion } from "./ResearchFlow";
import { MessageRenderer } from "./MessageRenderer";
import { Icon, labels } from "./ui";
export function ConversationView({
  chat,
  chatId,
  loading,
  error,
  reader,
  onScroll,
  onDraft,
  onConfigure,
  onCandidate,
  setup,
  research,
  completion,
  onResearch,
  onReport,
  onInsights,
}: {
  chat: Chat | null;
  chatId: string | null;
  loading: boolean;
  error: string;
  reader: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  onDraft: (v: string) => void;
  onConfigure: () => void;
  onCandidate: () => void;
  setup: SetupView | null;
  research?: ResearchView | null;
  completion?: Report | null;
  onResearch?: () => void;
  onReport?: () => void;
  onInsights?:()=>void;
}) {
  return (
    <div
      ref={reader}
      className="message-scroll"
      data-testid="message-scroll"
      onScroll={onScroll}
    >
      <div className="reading-column" data-chat-id={chat?.session.id || ""}>
        {loading || (!chat && chatId && !error) ? (
          <div className="reading-status" role="status">
            正在核对当前会话与来源…
          </div>
        ) : error ? (
          <section className="error-state" role="alert">
            <h2>当前研究需要重新核验</h2>
            <p>{error}</p>
            <button onClick={() => location.reload()}>刷新并核对</button>
            {onInsights&&<button onClick={onInsights}>检查本研究来源</button>}
          </section>
        ) : !chat?.messages.length ? (
          <section className="welcome">
            <div className="welcome-mark">
              <Icon name="brand" size={30} />
            </div>
            <p className="eyebrow">CausalOps · AI Research Workspace</p>
            <h1>从一个值得研究的问题开始。</h1>
            <p>与研究持续对话，让结论有证据、过程可审核。</p>
            <div className="prompt-starters">
              <button
                onClick={() =>
                  onDraft(
                    "我有一份双组实验数据，需要先确认指标、比较对象和研究条件。",
                  )
                }
              >
                我有一份数据，如何开始？<span>↗</span>
              </button>
              <button
                onClick={() =>
                  onDraft("请解释已保存研究的样本量、比例差、置信区间与限制。")
                }
              >
                解读一项已有研究<span>↗</span>
              </button>
            </div>
            <small>当前支持单表、双组、二元结果的受控研究。</small>
          </section>
        ) : (
          chat.messages.map((m) => (
            <MessageRenderer key={m.id} m={m} currentSubject={chat.study?.id} />
          ))
        )}
        {!error && research && chat?.study?.id === research.task.id && (
          <section className="research-chat-status">
            <div>
              <span>
                正式研究 ·{" "}
                {labels[research.task.status] || research.task.status}
              </span>
              <small>
                {research.steps.filter((x) => x.status === "succeeded").length}/
                {research.steps.length} 步证据已保存
                {research.active ? " · 后台运行中" : ""}
              </small>
            </div>
            <button onClick={onResearch}>
              {research.task.status === "candidate"
                ? "正式审核"
                : research.task.status === "approved"
                  ? "审核与开始"
                  : "执行状态与控制"}{" "}
              →
            </button>
          </section>
        )}
        {!error &&
          completion &&
          chat?.study?.id === completion.task_id &&
          onReport && (
            <ResearchCompletion report={completion} onReport={onReport} />
          )}
        {!error && chat?.study && onInsights && <div className="chat-next-actions"><button onClick={onInsights}>查看研究诊断与决定 →</button><small>显式检查 · 历史决定 · 无执行权限</small></div>}
        {!error && setup?.editable && (
          <section className="setup-action" aria-label="当前数据配置状态">
            <div>
              <span className="eyebrow">
                {setup.configuration
                  ? "数据合同已确认"
                  : "数据已登记 · 合同待确认"}
              </span>
              <p>
                {setup.candidate
                  ? "候选已编译，请核对并显式采纳。"
                  : setup.configuration
                    ? "研究口径已保存，可以生成受限候选。"
                    : "下一步，确认字段、比较组与研究条件。"}
              </p>
            </div>
            <button
              onClick={
                setup.candidate
                  ? onCandidate
                  : setup.configuration
                    ? onCandidate
                    : onConfigure
              }
            >
              {setup.candidate
                ? "查看候选"
                : setup.configuration
                  ? "生成候选"
                  : "配置研究"}
              <Icon name="chevron" size={16} />
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
