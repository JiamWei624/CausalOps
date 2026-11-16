import type { Report, Study } from "../api";
import { Markdown, EvidenceDetails } from "./ui";
export function ReportReader({
  report,
  study,
  onClose,
  onInsights,
}: {
  report: Report;
  study: Study | null;
  onClose: () => void;
  onInsights?:()=>void;
}) {
  return (
    <div
      className="report-surface"
      role="dialog"
      aria-modal="true"
      aria-label="完整研究报告"
      data-report-task={report.task_id}
    >
      <header className="report-toolbar">
        <button onClick={() => onClose()}>← 返回原对话</button>
        <span>已保存的正式研究报告</span>
        {onInsights&&<button onClick={onInsights}>研究诊断与决定</button>}
        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(report, null, 2)], {
              type: "application/json",
            });
            const url = URL.createObjectURL(blob),
              a = document.createElement("a");
            a.href = url;
            a.download = "CausalOps_研究证据.json";
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          导出原始证据
        </button>
      </header>
      <article className="report-content">
        <p className="eyebrow">CausalOps · 研究报告</p>
        <h1>{study?.title}</h1>
        <p className="report-subtitle">
          {report.scope.analysis_unit} ·{" "}
          {report.scope.window || report.scope.metric_window}
        </p>
        <section className="report-result">
          <p>{report.display.difference_kind}</p>
          <div className="effect-value">
            {report.display.difference}
            <span>{report.display.unit}</span>
          </div>
          <p>
            {report.display.interval
              ? "原工具95%区间：[" +
                report.display.interval.join(", ") +
                "] 个百分点"
              : "仅有描述性统计；没有执行推断区间。"}
          </p>
        </section>
        <table>
          <thead>
            <tr>
              <th>比较组</th>
              <th>样本量</th>
              <th>{report.scope.metric || report.scope.outcome}</th>
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
        <h2>研究限制与证据边界</h2>
        {report.risks
          .filter((x) =>
            ["unverified_assumptions", "source_confirmation"].includes(x.rule),
          )
          .map((x) => (
            <p key={x.rule}>{x.detail}</p>
          ))}
        <p>
          统计方法：{report.display.method}
          。以上数值直接读取当前研究已核验报告；没有在浏览器重新估计。
        </p>
        <h2>保存的完整报告正文</h2>
        <div className="prose">
          <Markdown
            text={
              report.display.text ||
              "原报告未保存额外叙述，数值与步骤来源见下方。"
            }
          />
        </div>
        <h2>运行与来源</h2>
        {report.manifest.source_runs.map((x, i) => (
          <p className="run-ref" key={x}>
            {i === 0 ? "描述统计" : "A/B 效果分析"} <code>{x}</code>
          </p>
        ))}
        <EvidenceDetails label="完整精度、版本及报告来源" value={report} />
      </article>
    </div>
  );
}
