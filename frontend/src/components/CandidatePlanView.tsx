import { useState } from "react";
import type { SetupView, Study } from "../api";
import { EvidenceDetails, Icon, labels } from "./ui";
const names: Record<string, string> = {
  S01: "数据与研究设计审计",
  S02: "分组描述统计",
  S03: "上游证据核验",
  S04: "双组效果分析",
  S05: "研究报告整合",
};
const kinds: Record<string, string> = {
  audit: "只读结构与设计检查",
  descriptive: "真实统计工具 · descriptive",
  gate: "结构化证据门禁",
  ab_test: "真实统计工具 · ab_test",
  report: "整合已保存证据",
};
export function CandidatePlanView({
  setup,
  study,
  busy,
  error,
  onBack,
  onConfigure,
  onGenerate,
  onAdopt,
  onReview,
}: {
  setup: SetupView;
  study: Study | null;
  busy: boolean;
  error: string;
  onBack: () => void;
  onConfigure: () => void;
  onGenerate: () => void;
  onAdopt: () => Promise<void>;
  onReview?: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false),
    r = setup.candidate,
    c = r?.candidate.candidate,
    adopted = setup.phase === "adopted",
    cfg = setup.configuration?.configuration,
    pending = !study || study.status === "candidate";
  return (
    <section className="candidate-workspace">
      <header className="focus-heading">
        <button className="quiet-button" onClick={onBack}>
          ← 返回对话
        </button>
        <span>候选研究方案</span>
        <small>确定性路径 · 模型调用关闭</small>
      </header>
      <div className="candidate-reading">
        <p className="eyebrow">RESEARCH PROPOSAL</p>
        <div className="candidate-title">
          <h1>
            {adopted
              ? pending
                ? "已采纳，等待正式审核。"
                : "已采纳的正式研究方案。"
              : "先核对方案，再决定采纳。"}
          </h1>
          <span className="state-pill">
            {adopted
              ? labels[study?.status || "candidate"] || study?.status
              : c
                ? "尚未采纳"
                : "尚未生成"}
          </span>
        </div>
        <p className="lead-copy">
          {adopted
            ? pending
              ? "原服务已保存新的待审计划版本。当前尚无统计批准或运行。"
              : "本页只读展示已采纳的方案。执行与审核状态来自原研究服务。"
            : "候选只提出受限研究路径。采纳会形成待审版本，不批准、也不开始统计。"}
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {!c ? (
          <div className="research-note">
            <p>请先确认当前数据合同，再生成受限候选。</p>
            <button
              className="primary"
              onClick={setup.configuration ? onGenerate : onConfigure}
              disabled={busy}
            >
              {setup.configuration ? "生成确定性候选" : "返回研究配置"}
            </button>
          </div>
        ) : (
          <>
            <section className="proposal-objective">
              <span className="section-label">研究目标</span>
              <p>{c.objective}</p>
            </section>
            <dl className="candidate-facts">
              <div>
                <dt>研究路径</dt>
                <dd>
                  {c.research_type === "descriptive_binary"
                    ? "双组二元描述性研究"
                    : "已登记随机化的双组二元研究"}
                </dd>
              </div>
              <div>
                <dt>研究指标</dt>
                <dd>{setup.configuration?.configuration.metric}</dd>
              </div>
              <div>
                <dt>观察窗口</dt>
                <dd>{setup.configuration?.configuration.window}</dd>
              </div>
              <div>
                <dt>统计工具调用</dt>
                <dd>
                  {
                    c.steps.filter((s) =>
                      ["descriptive", "ab_test"].includes(s.method),
                    ).length
                  }{" "}
                  次 ·{" "}
                  {c.steps
                    .filter((s) =>
                      ["descriptive", "ab_test"].includes(s.method),
                    )
                    .map((s) => s.method)
                    .join(" + ")}
                </dd>
              </div>
              <div>
                <dt>比较对象</dt>
                <dd>
                  {cfg?.treated_label} 对比 {cfg?.control_label}
                </dd>
              </div>
              <div>
                <dt>分析单位</dt>
                <dd>{cfg?.analysis_unit}</dd>
              </div>
              <div>
                <dt>结果字段与编码</dt>
                <dd>
                  {cfg?.outcome} · {cfg?.negative_value} → 0 /{" "}
                  {cfg?.positive_value} → 1
                </dd>
              </div>
              <div>
                <dt>指标单位</dt>
                <dd>{cfg?.unit} · 差异以百分点展示</dd>
              </div>
            </dl>
            {!r?.source_current && (
              <div className="form-error" role="alert">
                {r?.source_error} 当前不能采纳这份历史候选。
              </div>
            )}
            <section className="plan-steps">
              <h2>步骤与证据依赖</h2>
              {c.steps.map((step, i) => (
                <article className="plan-step" key={step.step_id}>
                  <span className="step-index">{i + 1}</span>
                  <div>
                    <h3>{names[step.step_id] || step.step_id}</h3>
                    <p>{kinds[step.method] || step.method}</p>
                    <small>
                      {step.depends_on.length
                        ? "依赖 " +
                          step.depends_on.map((x) => names[x] || x).join("、")
                        : "从已确认数据与合同开始"}{" "}
                      · 输出 {step.output_evidence}
                    </small>
                  </div>
                  <Icon
                    name={
                      ["descriptive", "ab_test"].includes(step.method)
                        ? "brand"
                        : "chevron"
                    }
                    size={18}
                  />
                </article>
              ))}
            </section>
            <section className="proposal-limits">
              <h2>研究前提与限制</h2>
              <p>
                {c.declared_assignment === "unknown"
                  ? "随机分配依据未知。本候选不包含 A/B，不生成因果效应或推断区间。"
                  : "随机分配资料来自使用者登记与核对；程序不因两组标签而证明随机化真实发生。"}
              </p>
              <ul>
                <li>
                  全部已登记记录纳入；缺少必要字段或缺失值时停止，不自动删除或填补。
                </li>
                <li>
                  独立观察单位由使用者确认；重复测量和纵向研究不在本路径范围内。
                </li>
                <li>
                  原工具的样本、组内变异和适用条件须在执行前检查；现在未执行的检查不算通过。
                </li>
                <li>正式人工审核、步骤级授权和预算门禁继续有效。</li>
              </ul>
            </section>
            {adopted ? (
              <div className="adopted-summary">
                <p>
                  <strong>采纳记录已保存。</strong>
                  {pending
                    ? "尚未产生 Approval 或统计 Run。"
                    : "当前研究：" +
                      (labels[study?.status || ""] || study?.status) +
                      " · " +
                      (study?.run_ids.length || 0) +
                      " 个真实 Run。"}
                </p>
                {onReview ? (
                  <button className="primary" onClick={onReview}>
                    {pending ? "进入正式人工审核" : "查看研究执行状态"}
                  </button>
                ) : (
                  study?.links.review && (
                    <a
                      className="button-link primary"
                      href={study.links.review}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {pending
                        ? "前往原工作台正式审核 ↗"
                        : "查看原研究工作流 ↗"}
                    </a>
                  )
                )}
                <small>审核是独立操作，不能用聊天“同意”代替。</small>
              </div>
            ) : (
              <section className="candidate-adoption">
                <label className="confirmation">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  <span>
                    我已核对目标、字段口径、步骤和限制，明确采纳此候选形成待审方案。采纳不授予执行权限。
                  </span>
                </label>
                <div className="scope-actions">
                  <button
                    className="primary"
                    disabled={!confirmed || busy || !r?.source_current}
                    onClick={() => void onAdopt()}
                  >
                    {busy ? "正在核对采纳来源…" : "采纳为待审方案"}
                  </button>
                  <button
                    className="quiet-button"
                    onClick={onConfigure}
                    disabled={busy}
                  >
                    返回核对合同
                  </button>
                </div>
              </section>
            )}
            <EvidenceDetails
              label="候选、合同与计划来源"
              value={{
                configuration: setup.configuration?.contract_ref,
                candidate: r,
                adoption: setup.adoption,
              }}
            />
          </>
        )}
      </div>
    </section>
  );
}
