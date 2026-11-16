import { useState } from "react";
import type { ResearchView, ResearchAction, Report } from "../api";
import { EvidenceDetails, labels } from "./ui";
const stepNames: Record<string, string> = {
  S01: "数据与研究设计审计",
  S02: "分组描述统计",
  S03: "上游证据核验",
  S04: "A/B 效果分析",
  S05: "研究报告整合",
};
export function ResearchFlow({
  value,
  busy,
  error,
  notice,
  onAction,
  onRefresh,
  onBack,
  onReport,
}: {
  value: ResearchView | null;
  busy: boolean;
  error: string;
  notice: string;
  onAction: (a: ResearchAction) => Promise<void>;
  onRefresh: () => void;
  onBack: () => void;
  onReport: () => void;
}) {
  const [approve, setApprove] = useState(false),
    [cancel, setCancel] = useState(false);
  const t = value?.task,
    p = t?.plan,
    permissions = value?.permissions,
    sourceUrl =
      p?.scope.assignment_source ||
      (typeof value?.task.source?.source_url === "string"
        ? value.task.source.source_url
        : "");
  const authority = value ? (
    <section className="flow-authority">
      <h2>{t!.status === "candidate" ? "正式人工审核" : "批准与任务控制"}</h2>
      {permissions!.approve && (
        <>
          <label className="confirmation">
            <input
              type="checkbox"
              checked={approve}
              onChange={(e) => setApprove(e.target.checked)}
            />
            <span>
              我已核对完整计划、数据版本、合同、比较组、指标、窗口、步骤和预算，正式批准本计划范围。批准后仍需单独启动。
            </span>
          </label>
          <button
            className="primary"
            disabled={!approve || busy}
            onClick={() => void onAction("approve")}
          >
            保存正式批准
          </button>
        </>
      )}
      {value.approval && (
        <p className="approval-receipt">
          正式批准收据已通过原服务核验 · 绑定当前计划 v{p!.version}。
        </p>
      )}
      {permissions!.start && (
        <>
          <p>已批准，尚未派发剩余统计步骤。请明确开始研究。</p>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void onAction("start")}
          >
            开始已批准研究
          </button>
        </>
      )}
      <div className="execution-controls">
        {permissions!.pause && (
          <button disabled={busy} onClick={() => void onAction("pause")}>
            请求暂停
          </button>
        )}
        {permissions!.resume && (
          <button disabled={busy} onClick={() => void onAction("resume")}>
            核查恢复并继续
          </button>
        )}
        {t!.status === "completed" && (
          <button className="primary" onClick={onReport}>
            阅读完整研究报告
          </button>
        )}
      </div>
      {value.active && (
        <p className="small muted">
          后台任务正在排队或执行。刷新只读取状态，不会重复派发。
        </p>
      )}
      {t!.status === "pause_requested" && (
        <p className="research-note">
          已请求暂停，将在当前步骤的安全边界停止；不会强制中断底层计算。
        </p>
      )}
      {t!.status === "cancel_requested" && (
        <p className="research-note">
          已请求取消，当前步骤结束后不再派发下游。
        </p>
      )}
      {t!.status === "cancelled" && (
        <p className="research-note">
          取消为终态，不能恢复。已有结果保留；后继研究须重新审核。
        </p>
      )}
      {notice && (
        <p className="feedback" role="status">
          {notice}
        </p>
      )}
      {permissions!.cancel && (
        <details className="cancel-control">
          <summary>取消此研究</summary>
          <label className="confirmation">
            <input
              type="checkbox"
              checked={cancel}
              onChange={(e) => setCancel(e.target.checked)}
            />
            <span>
              我确认取消当前任务，保留已有步骤与 Run；取消后不能恢复。
            </span>
          </label>
          <button
            disabled={!cancel || busy}
            onClick={() => void onAction("cancel")}
          >
            确认取消研究
          </button>
        </details>
      )}
    </section>
  ) : null;
  return (
    <section className="research-flow">
      <header className="focus-heading">
        <button className="quiet-button" onClick={onBack}>
          ← 返回对话
        </button>
        <span>研究审核与执行</span>
        <small>人工批准 ≠ 已开始统计</small>
        <button className="quiet-button" onClick={onRefresh} disabled={busy}>
          刷新状态
        </button>
      </header>
      <div className="flow-reading">
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {!value ? (
          <p>{error?'当前来源未通过核验。历史证据保留，请核对后刷新；不使用其他研究替代。':'正在核对当前研究与批准来源…'}</p>
        ) : (
          <>
            <div className="flow-title">
              <p className="eyebrow">CONTROLLED RESEARCH</p>
              <span className="state-pill" data-task-status={t!.status}>
                {labels[t!.status] || t!.status}
              </span>
            </div>
            <h1>{p!.objective}</h1>
            <p className="lead-copy">
              研究口径、整体批准与每一步执行授权分别核验。下方状态来自已保存任务，不表示预计剩余时间。
            </p>
            <details
              className="execution-scope"
              open={t!.status === "candidate"}
            >
              <summary>数据、研究范围与结论限制</summary>{" "}
              <dl className="candidate-facts">
                <div>
                  <dt>正式指标</dt>
                  <dd>
                    {p!.scope.metric || p!.scope.outcome} · {p!.scope.unit}
                  </dd>
                </div>
                <div>
                  <dt>比较对象</dt>
                  <dd>{Object.values(p!.scope.groups).join(" / ")}</dd>
                </div>
                <div>
                  <dt>分析单位</dt>
                  <dd>{p!.scope.analysis_unit}</dd>
                </div>
                <div>
                  <dt>观察窗口</dt>
                  <dd>{p!.scope.window || p!.scope.metric_window}</dd>
                </div>
                <div>
                  <dt>数据与合同版本</dt>
                  <dd>
                    数据 {String(p!.data.frame_sha).slice(0, 10)}… · 合同 v
                    {String(p!.contract_ref.version)}
                  </dd>
                </div>
                <div>
                  <dt>计划版本</dt>
                  <dd>
                    v{p!.version} · {p!.steps.length} 个逻辑步骤 /{" "}
                    {p!.steps.filter((s) => s.kind === "statistical").length}{" "}
                    次预期统计调用
                  </dd>
                </div>
              </dl>
              <section className="flow-limits">
                <h2>研究条件与结论边界</h2>
                <p>
                  {p!.scope.assignment === "unknown"
                    ? "随机分配依据未知：仅授权描述性分析，不生成 A/B 因果效应或推断区间。"
                    : "随机分配依据来自已登记的设计资料和使用者核对；两个组别本身不构成随机化证明。"}
                </p>
                {sourceUrl && (
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                    查看登记的研究设计来源 ↗
                  </a>
                )}
                <p>
                  严格缺失策略，不自动删样本、填补或更换方法。程序不能证明无干扰、外部代表性及全部识别假设。结论限于当前对象、指标与观察窗口。
                </p>
              </section>
            </details>
            {value.binding_error && (
              <p className="form-error" role="alert">
                执行授权不可用：{value.binding_error}
              </p>
            )}
            {value.review_requirement && (
              <p className="form-error">{value.review_requirement}</p>
            )}
            {t!.status === "candidate" ? null : authority}
            <section className="flow-progress">
              <div className="progress-heading">
                <h2>实际步骤与证据</h2>
                <span>
                  {value.steps.filter((x) => x.status === "succeeded").length}/
                  {value.steps.length} 已保存
                </span>
              </div>
              <div className="real-progress" aria-label="持久化步骤进度">
                <div
                  style={{
                    width:
                      (100 *
                        value.steps.filter((x) => x.status === "succeeded")
                          .length) /
                        value.steps.length +
                      "%",
                  }}
                />
              </div>
              {value.steps.map((s) => (
                <details key={s.step_id} className="execution-step">
                  <summary>
                    <span className={"step-marker " + s.status}>
                      {s.status === "succeeded" ? "✓" : "·"}
                    </span>
                    <span>{stepNames[s.step_id] || s.name}</span>
                    <small>{labels[s.status] || s.status}</small>
                  </summary>
                  <p>
                    依赖：
                    {p!.steps
                      .find((x) => x.step_id === s.step_id)
                      ?.depends_on.map((x) => stepNames[x] || x)
                      .join(" → ") || "数据、合同及完整计划批准"}
                  </p>
                  <p>
                    {s.run_id
                      ? "实际统计 Run：" + s.run_id
                      : "尚无已确认统计 Run；审计与证据核验不属于统计运行。"}
                  </p>
                  <EvidenceDetails
                    label="步骤证据与实际来源"
                    value={{
                      step: s,
                      evidence: value.evidence[s.step_id] ?? null,
                    }}
                  />
                </details>
              ))}
            </section>
            {(t!.reason || value.jobs[0]?.error_note) && (
              <p className="form-error">
                停止/核查原因：{t!.reason || value.jobs[0].error_note}{" "}
                已保存证据保留；不能确定执行结果时先调和，不盲目重算。
              </p>
            )}
            <section className="flow-budget">
              <h2>实际预算与停止边界</h2>
              <p>
                模型物理请求 {value.budget.physical_requests}/12 · 语义修订{" "}
                {value.budget.semantic_revisions}/2 ·
                每个统计工具最多2次尝试（包含首次）。
              </p>
              <p>
                实际工具尝试：
                {value.steps
                  .filter(
                    (s) =>
                      p!.steps.find((x) => x.step_id === s.step_id)?.kind ===
                      "statistical",
                  )
                  .map(
                    (s) =>
                      (stepNames[s.step_id] || s.step_id) +
                      " " +
                      s.tool_attempts +
                      "/2",
                  )
                  .join("；")}
                。
              </p>
              <p>
                输入令牌 {value.budget.input_tokens}，输出令牌{" "}
                {value.budget.output_tokens}，未知用量{" "}
                {value.budget.usage_unknown} 次。当前固定执行不调用模型。
              </p>
              <p className="small muted">
                ¥1
                为估算预警，非精确账单截断；没有已核实价格快照时不展示人民币费用。上游未通过、批准失效、数据变化、预算不足或运行不确定时停止。
              </p>
            </section>
            {t!.status === "candidate" && authority}
            <EvidenceDetails
              label="计划、批准、预算与执行事件的完整来源"
              value={{
                task: t,
                approval: value.approval,
                review_sha: value.review_sha,
                jobs: value.jobs,
                budget: value.budget,
                events: value.events,
              }}
            />
          </>
        )}
      </div>
    </section>
  );
}
export function ResearchCompletion({
  report,
  onReport,
}: {
  report: Report;
  onReport: () => void;
}) {
  return (
    <section
      className="completion-summary"
      data-completion-task={report.task_id}
    >
      <p className="eyebrow">已保存研究结果 · 确定性事实摘要</p>
      <h2>
        {report.scope.metric || report.scope.outcome}：
        {report.display.difference_kind} {report.display.difference}{" "}
        {report.display.unit}
      </h2>
      <table>
        <thead>
          <tr>
            <th>比较组</th>
            <th>样本量</th>
            <th>比例</th>
          </tr>
        </thead>
        <tbody>
          {report.display.groups.map((g) => (
            <tr key={g.label}>
              <td>{g.label}</td>
              <td>{g.n.toLocaleString()}</td>
              <td>{g.rate}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        {report.display.interval
          ? "原工具95%区间：[" +
            report.display.interval.join(", ") +
            "] 个百分点。"
          : "本研究仅有描述统计，没有执行 A/B 或推断区间。"}
      </p>
      <p>
        观察窗口：{report.scope.window || report.scope.metric_window}；方法：
        {report.display.method}。
      </p>
      {report.risks
        .filter((x) =>
          ["source_confirmation", "unverified_assumptions"].includes(x.rule),
        )
        .map((x) => (
          <p className="completion-limitation" key={x.rule}>
            研究限制：{x.detail}
          </p>
        ))}
      <button className="quiet-button" onClick={onReport}>
        阅读全文与运行来源 →
      </button>
      <EvidenceDetails
        label="此摘要的实际报告与运行引用"
        value={{
          task: report.task_id,
          report_sha: report.report_sha,
          run_ids: report.manifest.source_runs,
          scope: report.scope,
        }}
      />
    </section>
  );
}
