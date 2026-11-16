import type { Message } from "../api";
import { Markdown } from "./ui";
function answerLayout(text: string, scope?: string) {
  if (scope !== "verified_automation_report") return { lead: null, body: text };
  const parts = text.split("\n\n");
  const index = parts.findIndex((x) =>
    /^(绝对差|描述性差异)（/.test(x.replaceAll("**", "")),
  );
  return {
    lead: index < 0 ? null : parts[index].replaceAll("**", ""),
    body: parts
      .filter((_, i) => i !== index)
      .join("\n\n")
      .replaceAll("**", ""),
  };
}
function hasSavedResult(m: Message) {
  const a = m.answer, ref = m.source_ref;
  const boundRuns = ref?.run_ids;
  const report = a?.scope === "verified_automation_report" &&
    typeof ref?.report_sha === "string" && /^[a-f0-9]{64}$/i.test(ref.report_sha);
  const runFacts = ["selected_run", "explicit_comparison"].includes(a?.scope || "") &&
    !!a?.facts?.length;
  // The API already verifies sources; this only labels replies that reference them.
  return !!(m.available && !m.error && m.status === "completed" && m.binding_id &&
    m.subject_id && ref?.subject_id === m.subject_id && Array.isArray(boundRuns) &&
    a?.run_ids.length && a.run_ids.every(id => boundRuns.includes(id)) &&
    (report || runFacts));
}
export function MessageRenderer({
  m,
  currentSubject,
}: {
  m: Message;
  currentSubject: string | undefined;
}) {
  const a = m.answer,
    layout = answerLayout(a?.text || "", a?.scope);
  return (
    <section
      className="turn"
      data-turn-id={m.id}
      data-bound-task={m.subject_id || ""}
    >
      <div className="user-row">
        <div className="user-bubble">{m.question}</div>
      </div>
      <article className="assistant-message">
        {m.binding_id && m.subject_id !== currentSubject && (
          <p className="historical">发送时的历史研究 · 本轮来源保留</p>
        )}
        {!m.binding_id && currentSubject && (
          <p className="historical">此条消息发送时尚未关联研究</p>
        )}
        {!m.available ? (
          <p className="error" role="alert">
            {m.error}
          </p>
        ) : m.status === "running" ? (
          <p className="muted">此轮仍在保存或等待核查，未自动重发。</p>
        ) : m.status === "interrupted" ? (
          <p className="error">此轮已中断，请核对来源后再决定是否重新提问。</p>
        ) : (
          <>
            {layout.lead && <p className="result-lead">{layout.lead}</p>}
            <div className="prose">
              <Markdown text={layout.body} />
            </div>
            {!!a?.facts?.length && a.scope !== "verified_automation_report" && (
              <div className="fact-list">
                {a.facts.map((f) => (
                  <p key={f.id}>
                    {f.text}：
                    {typeof f.value === "object"
                      ? JSON.stringify(f.value)
                      : String(f.value)}
                  </p>
                ))}
              </div>
            )}
          </>
        )}
        <details className="source">
          <summary>
            {hasSavedResult(m) ? "依据：已保存研究结果" : "回答依据"}
          </summary>
          <p>{a?.source || "消息状态记录"}</p>
          <p className="small">
            聊天不是批准；原回复及每轮绑定保持保存时的版本。
          </p>
          <pre>
            {JSON.stringify(
              {
                message: m.id,
                binding: m.binding_id,
                research: m.subject_id,
                run_ids: a?.run_ids || [],
                source: m.source_ref,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </article>
    </section>
  );
}
